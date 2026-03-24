
#fundamental.py — Fundamentale Analyse-Funktionen.
#Enthält: DCF, Bilanzqualität, Margen-Trends, Peer-Vergleich,Dividendenanalyse, Insider/Institutionelle, Analysten-Konsens.
import warnings
import pandas as pd
import numpy as np
import yfinance as yf

# ---------------------------------------------------------------------------
# Dynamische Risk-Free Rate (Live Treasury Yield)
# ---------------------------------------------------------------------------

_cached_risk_free = {"value": None, "timestamp": 0}

def _get_live_risk_free_rate(fallback: float = 0.03) -> float:
    """Zieht den aktuellen 10Y US-Treasury Yield als Risk-Free Rate.
    
    Cached den Wert für 1 Stunde, um API-Calls zu minimieren.
    Fallback: 3 % bei Fehler oder fehlenden Daten.
    """
    import time
    now = time.time()
    if _cached_risk_free["value"] is not None and (now - _cached_risk_free["timestamp"]) < 3600:
        return _cached_risk_free["value"]
    try:
        tnx = yf.Ticker("^TNX").history(period="5d")
        if tnx is not None and not tnx.empty:
            rate = float(tnx["Close"].iloc[-1]) / 100  # z.B. 4.5 → 0.045
            rate = max(0.005, min(rate, 0.12))  # Clamp: 0.5% – 12%
            _cached_risk_free["value"] = rate
            _cached_risk_free["timestamp"] = now
            return rate
    except Exception as exc:
        warnings.warn(f"_get_live_risk_free_rate: {exc}")
    return fallback

# ---------------------------------------------------------------------------
# DCF Fair Value Berechnung
# ---------------------------------------------------------------------------

def calc_dcf_valuation(info: dict) -> dict | None:
    try:
        fcf = info.get("freeCashflow")
        shares = info.get("sharesOutstanding")
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        rev_growth = info.get("revenueGrowth", 0.0) or 0.0
        beta = info.get("beta", 1.0) or 1.0
        total_debt = info.get("totalDebt", 0) or 0
        total_cash = info.get("totalCash", 0) or 0

        if not fcf or not shares or fcf <= 0 or shares <= 0:
            return None

        risk_free = _get_live_risk_free_rate()
        erp = 0.055
        cost_of_equity = risk_free + beta * erp
        wacc = 0.7 * cost_of_equity + 0.3 * 0.04 * 0.75
        wacc = max(wacc, 0.06)

        growth = min(max(rev_growth, -0.05), 0.25)
        terminal_growth = 0.025

        projected_fcfs = []
        current_fcf = float(fcf)
        for year in range(1, 6):
            year_growth = growth * (1 - (year - 1) * 0.15)
            current_fcf *= (1 + year_growth)
            discounted = current_fcf / ((1 + wacc) ** year)
            projected_fcfs.append(discounted)

        terminal_fcf = current_fcf * (1 + terminal_growth)
        terminal_value = terminal_fcf / (wacc - terminal_growth)
        discounted_terminal = terminal_value / ((1 + wacc) ** 5)

        dcf_ev = sum(projected_fcfs) + discounted_terminal
        equity_value = dcf_ev - total_debt + total_cash
        fair_value_per_share = equity_value / shares

        upside_pct = ((fair_value_per_share - current_price) / current_price) * 100 if current_price and current_price > 0 else 0.0
        margin_of_safety = fair_value_per_share > current_price * 1.2 if current_price else False

        return {
            "fair_value": round(fair_value_per_share, 2),
            "current_price": round(current_price, 2) if current_price else 0,
            "upside_pct": round(upside_pct, 1),
            "margin_of_safety": margin_of_safety,
            "wacc": round(wacc * 100, 1),
            "growth_used": round(growth * 100, 1),
            "fcf": fcf,
            "dcf_ev": round(dcf_ev, 0),
        }
    except Exception as exc:
        warnings.warn(f"calc_dcf_valuation: {exc}")
        return None


# ---------------------------------------------------------------------------
# Bilanzqualität & Verschuldung
# ---------------------------------------------------------------------------

