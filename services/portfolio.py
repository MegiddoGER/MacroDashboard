"""
services/portfolio.py — Portfolio-Performance & Benchmark-Analyse.

Erweitert das bestehende Positions-Tracking (watchlist.py) um:
- Historische Equity-Kurve
- Dynamischer Benchmark-Vergleich (S&P 500 / DAX basierend auf Portfolio-Gewichtung)
- Performance-Metriken (Sharpe, Sortino, Max Drawdown, Win-Rate)
- Sektor-Allokation
"""

import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class PerformanceMetrics:
    """Portfolio-Performance-Kennzahlen."""
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown_pct: float = 0.0
    max_drawdown_eur: float = 0.0
    win_rate: float = 0.0            # % geschlossener Trades mit Gewinn
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    volatility_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    avg_holding_days: float = 0.0
    profit_factor: float = 0.0       # Summe Gewinne / Summe Verluste


# ---------------------------------------------------------------------------
# Benchmark-Auswahl (dynamisch nach Portfolio-Gewichtung)
# ---------------------------------------------------------------------------

def _determine_benchmark(positions: list[dict]) -> tuple[str, str]:
    """Bestimmt den passenden Benchmark basierend auf Portfolio-Gewichtung.

    Regeln:
    - >60% .DE-Ticker → DAX (^GDAXI)
    - >60% US-Ticker → S&P 500 (^GSPC)
    - Gemischt → MSCI World (URTH)

    Returns:
        (ticker, label) Tuple
    """
    if not positions:
        return "^GSPC", "S&P 500"

    total_value = 0.0
    de_value = 0.0
    us_value = 0.0

    for p in positions:
        ticker = p.get("ticker", "")
        pos = p.get("position", {})
        value = pos.get("buy_price", 0) * pos.get("quantity", 0)
        total_value += value
        if ticker.endswith(".DE"):
            de_value += value
        else:
            us_value += value

    if total_value == 0:
        return "^GSPC", "S&P 500"

    de_pct = de_value / total_value
    us_pct = us_value / total_value

    if de_pct > 0.6:
        return "^GDAXI", "DAX"
    elif us_pct > 0.6:
        return "^GSPC", "S&P 500"
    else:
        return "URTH", "MSCI World"


# ---------------------------------------------------------------------------
# Equity-Kurve
# ---------------------------------------------------------------------------

