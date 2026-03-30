"""
services/options.py — Options Flow & Open Interest für das MacroDashboard.

Funktionalität:
- Options-Kette (Calls/Puts mit Strike, Volume, OI, IV)
- Put/Call-Ratio als Sentiment-Indikator
- Max Pain (Preismagnet an Verfallstagen)
- Implied Volatility vs. Historical Volatility
- Erkennung ungewöhnlicher Options-Aktivität

Datenquelle: yfinance (tk.options, tk.option_chain())
"""

import warnings
import pandas as pd
import numpy as np
import yfinance as yf
from dataclasses import dataclass, field
from datetime import datetime


# ---------------------------------------------------------------------------
# Datenmodelle
# ---------------------------------------------------------------------------

@dataclass
class OptionsOverview:
    """Zusammenfassung der Options-Analyse für einen Ticker."""
    ticker: str
    expiry_date: str              # Nächster Verfallstermin
    available_expiries: list[str] = field(default_factory=list)
    # Put/Call Ratio
    pc_ratio_volume: float | None = None    # Put-Vol / Call-Vol
    pc_ratio_oi: float | None = None        # Put-OI / Call-OI
    pc_sentiment: str = ""                   # "Bullish", "Bearish", "Neutral"
    pc_description: str = ""
    # Max Pain
    max_pain: float | None = None
    current_price: float | None = None
    max_pain_distance_pct: float | None = None
    # IV vs HV
    implied_vol: float | None = None         # Durchschn. ATM IV
    historical_vol: float | None = None      # Historische Volatilität (annualisiert)
    iv_hv_ratio: float | None = None
    iv_hv_signal: str = ""                   # "IV Premium", "IV Discount", "Fair"
    # Unusual Activity
    unusual_calls: list[dict] = field(default_factory=list)
    unusual_puts: list[dict] = field(default_factory=list)
    # Options Chain Data
    calls_df: pd.DataFrame | None = None
    puts_df: pd.DataFrame | None = None
    # Top-Strikes
    top_call_strikes: list[dict] = field(default_factory=list)
    top_put_strikes: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Options-Daten laden
# ---------------------------------------------------------------------------

def _get_options_data(ticker: str, expiry: str | None = None) -> tuple:
    """Lädt Options-Chain-Daten über yfinance.

    Returns:
        (calls_df, puts_df, expiry_used, all_expiries, current_price)
    """
    try:
        tk = yf.Ticker(ticker)

        # Alle verfügbaren Verfallstermine
        all_expiries = list(tk.options) if tk.options else []
        if not all_expiries:
            return None, None, None, [], None

        # Verfallstermin auswählen (nächster oder spezifizierter)
        if expiry and expiry in all_expiries:
            selected = expiry
        else:
            selected = all_expiries[0]  # Nächster Verfall

        # Options-Kette laden
        chain = tk.option_chain(selected)
        if chain is None:
            return None, None, None, all_expiries, None

        calls = chain.calls
        puts = chain.puts

        # Aktueller Kurs
        info = tk.info or {}
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if current_price is None:
            hist = tk.history(period="1d")
            if hist is not None and not hist.empty:
                current_price = float(hist["Close"].iloc[-1])

        return calls, puts, selected, all_expiries, current_price

    except Exception as exc:
        warnings.warn(f"_get_options_data({ticker}): {exc}")
        return None, None, None, [], None


# ---------------------------------------------------------------------------
# Put/Call Ratio
# ---------------------------------------------------------------------------

def _calc_put_call_ratio(calls: pd.DataFrame, puts: pd.DataFrame) -> dict:
    """Berechnet Put/Call Ratios (Volume und Open Interest)."""
    result = {
        "volume": None,
        "oi": None,
        "sentiment": "Neutral",
        "description": "",
    }

    try:
        call_vol = calls["volume"].sum() if "volume" in calls.columns else 0
        put_vol = puts["volume"].sum() if "volume" in puts.columns else 0
        call_oi = calls["openInterest"].sum() if "openInterest" in calls.columns else 0
        put_oi = puts["openInterest"].sum() if "openInterest" in puts.columns else 0

        if call_vol and call_vol > 0:
            result["volume"] = round(put_vol / call_vol, 3)

        if call_oi and call_oi > 0:
            result["oi"] = round(put_oi / call_oi, 3)

        # Sentiment bestimmen (basierend auf Volume-Ratio)
        ratio = result["volume"]
        if ratio is not None:
            if ratio > 1.2:
                result["sentiment"] = "Bearish"
                result["description"] = (
                    "Hohe Put-Aktivität — Marktteilnehmer sichern vermehrt ab "
                    "oder spekulieren auf fallende Kurse."
                )
            elif ratio < 0.7:
                result["sentiment"] = "Bullish"
                result["description"] = (
                    "Hohe Call-Aktivität — Marktteilnehmer setzen auf steigende Kurse "
                    "oder abgesicherte Positionen werden aufgelöst."
                )
            else:
                result["sentiment"] = "Neutral"
                result["description"] = (
                    "Ausgewogenes Put/Call-Verhältnis — kein klares Sentiment-Signal."
                )
        else:
            result["description"] = "Keine Volumendaten verfügbar."

    except Exception as exc:
        warnings.warn(f"_calc_put_call_ratio Error: {exc}")

    return result