def calc_balance_sheet_quality(info: dict) -> dict | None:
    """Bewertet die Bilanzqualität anhand von Verschuldungs-Kennzahlen."""
    try:
        debt_to_equity = info.get("debtToEquity")
        current_ratio = info.get("currentRatio")
        quick_ratio = info.get("quickRatio")
        total_debt = info.get("totalDebt", 0) or 0
        total_cash = info.get("totalCash", 0) or 0
        ebitda = info.get("ebitda")

        net_debt = total_debt - total_cash
        net_debt_ebitda = (net_debt / ebitda) if ebitda and ebitda > 0 else None

        warnings_list = []
        score = 0

        if debt_to_equity is not None:
            if debt_to_equity < 50:
                score += 1
            elif debt_to_equity > 150:
                score -= 1
                warnings_list.append("Hohe Verschuldung (D/E > 150%)")

        if current_ratio is not None:
            if current_ratio > 1.5:
                score += 1
            elif current_ratio < 1.0:
                score -= 1
                warnings_list.append("Kurzfristige Liquidität kritisch (CR < 1.0)")

        if net_debt_ebitda is not None:
            if net_debt_ebitda < 2.0:
                score += 1
            elif net_debt_ebitda > 4.0:
                score -= 1
                warnings_list.append(f"Hohe Nettoverschuldung ({net_debt_ebitda:.1f}x EBITDA)")

        if score >= 2:
            label = "Solide 🟢"
        elif score >= 0:
            label = "Akzeptabel 🟡"
        else:
            label = "Kritisch 🔴"

        return {
            "debt_to_equity": round(debt_to_equity, 1) if debt_to_equity else None,
            "current_ratio": round(current_ratio, 2) if current_ratio else None,
            "quick_ratio": round(quick_ratio, 2) if quick_ratio else None,
            "total_debt": total_debt,
            "total_cash": total_cash,
            "net_debt": net_debt,
            "net_debt_ebitda": round(net_debt_ebitda, 1) if net_debt_ebitda else None,
            "label": label,
            "score": score,
            "warnings": warnings_list,
        }
    except Exception as exc:
        warnings.warn(f"calc_balance_sheet_quality: {exc}")
        return None


# ---------------------------------------------------------------------------
# Margen- & Cashflow-Trends (Multi-Year)
# ---------------------------------------------------------------------------

