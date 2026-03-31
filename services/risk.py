"""
services/risk.py — Portfolio-Risiko-Analyse.

Berechnet:
- Value at Risk (Monte Carlo Simulation)
- Portfolio-Beta
- Sektor-Konzentration (Herfindahl-Index)
- Drawdown-Analyse
- Korrelationsbasiertes Klumpenrisiko
"""

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class RiskMetrics:
    """Portfolio-Risiko-Kennzahlen."""
    # VaR
    var_95_eur: float = 0.0          # 95% VaR in EUR (täglicher Verlust)
    var_99_eur: float = 0.0          # 99% VaR in EUR
    var_95_pct: float = 0.0          # 95% VaR als %
    var_99_pct: float = 0.0          # 99% VaR als %
    cvar_95_eur: float = 0.0         # Conditional VaR (Expected Shortfall)

    # Beta
    portfolio_beta: float | None = None
    beta_description: str = ""

    # Sektor-Konzentration
    herfindahl_index: float = 0.0    # 0-1, höher = konzentrierter
    concentration_warning: str = ""
    top_sector: str = ""
    top_sector_pct: float = 0.0

    # Drawdown
    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_dd_start: str = ""
    max_dd_end: str = ""
    recovery_days: int | None = None

    # Korrelationsrisiko
    avg_correlation: float | None = None
    correlation_warning: str = ""
    high_corr_pairs: list = field(default_factory=list)  # [(t1, t2, corr), ...]
    corr_matrix: pd.DataFrame | None = None


# ---------------------------------------------------------------------------
# Value at Risk (Monte Carlo)
# ---------------------------------------------------------------------------