# ---------------------------------------------------------------------------
# Max Pain Berechnung
# ---------------------------------------------------------------------------

def _calc_max_pain(calls: pd.DataFrame, puts: pd.DataFrame) -> float | None:
    """Berechnet den Max Pain Level — der Preis bei dem die meisten Optionen wertlos verfallen.

    An diesem Preis haben die Options-Verkäufer (Market Maker) den geringsten Verlust,
    weshalb der Kurs an Verfallstagen oft in Richtung Max Pain tendiert.
    """
    try:
        all_strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
        if not all_strikes:
            return None

        min_pain = float("inf")
        max_pain_strike = None

        for test_price in all_strikes:
            total_pain = 0.0

            # Schmerzen für Call-Halter
            for _, row in calls.iterrows():
                strike = row["strike"]
                oi = row.get("openInterest", 0) or 0
                if test_price > strike:
                    total_pain += (test_price - strike) * oi

            # Schmerzen für Put-Halter
            for _, row in puts.iterrows():
                strike = row["strike"]
                oi = row.get("openInterest", 0) or 0
                if test_price < strike:
                    total_pain += (strike - test_price) * oi

            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = test_price

        return max_pain_strike

    except Exception as exc:
        warnings.warn(f"_calc_max_pain Error: {exc}")
        return None


# ---------------------------------------------------------------------------
# IV vs HV
# ---------------------------------------------------------------------------

def _calc_iv_vs_hv(calls: pd.DataFrame, puts: pd.DataFrame,
                    current_price: float | None,
                    ticker: str) -> dict:
    """Vergleicht Implied Volatility (IV) mit Historical Volatility (HV)."""
    result = {
        "implied_vol": None,
        "historical_vol": None,
        "ratio": None,
        "signal": "",
    }

    try:
        # ATM IV (Calls + Puts nahe am aktuellen Kurs)
        if current_price and "impliedVolatility" in calls.columns:
            # ATM = Strike nahe am Kurs (±5%)
            atm_range = current_price * 0.05
            atm_calls = calls[
                (calls["strike"] >= current_price - atm_range) &
                (calls["strike"] <= current_price + atm_range)
            ]
            atm_puts = puts[
                (puts["strike"] >= current_price - atm_range) &
                (puts["strike"] <= current_price + atm_range)
            ]

            ivs = []
            if not atm_calls.empty and "impliedVolatility" in atm_calls.columns:
                ivs.extend(atm_calls["impliedVolatility"].dropna().tolist())
            if not atm_puts.empty and "impliedVolatility" in atm_puts.columns:
                ivs.extend(atm_puts["impliedVolatility"].dropna().tolist())

            if ivs:
                result["implied_vol"] = round(float(np.mean(ivs)) * 100, 1)

        # Historical Volatility (30-Tage annualisiert)
        tk = yf.Ticker(ticker)
        hist = tk.history(period="3mo")
        if hist is not None and len(hist) >= 20:
            returns = hist["Close"].pct_change().dropna()
            hv_30 = float(returns.tail(30).std() * np.sqrt(252)) * 100
            result["historical_vol"] = round(hv_30, 1)

        # IV/HV Ratio
        if result["implied_vol"] and result["historical_vol"] and result["historical_vol"] > 0:
            result["ratio"] = round(result["implied_vol"] / result["historical_vol"], 2)

            if result["ratio"] > 1.3:
                result["signal"] = "IV Premium"
            elif result["ratio"] < 0.8:
                result["signal"] = "IV Discount"
            else:
                result["signal"] = "Fair"

    except Exception as exc:
        warnings.warn(f"_calc_iv_vs_hv Error: {exc}")

    return result


# ---------------------------------------------------------------------------
# Unusual Activity Detection
# ---------------------------------------------------------------------------