def calc_equity_curve(current_prices: dict[str, float] = None) -> pd.DataFrame | None:
    """Berechnet eine historische Equity-Kurve des Portfolios.

    Nutzt die Kaufdaten der Positionen und historische Kursdaten.
    Gibt einen DataFrame mit Spalten [Datum, Portfolio, Benchmark, Benchmark_Label] zurück.
    """
    from watchlist import get_open_positions, get_closed_positions

    open_pos = get_open_positions()
    closed_pos = get_closed_positions()
    all_positions = open_pos + closed_pos

    if not all_positions:
        return None

    # Frühestes Kaufdatum als Start
    buy_dates = []
    for p in all_positions:
        pos = p["position"]
        bd = pos.get("buy_date")
        if bd:
            try:
                buy_dates.append(datetime.strptime(bd, "%Y-%m-%d"))
            except ValueError:
                pass

    if not buy_dates:
        return None

    start_date = min(buy_dates) - timedelta(days=5)
    end_date = datetime.now()

    # Alle benötigten Ticker sammeln
    tickers = list(set(p["ticker"] for p in all_positions))

    # Benchmark bestimmen
    benchmark_ticker, benchmark_label = _determine_benchmark(all_positions)

    # Historische Daten laden
    hist_data = {}
    for t in tickers + [benchmark_ticker]:
        try:
            tk = yf.Ticker(t)
            hist = tk.history(start=start_date.strftime("%Y-%m-%d"),
                              end=end_date.strftime("%Y-%m-%d"))
            if not hist.empty:
                # Timezone entfernen
                idx = hist.index.tz_localize(None) if hist.index.tz else hist.index
                hist_data[t] = pd.Series(hist["Close"].values, index=idx, name=t)
        except Exception:
            pass

    if not hist_data:
        return None

    # Gemeinsamer DatetimeIndex
    all_dates = pd.DatetimeIndex(sorted(set().union(
        *(s.index for s in hist_data.values())
    )))
    price_df = pd.DataFrame(index=all_dates)
    for t, series in hist_data.items():
        price_df[t] = series
    price_df = price_df.ffill().bfill()

    # Portfolio-Wert pro Tag berechnen
    portfolio_values = pd.Series(0.0, index=price_df.index)
    cash_invested = pd.Series(0.0, index=price_df.index)

    for p in all_positions:
        ticker = p["ticker"]
        pos = p["position"]
        if ticker not in price_df.columns:
            continue

        try:
            buy_dt = pd.Timestamp(pos["buy_date"])
        except (ValueError, KeyError):
            continue

        qty = pos.get("quantity", 0)
        buy_price = pos.get("buy_price", 0)

        sell_dt = None
        if pos.get("sell_date"):
            try:
                sell_dt = pd.Timestamp(pos["sell_date"])
            except ValueError:
                pass

        # Position-Wert für jeden Tag
        for dt in price_df.index:
            if dt >= buy_dt:
                if sell_dt is None or dt <= sell_dt:
                    price = price_df.loc[dt, ticker]
                    if not pd.isna(price):
                        portfolio_values[dt] += price * qty
                        cash_invested[dt] += buy_price * qty

    # Nur Tage mit Werten > 0
    mask = portfolio_values > 0
    if not mask.any():
        return None

    portfolio_values = portfolio_values[mask]
    cash_invested = cash_invested[mask]

    # Benchmark normalisieren auf gleichen Startwert
    if benchmark_ticker in price_df.columns:
        bm_series = price_df[benchmark_ticker][mask]
        initial_invest = cash_invested.iloc[0] if cash_invested.iloc[0] > 0 else 1
        bm_start = bm_series.iloc[0] if bm_series.iloc[0] > 0 else 1
        bm_normalized = bm_series / bm_start * initial_invest
    else:
        bm_normalized = pd.Series(np.nan, index=portfolio_values.index)

    result = pd.DataFrame({
        "Datum": portfolio_values.index,
        "Portfolio": portfolio_values.values,
        "Benchmark": bm_normalized.values,
        "Investiert": cash_invested.values,
    })
    result["Benchmark_Label"] = benchmark_label

    return result


# ---------------------------------------------------------------------------
# Performance-Metriken
# ---------------------------------------------------------------------------

