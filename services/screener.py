"""
services/screener.py — Aktien-Screener für das MacroDashboard.

Scannt S&P 500 Aktien per Batch-Download und bewertet sie mit
der Quick-Score-Engine (nur OHLCV, kein API-Call pro Ticker).

Funktionalität:
- Batch-Download der S&P 500 Kursdaten (yf.download)
- Quick-Score pro Ticker (Trend, Volume, Oszillatoren)
- Vordefinierte Filter-Presets
- Caching (15 Min über Streamlit)
"""

import warnings
import pandas as pd
import numpy as np
import yfinance as yf

from services.scoring import calc_quick_score


# ---------------------------------------------------------------------------
# S&P 500 Ticker-Liste
# ---------------------------------------------------------------------------

def get_sp500_tickers() -> pd.DataFrame | None:
    """Lädt S&P 500 Komponenten von Wikipedia.

    Rückgabe: DataFrame mit [Symbol, Security, GICS Sector, GICS Sub-Industry]
    """
    try:
        import requests
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(url, headers=headers, timeout=15).text
        tables = pd.read_html(html)
        df = tables[0]
        # Symbole in yfinance-Format (BRK.B → BRK-B)
        df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
        return df[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]]
    except Exception as exc:
        warnings.warn(f"get_sp500_tickers: {exc}")
        return None


# ---------------------------------------------------------------------------
# Vordefinierte Screener-Presets
# ---------------------------------------------------------------------------

PRESETS = {
    "all": {
        "name": "🔍 Alle scannen",
        "description": "Alle S&P 500 Aktien bewerten und nach Score sortieren.",
        "filters": {},
    },
    "oversold_quality": {
        "name": "📉 Überverkaufte Qualitätsaktien",
        "description": "RSI < 35, bullischer Trend (Kurs > SMA 200) — Rebound-Kandidaten.",
        "filters": {
            "rsi_max": 35,
            "trend_bullish": True,
        },
    },
    "momentum": {
        "name": "🚀 Momentum Leaders",
        "description": "Score > 65, starker Aufwärtstrend — Momentum-Aktien.",
        "filters": {
            "score_min": 65,
        },
    },
    "bearish": {
        "name": "🐻 Bearish Signals",
        "description": "Score < 35, überverkaufte Aktien mit schwachem Trend.",
        "filters": {
            "score_max": 35,
        },
    },
    "volume_accumulation": {
        "name": "📊 Akkumulation (Volume)",
        "description": "Bullisches OBV + Kurs über VWAP — institutioneller Kaufdruck.",
        "filters": {
            "obv_bullish": True,
            "vwap_bullish": True,
        },
    },
}


# ---------------------------------------------------------------------------
# Batch-Scoring
# ---------------------------------------------------------------------------

def _extract_single_ticker_hist(data: pd.DataFrame, ticker: str,
                                all_tickers: list[str]) -> pd.DataFrame | None:
    """Extrahiert OHLCV-Daten für einen einzelnen Ticker aus Batch-Download.

    yfinance liefert bei Multi-Ticker-Download MultiIndex-Columns
    (Level 0 = Price, Level 1 = Ticker). Bei einem einzigen Ticker
    gibt es einfache Columns.
    """
    try:
        if isinstance(data.columns, pd.MultiIndex):
            # Multi-Ticker: (Close, AAPL), (Open, AAPL), ...
            if ticker not in data.columns.get_level_values(1):
                return None
            sub = data.xs(ticker, level=1, axis=1)
        else:
            # Nur 1 Ticker im Batch → einfache Columns
            sub = data

        if sub is None or sub.empty:
            return None

        # Sicherstellen dass OHLCV vorhanden
        required = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in sub.columns for c in required):
            return None

        sub = sub[required].dropna()
        if len(sub) < 50:
            return None

        return sub

    except Exception:
        return None