def calc_portfolio_var(positions: list[dict],
                       current_prices: dict[str, float],
                       n_simulations: int = 10000,
                       n_days: int = 1) -> dict:
    """Berechnet den Value at Risk via Monte Carlo Simulation.

    Args:
        positions: Liste von offenen Positionen [{ticker, position}, ...]
        current_prices: {ticker: aktueller_kurs}
        n_simulations: Anzahl Simulationen
        n_days: Zeithorizont in Tagen

    Returns:
        Dict mit var_95, var_99, cvar_95에 (in EUR und %)
    """
    if not positions or not current_prices:
        return {"var_95_eur": 0, "var_99_eur": 0, "var_95_pct": 0,
                "var_99_pct": 0, "cvar_95_eur": 0}

    # Ticker und Gewichte sammeln
    tickers = []
    weights = []
    total_value = 0.0

    for p in positions:
        ticker = p["ticker"]
        pos = p["position"]
        price = current_prices.get(ticker, pos.get("buy_price", 0))
        value = price * pos.get("quantity", 0)
        if value > 0:
            tickers.append(ticker)
            weights.append(value)
            total_value += value

    if total_value == 0 or not tickers:
        return {"var_95_eur": 0, "var_99_eur": 0, "var_95_pct": 0,
                "var_99_pct": 0, "cvar_95_eur": 0}

    weights = np.array(weights) / total_value

    # Historische Returns laden (1 Jahr)
    returns_data = {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(period="1y")
            if not hist.empty and len(hist) > 20:
                rets = hist["Close"].pct_change().dropna()
                returns_data[t] = rets.values
        except Exception:
            pass

    if not returns_data:
        return {"var_95_eur": 0, "var_99_eur": 0, "var_95_pct": 0,
                "var_99_pct": 0, "cvar_95_eur": 0}

    # Gemeinsame Länge
    min_len = min(len(v) for v in returns_data.values())
    valid_tickers = [t for t in tickers if t in returns_data]
    if not valid_tickers:
        return {"var_95_eur": 0, "var_99_eur": 0, "var_95_pct": 0,
                "var_99_pct": 0, "cvar_95_eur": 0}

    returns_matrix = np.column_stack(
        [returns_data[t][-min_len:] for t in valid_tickers]
    )

    # Gewichte für verfügbare Ticker neu normalisieren
    valid_weights = np.array([weights[tickers.index(t)] for t in valid_tickers])
    valid_weights = valid_weights / valid_weights.sum()

    # Kovarianzmatrix
    cov_matrix = np.cov(returns_matrix, rowvar=False)

    # Monte Carlo Simulation
    mean_returns = np.mean(returns_matrix, axis=0)
    np.random.seed(42)

    simulated_returns = np.random.multivariate_normal(
        mean_returns * n_days,
        cov_matrix * n_days,
        n_simulations,
    )

    # Portfolio-Returns
    portfolio_returns = simulated_returns @ valid_weights
    portfolio_losses = -portfolio_returns * total_value

    # VaR
    var_95_eur = float(np.percentile(portfolio_losses, 95))
    var_99_eur = float(np.percentile(portfolio_losses, 99))
    var_95_pct = float(np.percentile(-portfolio_returns, 95) * 100)
    var_99_pct = float(np.percentile(-portfolio_returns, 99) * 100)

    # CVaR (Expected Shortfall)
    cvar_95_eur = float(np.mean(portfolio_losses[portfolio_losses >= var_95_eur]))

    return {
        "var_95_eur": round(var_95_eur, 2),
        "var_99_eur": round(var_99_eur, 2),
        "var_95_pct": round(var_95_pct, 2),
        "var_99_pct": round(var_99_pct, 2),
        "cvar_95_eur": round(cvar_95_eur, 2),
    }


# ---------------------------------------------------------------------------
# Portfolio-Beta
# ---------------------------------------------------------------------------

def calc_portfolio_beta(positions: list[dict],
                        current_prices: dict[str, float],
                        benchmark: str = "^GSPC") -> dict:
    """Berechnet den gewichteten Portfolio-Beta relativ zum Benchmark.

    Returns:
        Dict mit beta, description
    """
    if not positions:
        return {"beta": None, "description": "Keine offenen Positionen"}

    tickers = []
    weights = []
    total_value = 0.0

    for p in positions:
        ticker = p["ticker"]
        pos = p["position"]
        price = current_prices.get(ticker, pos.get("buy_price", 0))
        value = price * pos.get("quantity", 0)
        if value > 0:
            tickers.append(ticker)
            weights.append(value)
            total_value += value

    if total_value == 0:
        return {"beta": None, "description": "Kein Portfolio-Wert"}

    weights = np.array(weights) / total_value

    # Benchmark-Returns
    try:
        bm_hist = yf.Ticker(benchmark).history(period="1y")
        bm_returns = bm_hist["Close"].pct_change().dropna()
    except Exception:
        return {"beta": None, "description": "Benchmark-Daten nicht verfügbar"}

    # Einzelne Betas berechnen und gewichten
    portfolio_beta = 0.0
    n_valid = 0

    for i, t in enumerate(tickers):
        try:
            hist = yf.Ticker(t).history(period="1y")
            if hist.empty or len(hist) < 30:
                continue
            stock_returns = hist["Close"].pct_change().dropna()

            # Gemeinsame Datenpunkte
            common_idx = stock_returns.index.intersection(bm_returns.index)
            if len(common_idx) < 30:
                continue

            sr = stock_returns.loc[common_idx].values
            br = bm_returns.loc[common_idx].values

            # Beta = Cov(stock, market) / Var(market)
            cov = np.cov(sr, br)[0, 1]
            var_market = np.var(br)
            if var_market > 0:
                beta = cov / var_market
                portfolio_beta += beta * weights[i]
                n_valid += 1
        except Exception:
            continue

    if n_valid == 0:
        return {"beta": None, "description": "Nicht genug Daten"}

    # Beschreibung
    if portfolio_beta > 1.3:
        desc = "Aggressiv — Portfolio bewegt sich stärker als der Markt"
    elif portfolio_beta > 1.0:
        desc = "Leicht aggressiv — etwas volatiler als der Markt"
    elif portfolio_beta > 0.7:
        desc = "Moderat — bewegt sich ähnlich wie der Markt"
    elif portfolio_beta > 0.3:
        desc = "Defensiv — weniger volatil als der Markt"
    else:
        desc = "Sehr defensiv — kaum Marktsensitivität"

    return {
        "beta": round(portfolio_beta, 2),
        "description": desc,
    }


# ---------------------------------------------------------------------------
# Sektor-Konzentration
# ---------------------------------------------------------------------------

def calc_sector_concentration(sector_allocation: list[dict]) -> dict:
    """Berechnet Konzentrations-Kennzahlen basierend auf Sektor-Allokation.

    Args:
        sector_allocation: Output von portfolio.calc_sector_allocation()

    Returns:
        Dict mit herfindahl_index, warning, top_sector, top_sector_pct
    """
    if not sector_allocation:
        return {
            "herfindahl_index": 0,
            "warning": "",
            "top_sector": "",
            "top_sector_pct": 0,
        }

    weights = [s["weight_pct"] / 100 for s in sector_allocation]
    hhi = sum(w ** 2 for w in weights)

    top = sector_allocation[0]
    top_sector = top["sector"]
    top_pct = top["weight_pct"]

    warning = ""
    if top_pct > 60:
        warning = f"🔴 Extreme Konzentration: {top_pct:.0f}% in {top_sector} — hohes Klumpenrisiko!"
    elif top_pct > 40:
        warning = f"⚠️ Hohe Konzentration: {top_pct:.0f}% in {top_sector} — Diversifikation empfohlen."
    elif hhi > 0.25:
        warning = f"⚠️ Mäßige Konzentration (HHI: {hhi:.2f}) — einige Sektoren übergewichtet."

    return {
        "herfindahl_index": round(hhi, 4),
        "warning": warning,
        "top_sector": top_sector,
        "top_sector_pct": round(top_pct, 1),
    }


# ---------------------------------------------------------------------------
# Drawdown-Analyse
# ---------------------------------------------------------------------------

def calc_drawdown_analysis(equity_curve: pd.DataFrame = None) -> dict:
    """Analysiert Drawdown-Phasen im Portfolio.

    Args:
        equity_curve: Output von portfolio.calc_equity_curve()

    Returns:
        Dict mit current_dd, max_dd, max_dd_start/end, recovery_days
    """
    if equity_curve is None or equity_curve.empty:
        return {
            "current_drawdown_pct": 0,
            "max_drawdown_pct": 0,
            "max_dd_start": "",
            "max_dd_end": "",
            "recovery_days": None,
        }

    values = equity_curve["Portfolio"].values
    dates = equity_curve["Datum"].values

    if len(values) < 2:
        return {
            "current_drawdown_pct": 0,
            "max_drawdown_pct": 0,
            "max_dd_start": "",
            "max_dd_end": "",
            "recovery_days": None,
        }

    # Running Maximum
    cummax = np.maximum.accumulate(values)
    drawdowns = (values - cummax) / cummax

    # Aktueller Drawdown
    current_dd = float(drawdowns[-1]) * 100

    # Max Drawdown
    max_dd_idx = np.argmin(drawdowns)
    max_dd = float(drawdowns[max_dd_idx]) * 100

    # Start & Ende des Max DD
    peak_idx = np.argmax(values[:max_dd_idx + 1])
    max_dd_start = str(pd.Timestamp(dates[peak_idx]).strftime("%Y-%m-%d"))
    max_dd_end = str(pd.Timestamp(dates[max_dd_idx]).strftime("%Y-%m-%d"))

    # Recovery: Ab Max DD trough, wann wurde das alte Hoch wieder erreicht?
    recovery_days = None
    peak_value = values[peak_idx]
    for j in range(max_dd_idx + 1, len(values)):
        if values[j] >= peak_value:
            recovery_days = int((pd.Timestamp(dates[j]) -
                                  pd.Timestamp(dates[max_dd_idx])).days)
            break

    return {
        "current_drawdown_pct": round(current_dd, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "max_dd_start": max_dd_start,
        "max_dd_end": max_dd_end,
        "recovery_days": recovery_days,
    }


# ---------------------------------------------------------------------------
# Korrelationsrisiko (Klumpenrisiko)
# ---------------------------------------------------------------------------

def calc_correlation_risk(positions: list[dict]) -> dict:
    """Berechnet die Intra-Portfolio-Korrelation als Klumpenrisiko-Indikator.

    Returns:
        Dict mit avg_correlation, warning, high_corr_pairs
    """
    if len(positions) < 2:
        return {
            "avg_correlation": None,
            "warning": "",
            "high_corr_pairs": [],
        }

    tickers = list(set(p["ticker"] for p in positions))
    if len(tickers) < 2:
        return {
            "avg_correlation": None,
            "warning": "Nur ein Ticker — keine Korrelation berechenbar",
            "high_corr_pairs": [],
        }

    # Returns laden
    returns_data = {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(period="6mo")
            if not hist.empty and len(hist) > 30:
                idx = hist.index.tz_localize(None) if hist.index.tz else hist.index
                returns_data[t] = pd.Series(
                    hist["Close"].pct_change().dropna().values,
                    index=idx[1:len(hist)],
                    name=t,
                )
        except Exception:
            pass

    if len(returns_data) < 2:
        return {
            "avg_correlation": None,
            "warning": "Nicht genug Daten für Korrelationsberechnung",
            "high_corr_pairs": [],
        }

    # Korrelationsmatrix
    df = pd.DataFrame(returns_data).ffill().bfill().dropna()
    if df.empty or len(df) < 10:
        return {
            "avg_correlation": None,
            "warning": "",
            "high_corr_pairs": [],
        }

    corr = df.corr()

    # Durchschnittliche Korrelation (ohne Diagonale)
    n = len(corr)
    mask = np.ones((n, n), dtype=bool)
    np.fill_diagonal(mask, False)
    avg_corr = float(corr.values[mask].mean())

    # Hoch korrelierte Paare (> 0.7)
    high_pairs = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c = float(corr.iloc[i, j])
            if abs(c) > 0.7:
                high_pairs.append((cols[i], cols[j], round(c, 2)))

    # Sortieren nach Korrelation (höchste zuerst)
    high_pairs.sort(key=lambda x: abs(x[2]), reverse=True)

    warning = ""
    if avg_corr > 0.6:
        warning = ("🔴 Hohes Klumpenrisiko: Portfolio-Positionen sind stark korreliert "
                   f"(∅ {avg_corr:.2f}). Diversifikation wäre empfehlenswert.")
    elif avg_corr > 0.4:
        warning = (f"⚠️ Mäßiges Korrelationsrisiko (∅ {avg_corr:.2f}). "
                   "Einige Positionen bewegen sich ähnlich.")

    return {
        "avg_correlation": round(avg_corr, 2),
        "warning": warning,
        "high_corr_pairs": high_pairs[:5],  # Top 5
        "corr_matrix": corr,
    }


# ---------------------------------------------------------------------------
# Gesamt-Risk-Report
# ---------------------------------------------------------------------------

def calc_full_risk_report(current_prices: dict[str, float] = None) -> RiskMetrics:
    """Erstellt einen vollständigen Risiko-Report für das Portfolio."""
    from services.watchlist import get_open_positions
    from services.portfolio import calc_sector_allocation, calc_equity_curve

    if current_prices is None:
        current_prices = {}

    metrics = RiskMetrics()
    open_pos = get_open_positions()

    if not open_pos:
        return metrics

    # VaR (Monte Carlo)
    var = calc_portfolio_var(open_pos, current_prices)
    metrics.var_95_eur = var["var_95_eur"]
    metrics.var_99_eur = var["var_99_eur"]
    metrics.var_95_pct = var["var_95_pct"]
    metrics.var_99_pct = var["var_99_pct"]
    metrics.cvar_95_eur = var["cvar_95_eur"]

    # Beta
    from services.portfolio import determine_benchmark
    bm_ticker, _ = determine_benchmark(open_pos)
    beta_result = calc_portfolio_beta(open_pos, current_prices, bm_ticker)
    metrics.portfolio_beta = beta_result["beta"]
    metrics.beta_description = beta_result["description"]

    # Sektor-Konzentration
    sectors = calc_sector_allocation(current_prices)
    conc = calc_sector_concentration(sectors)
    metrics.herfindahl_index = conc["herfindahl_index"]
    metrics.concentration_warning = conc["warning"]
    metrics.top_sector = conc["top_sector"]
    metrics.top_sector_pct = conc["top_sector_pct"]

    # Drawdown
    equity = calc_equity_curve(current_prices)
    dd = calc_drawdown_analysis(equity)
    metrics.current_drawdown_pct = dd["current_drawdown_pct"]
    metrics.max_drawdown_pct = dd["max_drawdown_pct"]
    metrics.max_dd_start = dd["max_dd_start"]
    metrics.max_dd_end = dd["max_dd_end"]
    metrics.recovery_days = dd["recovery_days"]

    # Korrelation
    corr = calc_correlation_risk(open_pos)
    metrics.avg_correlation = corr.get("avg_correlation")
    metrics.correlation_warning = corr.get("warning", "")
    metrics.high_corr_pairs = corr.get("high_corr_pairs", [])
    metrics.corr_matrix = corr.get("corr_matrix")

    return metrics