def get_margin_trends(ticker: str) -> list[dict] | None:
    """Extrahiert Margen und Cashflow über mehrere Jahre."""
    try:
        tk = yf.Ticker(ticker)
        fin = tk.financials
        cf = tk.cashflow

        if fin is None or fin.empty:
            return None

        years = sorted(fin.columns)
        records = []

        for yr in years:
            yr_data = fin[yr]
            revenue = yr_data.get("Total Revenue")
            gross_profit = yr_data.get("Gross Profit")
            ebitda_val = yr_data.get("EBITDA")
            net_income = yr_data.get("Net Income")

            gross_margin = (gross_profit / revenue * 100) if revenue and gross_profit and revenue != 0 else None
            ebitda_margin = (ebitda_val / revenue * 100) if revenue and ebitda_val and revenue != 0 else None
            net_margin = (net_income / revenue * 100) if revenue and net_income and revenue != 0 else None

            fcf = None
            if cf is not None and not cf.empty and yr in cf.columns:
                cf_data = cf[yr]
                op_cf = cf_data.get("Operating Cash Flow") or cf_data.get("Total Cash From Operating Activities")
                capex = cf_data.get("Capital Expenditure") or cf_data.get("Capital Expenditures")
                if op_cf is not None and capex is not None and not pd.isna(op_cf) and not pd.isna(capex):
                    fcf = float(op_cf) + float(capex)

            records.append({
                "year": yr.year if hasattr(yr, "year") else str(yr)[:4],
                "revenue": float(revenue) if revenue and not pd.isna(revenue) else None,
                "gross_margin": round(float(gross_margin), 1) if gross_margin and not pd.isna(gross_margin) else None,
                "ebitda_margin": round(float(ebitda_margin), 1) if ebitda_margin and not pd.isna(ebitda_margin) else None,
                "net_margin": round(float(net_margin), 1) if net_margin and not pd.isna(net_margin) else None,
                "fcf": round(fcf, 0) if fcf else None,
            })

        return records if records else None
    except Exception as exc:
        warnings.warn(f"get_margin_trends({ticker}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Peer-Vergleich (Sektor)
# ---------------------------------------------------------------------------

def get_sector_peers(ticker: str, sector: str, industry: str, max_peers: int = 5) -> pd.DataFrame | None:
    """Findet Peers im gleichen Sektor und vergleicht Kennzahlen."""
    try:
        from services.market_data import get_sp500_components
        sp500 = get_sp500_components()
        if sp500 is None or sp500.empty:
            return None

        peers_df = pd.DataFrame()
        if industry:
            peers_df = sp500[sp500["GICS Sub-Industry"].str.contains(industry, case=False, na=False)]
        if peers_df.empty and sector:
            peers_df = sp500[sp500["GICS Sector"].str.contains(sector, case=False, na=False)]

        if peers_df.empty:
            return None

        peer_tickers = [t for t in peers_df["Symbol"].tolist() if t.upper() != ticker.upper()][:max_peers]
        all_tickers = [ticker] + peer_tickers

        records = []
        for t in all_tickers:
            try:
                tk_peer = yf.Ticker(t)
                pinfo = tk_peer.info or {}
                records.append({
                    "Ticker": t,
                    "Name": (pinfo.get("shortName", t) or t)[:25],
                    "KGV": round(pinfo.get("trailingPE", 0) or 0, 1),
                    "EV/EBITDA": round(pinfo.get("enterpriseToEbitda", 0) or 0, 1),
                    "Marge (%)": round((pinfo.get("profitMargins", 0) or 0) * 100, 1),
                    "Wachstum (%)": round((pinfo.get("revenueGrowth", 0) or 0) * 100, 1),
                    "Div. Rendite (%)": round((pinfo.get("dividendYield", 0) or 0) * 100, 2),
                })
            except Exception:
                continue

        if not records:
            return None
        return pd.DataFrame(records)
    except Exception as exc:
        warnings.warn(f"get_sector_peers({ticker}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Dividendenanalyse
# ---------------------------------------------------------------------------

def calc_dividend_analysis(ticker: str) -> dict | None:
    """Analysiert die Dividendenhistorie einer Aktie."""
    try:
        tk = yf.Ticker(ticker)
        dividends = tk.dividends
        info = tk.info or {}

        current_yield = info.get("dividendYield", 0) or 0
        payout_ratio = info.get("payoutRatio", 0) or 0

        if dividends is None or dividends.empty:
            return {
                "has_dividends": False,
                "current_yield": round(current_yield * 100, 2) if current_yield < 1 else round(current_yield, 2),
                "payout_ratio": round(payout_ratio * 100, 1) if payout_ratio < 1 else round(payout_ratio, 1),
                "annual_dividends": [],
                "growth_rate": None,
                "streak": 0,
            }

        annual = dividends.groupby(dividends.index.year).sum()
        annual_records = [{"year": int(yr), "amount": round(float(val), 4)} for yr, val in annual.items()]

        streak = 0
        values = list(annual.values)
        if len(values) >= 2:
            for i in range(len(values) - 1, 0, -1):
                if values[i] >= values[i - 1]:
                    streak += 1
                else:
                    break

        growth_rate = None
        if len(values) >= 3 and values[0] > 0:
            years_span = len(values) - 1
            growth_rate = ((values[-1] / values[0]) ** (1 / years_span) - 1) * 100

        return {
            "has_dividends": True,
            "current_yield": round(current_yield * 100, 2) if current_yield < 1 else round(current_yield, 2),
            "payout_ratio": round(payout_ratio * 100, 1) if payout_ratio < 1 else round(payout_ratio, 1),
            "annual_dividends": annual_records,
            "growth_rate": round(growth_rate, 1) if growth_rate else None,
            "streak": streak,
        }
    except Exception as exc:
        warnings.warn(f"calc_dividend_analysis({ticker}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Insider-Transaktionen & Institutionelle Halter
# ---------------------------------------------------------------------------

def get_insider_institutional(ticker: str) -> dict | None:
    """Lädt Insider-Transaktionen und Top institutionelle Halter."""
    try:
        tk = yf.Ticker(ticker)

        insider_df = None
        try:
            ins = tk.insider_transactions
            if ins is not None and not ins.empty:
                insider_df = ins.head(10)
        except Exception:
            pass

        institutional_df = None
        try:
            inst = tk.institutional_holders
            if inst is not None and not inst.empty:
                institutional_df = inst.head(5)
        except Exception:
            pass

        net_buys, net_sells = 0, 0
        if insider_df is not None and not insider_df.empty:
            for _, row in insider_df.iterrows():
                transaction = str(row.get("Transaction", "") or row.get("Text", "")).lower()
                if "purchase" in transaction or "buy" in transaction or "acquisition" in transaction:
                    net_buys += 1
                elif "sale" in transaction or "sell" in transaction:
                    net_sells += 1

        return {
            "insider_df": insider_df,
            "institutional_df": institutional_df,
            "net_buys": net_buys,
            "net_sells": net_sells,
            "has_insider_data": insider_df is not None and not insider_df.empty,
            "has_institutional_data": institutional_df is not None and not institutional_df.empty,
        }
    except Exception as exc:
        warnings.warn(f"get_insider_institutional({ticker}): {exc}")
        return None


# ---------------------------------------------------------------------------
# Analysten-Konsens
# ---------------------------------------------------------------------------

def get_analyst_consensus(ticker: str) -> dict | None:
    """Lädt Analysten-Kursziele und Empfehlungen."""
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}

        target_low = info.get("targetLowPrice")
        target_mean = info.get("targetMeanPrice")
        target_high = info.get("targetHighPrice")
        target_median = info.get("targetMedianPrice")
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        num_analysts = info.get("numberOfAnalystOpinions")
        recommendation = info.get("recommendationKey", "—")
        recommendation_mean = info.get("recommendationMean")

        upside_pct = None
        if target_mean and current_price and current_price > 0:
            upside_pct = ((target_mean - current_price) / current_price) * 100

        recs_df = None
        try:
            recs = tk.recommendations
            if recs is not None and not recs.empty:
                recs_df = recs.tail(1)
        except Exception:
            pass

        return {
            "target_low": round(target_low, 2) if target_low else None,
            "target_mean": round(target_mean, 2) if target_mean else None,
            "target_high": round(target_high, 2) if target_high else None,
            "target_median": round(target_median, 2) if target_median else None,
            "current_price": round(current_price, 2) if current_price else None,
            "upside_pct": round(upside_pct, 1) if upside_pct else None,
            "num_analysts": num_analysts,
            "recommendation": recommendation,
            "recommendation_mean": round(recommendation_mean, 1) if recommendation_mean else None,
            "recs_df": recs_df,
        }
    except Exception as exc:
        warnings.warn(f"get_analyst_consensus({ticker}): {exc}")
        return None