def calc_performance_metrics(current_prices: dict[str, float] = None) -> PerformanceMetrics:
    """Berechnet alle Portfolio-Performance-Kennzahlen."""
    from watchlist import get_open_positions, get_closed_positions, calc_position_pnl

    if current_prices is None:
        current_prices = {}

    metrics = PerformanceMetrics()
    open_pos = get_open_positions()
    closed_pos = get_closed_positions()

    # Win-Rate (geschlossene Trades)
    if closed_pos:
        wins = 0
        total_gains = 0.0
        total_losses = 0.0
        best_pct = -999.0
        worst_pct = 999.0
        holding_days = []

        for cp in closed_pos:
            pos = cp["position"]
            pnl = calc_position_pnl(pos)

            if pnl["pnl_eur"] > 0:
                wins += 1
                total_gains += pnl["pnl_eur"]
            else:
                total_losses += abs(pnl["pnl_eur"])

            if pnl["pnl_pct"] > best_pct:
                best_pct = pnl["pnl_pct"]
            if pnl["pnl_pct"] < worst_pct:
                worst_pct = pnl["pnl_pct"]

            # Haltedauer
            try:
                bd = datetime.strptime(pos["buy_date"], "%Y-%m-%d")
                sd = datetime.strptime(pos["sell_date"], "%Y-%m-%d")
                holding_days.append((sd - bd).days)
            except (ValueError, KeyError):
                pass

        metrics.win_rate = round(wins / len(closed_pos) * 100, 1)
        metrics.best_trade_pct = round(best_pct, 2) if best_pct > -999 else 0.0
        metrics.worst_trade_pct = round(worst_pct, 2) if worst_pct < 999 else 0.0
        metrics.avg_holding_days = round(np.mean(holding_days), 1) if holding_days else 0.0
        metrics.profit_factor = round(total_gains / total_losses, 2) if total_losses > 0 else float("inf") if total_gains > 0 else 0.0

    # Equity-Kurve für Sharpe, Sortino, Max DD
    equity = calc_equity_curve(current_prices)
    if equity is not None and len(equity) > 10:
        portfolio_series = equity["Portfolio"].values

        # Tägliche Returns
        returns = np.diff(portfolio_series) / portfolio_series[:-1]
        returns = returns[np.isfinite(returns)]

        if len(returns) > 5:
            # Annualisierte Rendite
            total_return = (portfolio_series[-1] / portfolio_series[0]) - 1
            n_days = len(portfolio_series)
            ann_return = (1 + total_return) ** (252 / max(n_days, 1)) - 1
            metrics.total_return_pct = round(total_return * 100, 2)
            metrics.annualized_return_pct = round(ann_return * 100, 2)

            # Volatilität
            vol = np.std(returns) * np.sqrt(252)
            metrics.volatility_pct = round(vol * 100, 2)

            # Sharpe Ratio (Risk-free rate ~4% für aktuelle Phase)
            rf_daily = 0.04 / 252
            excess_returns = returns - rf_daily
            if np.std(excess_returns) > 0:
                metrics.sharpe_ratio = round(
                    np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252), 2)

            # Sortino Ratio (nur Downside-Volatilität)
            downside = returns[returns < 0]
            if len(downside) > 0 and np.std(downside) > 0:
                metrics.sortino_ratio = round(
                    (np.mean(returns) - rf_daily) / np.std(downside) * np.sqrt(252), 2)

            # Max Drawdown
            cummax = np.maximum.accumulate(portfolio_series)
            drawdowns = (portfolio_series - cummax) / cummax
            metrics.max_drawdown_pct = round(np.min(drawdowns) * 100, 2)
            metrics.max_drawdown_eur = round(
                np.min(portfolio_series - cummax), 2)

    return metrics


# ---------------------------------------------------------------------------
# Sektor-Allokation
# ---------------------------------------------------------------------------

def calc_sector_allocation(current_prices: dict[str, float] = None) -> list[dict]:
    """Berechnet die Sektor-Gewichtung des Portfolios.

    Returns:
        Liste von dicts [{sector, value, weight_pct, tickers}, ...]
    """
    from watchlist import get_open_positions

    if current_prices is None:
        current_prices = {}

    open_pos = get_open_positions()
    if not open_pos:
        return []

    sector_values = {}  # sector -> {value, tickers}

    for op in open_pos:
        ticker = op["ticker"]
        pos = op["position"]
        price = current_prices.get(ticker, pos.get("buy_price", 0))
        value = price * pos.get("quantity", 0)

        # Sektor von yfinance
        try:
            info = yf.Ticker(ticker).info
            sector = info.get("sector", "Sonstige")
        except Exception:
            sector = "Sonstige"

        if sector not in sector_values:
            sector_values[sector] = {"value": 0.0, "tickers": []}
        sector_values[sector]["value"] += value
        sector_values[sector]["tickers"].append(ticker)

    total = sum(s["value"] for s in sector_values.values())
    if total == 0:
        return []

    result = []
    for sector, data in sorted(sector_values.items(),
                                 key=lambda x: x[1]["value"], reverse=True):
        result.append({
            "sector": sector,
            "value": round(data["value"], 2),
            "weight_pct": round(data["value"] / total * 100, 1),
            "tickers": data["tickers"],
        })
    return result