def _detect_unusual_activity(df: pd.DataFrame, current_price: float | None,
                              option_type: str = "call") -> list[dict]:
    """Erkennt ungewöhnliche Options-Aktivität (große Volume-Spikes)."""
    unusual = []
    try:
        if "volume" not in df.columns or "openInterest" not in df.columns:
            return unusual

        df_clean = df.dropna(subset=["volume", "openInterest"])
        if df_clean.empty:
            return unusual

        # Kriterium 1: Volume > 5x Open Interest (Block-Trades)
        for _, row in df_clean.iterrows():
            vol = row.get("volume", 0) or 0
            oi = row.get("openInterest", 0) or 0
            strike = row.get("strike", 0)
            iv = row.get("impliedVolatility", None)

            if oi > 0 and vol > 5 * oi and vol >= 1000:
                unusual.append({
                    "strike": strike,
                    "volume": int(vol),
                    "open_interest": int(oi),
                    "vol_oi_ratio": round(vol / oi, 1) if oi > 0 else 0,
                    "iv": round(float(iv) * 100, 1) if iv and not pd.isna(iv) else None,
                    "type": option_type,
                    "distance_pct": round(((strike - current_price) / current_price) * 100, 1) if current_price else None,
                })

        # Top 5 nach Volume sortieren
        unusual.sort(key=lambda x: x["volume"], reverse=True)
        return unusual[:5]

    except Exception as exc:
        warnings.warn(f"_detect_unusual_activity Error: {exc}")
        return unusual


# ---------------------------------------------------------------------------
# Top-Strikes nach OI/Volume
# ---------------------------------------------------------------------------

def _get_top_strikes(df: pd.DataFrame, n: int = 5,
                      by: str = "openInterest") -> list[dict]:
    """Gibt die Top-N Strikes nach OI oder Volume zurück."""
    try:
        if by not in df.columns:
            return []

        top = df.nlargest(n, by)
        results = []
        for _, row in top.iterrows():
            results.append({
                "strike": row.get("strike", 0),
                "volume": int(row.get("volume", 0) or 0),
                "open_interest": int(row.get("openInterest", 0) or 0),
                "iv": round(float(row.get("impliedVolatility", 0) or 0) * 100, 1),
                "last_price": round(float(row.get("lastPrice", 0) or 0), 2),
            })
        return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def get_options_overview(ticker: str, expiry: str | None = None) -> OptionsOverview | None:
    """Erstellt eine vollständige Options-Analyse für einen Ticker.

    Args:
        ticker: Aktien-Symbol (z.B. "AAPL", "MSFT")
        expiry: Optional. Spezifischer Verfallstermin (Format: "YYYY-MM-DD")

    Returns:
        OptionsOverview mit allen Analysen, oder None bei Fehler.
    """
    try:
        calls, puts, expiry_used, all_expiries, current_price = _get_options_data(ticker, expiry)

        if calls is None or puts is None:
            return None

        # Put/Call Ratio
        pc = _calc_put_call_ratio(calls, puts)

        # Max Pain
        max_pain = _calc_max_pain(calls, puts)
        mp_dist = None
        if max_pain and current_price and current_price > 0:
            mp_dist = round(((max_pain - current_price) / current_price) * 100, 2)

        # IV vs HV
        iv_hv = _calc_iv_vs_hv(calls, puts, current_price, ticker)

        # Unusual Activity
        unusual_calls = _detect_unusual_activity(calls, current_price, "call")
        unusual_puts = _detect_unusual_activity(puts, current_price, "put")

        # Top Strikes
        top_calls = _get_top_strikes(calls, 5, "openInterest")
        top_puts = _get_top_strikes(puts, 5, "openInterest")

        return OptionsOverview(
            ticker=ticker,
            expiry_date=expiry_used or "",
            available_expiries=all_expiries,
            pc_ratio_volume=pc["volume"],
            pc_ratio_oi=pc["oi"],
            pc_sentiment=pc["sentiment"],
            pc_description=pc["description"],
            max_pain=max_pain,
            current_price=current_price,
            max_pain_distance_pct=mp_dist,
            implied_vol=iv_hv["implied_vol"],
            historical_vol=iv_hv["historical_vol"],
            iv_hv_ratio=iv_hv["ratio"],
            iv_hv_signal=iv_hv["signal"],
            unusual_calls=unusual_calls,
            unusual_puts=unusual_puts,
            calls_df=calls,
            puts_df=puts,
            top_call_strikes=top_calls,
            top_put_strikes=top_puts,
        )

    except Exception as exc:
        warnings.warn(f"get_options_overview({ticker}): {exc}")
        return None