def scan_batch(tickers: list[str], sp500_info: pd.DataFrame | None = None,
               filters: dict | None = None,
               progress_callback=None) -> list[dict]:
    """Scannt eine Liste von Tickern und gibt bewertete Ergebnisse zurück.

    Args:
        tickers: Liste von Ticker-Symbolen
        sp500_info: S&P 500 DataFrame mit Symbol/Security/Sector
        filters: Dict mit Filterkriterien (s. _apply_filters)
        progress_callback: Optional. Callable(progress: float, status: str)
                          für Streamlit-Progress-Bar.

    Returns: Liste von Dicts, sortiert nach Score (höchste zuerst)
    """
    filters = filters or {}
    results = []

    # Info-Lookup erstellen
    info_map = {}
    if sp500_info is not None:
        for _, row in sp500_info.iterrows():
            info_map[row["Symbol"]] = {
                "name": row.get("Security", ""),
                "sector": row.get("GICS Sector", ""),
                "sub_industry": row.get("GICS Sub-Industry", ""),
            }

    # In Chunks aufteilen um API-Limits zu vermeiden
    chunk_size = 50
    chunks = [tickers[i:i + chunk_size]
              for i in range(0, len(tickers), chunk_size)]

    processed = 0
    total = len(tickers)

    for chunk_idx, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(
                processed / total,
                f"Lade Chunk {chunk_idx + 1}/{len(chunks)} "
                f"({len(chunk)} Ticker)..."
            )

        # Batch-Download: 1 Jahr OHLCV für alle Ticker im Chunk
        try:
            data = yf.download(
                chunk,
                period="1y",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if data is None or data.empty:
                processed += len(chunk)
                continue
        except Exception as exc:
            warnings.warn(f"Batch-Download Chunk {chunk_idx}: {exc}")
            processed += len(chunk)
            continue

        # Quick-Score für jeden Ticker berechnen
        for ticker in chunk:
            processed += 1
            if progress_callback and processed % 10 == 0:
                progress_callback(
                    processed / total,
                    f"Scoring {processed}/{total}: {ticker}..."
                )

            hist = _extract_single_ticker_hist(data, ticker, chunk)
            if hist is None:
                continue

            try:
                score_result = calc_quick_score(hist)
                if score_result is None:
                    continue

                info = info_map.get(ticker, {})
                current_price = float(hist["Close"].iloc[-1])

                entry = {
                    "ticker": ticker,
                    "name": info.get("name", ""),
                    "sector": info.get("sector", ""),
                    "sub_industry": info.get("sub_industry", ""),
                    "confidence": score_result.confidence,
                    "score_label": score_result.score_label,
                    "confidence_label": score_result.confidence_label,
                    "price": round(current_price, 2),
                    # Einzelsignale für Filter
                    "rsi": score_result.signals.get("rsi_val"),
                    "trend_bullish": score_result.signals.get("trend_macro_bullish", False),
                    "macd_bullish": score_result.signals.get("macd_bullish", False),
                    "obv_bullish": score_result.signals.get("obv_bullish", False),
                    "vwap_bullish": score_result.signals.get("vwap_bullish", False),
                    "adx_strong": score_result.signals.get("adx_strong", False),
                    "adx_val": score_result.signals.get("adx_val"),
                    "sma200": score_result.signals.get("sma200_val"),
                }

                # Filter anwenden
                if _passes_filters(entry, filters):
                    results.append(entry)

            except Exception:
                continue

    if progress_callback:
        progress_callback(1.0, f"Fertig — {len(results)} Ergebnisse")

    # Nach Confidence sortieren (höchste zuerst)
    results.sort(key=lambda r: r["confidence"], reverse=True)

    return results


# ---------------------------------------------------------------------------
# Filter-Logik
# ---------------------------------------------------------------------------

def _passes_filters(entry: dict, filters: dict) -> bool:
    """Prüft ob ein Eintrag alle aktiven Filter besteht."""
    if not filters:
        return True

    # Score-Filter
    score_min = filters.get("score_min")
    if score_min is not None and entry["confidence"] < score_min:
        return False

    score_max = filters.get("score_max")
    if score_max is not None and entry["confidence"] > score_max:
        return False

    # RSI-Filter
    rsi = entry.get("rsi")

    rsi_max = filters.get("rsi_max")
    if rsi_max is not None:
        if rsi is None or rsi > rsi_max:
            return False

    rsi_min = filters.get("rsi_min")
    if rsi_min is not None:
        if rsi is None or rsi < rsi_min:
            return False

    # Trend-Filter
    if filters.get("trend_bullish") and not entry.get("trend_bullish"):
        return False

    if filters.get("trend_bearish") and entry.get("trend_bullish"):
        return False

    # Volume-Filter
    if filters.get("obv_bullish") and not entry.get("obv_bullish"):
        return False

    if filters.get("vwap_bullish") and not entry.get("vwap_bullish"):
        return False

    # Sektor-Filter
    sector = filters.get("sector")
    if sector and entry.get("sector") != sector:
        return False

    return True


# ---------------------------------------------------------------------------
# Convenience: Voller S&P 500 Scan
# ---------------------------------------------------------------------------

def scan_sp500(preset: str = "all",
               custom_filters: dict | None = None,
               progress_callback=None) -> list[dict]:
    """Scannt alle S&P 500 Aktien mit einem vordefinierten Preset.

    Args:
        preset: Schlüssel aus PRESETS ("all", "oversold_quality", "momentum", ...)
        custom_filters: Überschreibt/ergänzt die Preset-Filter
        progress_callback: Callable(progress, status) für UI-Updates

    Returns: Sortierte Liste von Screener-Ergebnissen
    """
    # S&P 500 Liste holen
    sp500_df = get_sp500_tickers()
    if sp500_df is None or sp500_df.empty:
        return []

    tickers = sp500_df["Symbol"].tolist()

    # Preset-Filter anwenden
    preset_config = PRESETS.get(preset, PRESETS["all"])
    filters = dict(preset_config.get("filters", {}))

    # Custom-Filter ergänzen/überschreiben
    if custom_filters:
        filters.update(custom_filters)

    return scan_batch(
        tickers=tickers,
        sp500_info=sp500_df,
        filters=filters,
        progress_callback=progress_callback,
    )
