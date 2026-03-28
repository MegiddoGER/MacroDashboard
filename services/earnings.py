"""
services/earnings.py — Earnings Surprise Tracking für das MacroDashboard.

Funktionalität:
- EPS Actual vs. Estimate pro Quartal (via yfinance)
- Earnings Surprise: Beat/Miss/Inline + Magnitude
- Post-Earnings Drift: Kursreaktion 1/5/20 Tage nach Earnings

Datenquellen:
- yfinance: tk.earnings_dates, tk.earnings_history
- Historische Kursdaten für Drift-Berechnung
"""

import warnings
import pandas as pd
import numpy as np
import yfinance as yf
from dataclasses import dataclass, field
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Datenmodelle
# ---------------------------------------------------------------------------

@dataclass
class EarningsSurprise:
    """Ein einzelnes Earnings-Event mit Surprise und Drift."""
    date: datetime
    quarter: str                  # z.B. "Q1 2024"
    eps_actual: float | None
    eps_estimate: float | None
    surprise_pct: float | None    # (actual - estimate) / |estimate| * 100
    result: str                   # "Beat", "Miss", "Inline"
    revenue_actual: float | None  # optional
    revenue_estimate: float | None
    # Post-Earnings Drift (Kursänderung in %)
    drift_1d: float | None
    drift_5d: float | None
    drift_20d: float | None
    price_at_earnings: float | None


@dataclass
class EarningsProfile:
    """Gesamtprofil der Earnings-Historie eines Tickers."""
    ticker: str
    events: list[EarningsSurprise] = field(default_factory=list)
    # Aggregierte Statistiken
    total_quarters: int = 0
    beats: int = 0
    misses: int = 0
    inlines: int = 0
    beat_rate: float = 0.0        # % der Quarters mit Beat
    avg_surprise_pct: float = 0.0
    avg_drift_1d: float | None = None
    avg_drift_5d: float | None = None
    avg_drift_20d: float | None = None
    avg_beat_drift_1d: float | None = None   # Ø Drift nach Beats
    avg_miss_drift_1d: float | None = None   # Ø Drift nach Misses
    next_earnings_date: datetime | None = None


# ---------------------------------------------------------------------------
# Daten laden: EPS History
# ---------------------------------------------------------------------------

def _get_earnings_from_yfinance(ticker: str) -> list[dict]:
    """Lädt Earnings-Daten über yfinance earnings_dates (zuverlässigste Quelle)."""
    try:
        tk = yf.Ticker(ticker)

        # earnings_dates liefert: Datum, EPS Estimate, Reported EPS, Surprise (%)
        ed = tk.earnings_dates
        if ed is None or ed.empty:
            return []

        records = []
        for idx, row in ed.iterrows():
            date = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
            # Nur abgeschlossene Quarters (mit Reported EPS)
            eps_actual = row.get("Reported EPS")
            eps_estimate = row.get("EPS Estimate")
            surprise_pct = row.get("Surprise(%)")

            if pd.isna(eps_actual):
                continue  # Zukunft oder fehlend

            records.append({
                "date": date,
                "eps_actual": float(eps_actual) if not pd.isna(eps_actual) else None,
                "eps_estimate": float(eps_estimate) if not pd.isna(eps_estimate) else None,
                "surprise_pct": float(surprise_pct) if not pd.isna(surprise_pct) else None,
            })

        return records
    except Exception as exc:
        warnings.warn(f"_get_earnings_from_yfinance({ticker}): {exc}")
        return []


# ---------------------------------------------------------------------------
# Post-Earnings Drift berechnen
# ---------------------------------------------------------------------------

def _calc_drift(hist: pd.DataFrame, earnings_date: datetime,
                days: int) -> float | None:
    """Berechnet die Kursänderung N Tage nach einem Earnings-Event.

    Returns: Kursänderung in Prozent oder None wenn Daten fehlen.
    """
    try:
        # Index auf Datum ohne Zeitzone normalisieren
        if hist.index.tz is not None:
            idx = hist.index.tz_localize(None)
        else:
            idx = hist.index

        ed = pd.Timestamp(earnings_date).tz_localize(None)

        # Nächster Handelstag nach/am Earnings-Datum finden
        mask_after = idx >= ed
        if not mask_after.any():
            return None

        start_idx = mask_after.argmax()
        end_idx = min(start_idx + days, len(hist) - 1)

        if start_idx >= len(hist) or end_idx >= len(hist):
            return None

        price_start = float(hist["Close"].iloc[start_idx])
        price_end = float(hist["Close"].iloc[end_idx])

        if price_start == 0:
            return None

        return round(((price_end - price_start) / price_start) * 100, 2)
    except Exception:
        return None


def _get_price_at_date(hist: pd.DataFrame, date: datetime) -> float | None:
    """Holt den Schlusskurs am/nahe einem Datum."""
    try:
        if hist.index.tz is not None:
            idx = hist.index.tz_localize(None)
        else:
            idx = hist.index

        ed = pd.Timestamp(date).tz_localize(None)
        mask = idx >= ed
        if not mask.any():
            return None

        pos = mask.argmax()
        return round(float(hist["Close"].iloc[pos]), 2)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def get_earnings_history(ticker: str) -> EarningsProfile | None:
    """Lädt die vollständige Earnings-Historie inkl. Post-Earnings-Drift.

    Args:
        ticker: Aktien-Symbol (z.B. "AAPL", "MSFT")

    Returns:
        EarningsProfile mit allen Events und aggregierten Statistiken,
        oder None bei Fehler.
    """
    try:
        # 1. EPS-Daten laden
        raw_earnings = _get_earnings_from_yfinance(ticker)
        if not raw_earnings:
            return None

        # 2. Historische Kursdaten für Drift-Berechnung (5 Jahre)
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5y")
        if hist is None or hist.empty:
            hist = pd.DataFrame()

        # 3. Nächstes Earnings-Datum ermitteln
        next_earnings = None
        try:
            ed = tk.earnings_dates
            if ed is not None and not ed.empty:
                for idx, row in ed.iterrows():
                    if pd.isna(row.get("Reported EPS")):
                        next_earnings = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else idx
                        break
        except Exception:
            pass

        # 4. Events erstellen
        events = []
        for r in raw_earnings:
            date = r["date"]
            eps_actual = r["eps_actual"]
            eps_estimate = r["eps_estimate"]
            surprise_pct = r["surprise_pct"]

            # Surprise berechnen falls nicht vorhanden
            if surprise_pct is None and eps_actual is not None and eps_estimate is not None:
                if eps_estimate != 0:
                    surprise_pct = round(
                        ((eps_actual - eps_estimate) / abs(eps_estimate)) * 100, 2
                    )

            # Result bestimmen
            if surprise_pct is not None:
                if surprise_pct > 2:
                    result = "Beat"
                elif surprise_pct < -2:
                    result = "Miss"
                else:
                    result = "Inline"
            elif eps_actual is not None and eps_estimate is not None:
                if eps_actual > eps_estimate * 1.02:
                    result = "Beat"
                elif eps_actual < eps_estimate * 0.98:
                    result = "Miss"
                else:
                    result = "Inline"
            else:
                result = "Inline"

            # Quarter-Label ableiten
            if hasattr(date, 'month'):
                q = (date.month - 1) // 3 + 1
                quarter = f"Q{q} {date.year}"
            else:
                quarter = str(date)[:10]

            # Drift berechnen
            drift_1d = None
            drift_5d = None
            drift_20d = None
            price_at = None

            if not hist.empty:
                drift_1d = _calc_drift(hist, date, 1)
                drift_5d = _calc_drift(hist, date, 5)
                drift_20d = _calc_drift(hist, date, 20)
                price_at = _get_price_at_date(hist, date)

            events.append(EarningsSurprise(
                date=date,
                quarter=quarter,
                eps_actual=eps_actual,
                eps_estimate=eps_estimate,
                surprise_pct=surprise_pct,
                result=result,
                revenue_actual=None,
                revenue_estimate=None,
                drift_1d=drift_1d,
                drift_5d=drift_5d,
                drift_20d=drift_20d,
                price_at_earnings=price_at,
            ))

        # Nach Datum sortieren (neueste zuerst)
        events.sort(key=lambda e: e.date, reverse=True)

        # 5. Aggregierte Statistiken berechnen
        total = len(events)
        beats = sum(1 for e in events if e.result == "Beat")
        misses = sum(1 for e in events if e.result == "Miss")
        inlines = total - beats - misses
        beat_rate = round((beats / total) * 100, 1) if total > 0 else 0.0

        surprises = [e.surprise_pct for e in events if e.surprise_pct is not None]
        avg_surprise = round(np.mean(surprises), 2) if surprises else 0.0

        # Drift-Durchschnitte
        drifts_1d = [e.drift_1d for e in events if e.drift_1d is not None]
        drifts_5d = [e.drift_5d for e in events if e.drift_5d is not None]
        drifts_20d = [e.drift_20d for e in events if e.drift_20d is not None]

        avg_d1 = round(np.mean(drifts_1d), 2) if drifts_1d else None
        avg_d5 = round(np.mean(drifts_5d), 2) if drifts_5d else None
        avg_d20 = round(np.mean(drifts_20d), 2) if drifts_20d else None

        # Drift nach Beats vs. Misses
        beat_drifts_1d = [e.drift_1d for e in events
                         if e.result == "Beat" and e.drift_1d is not None]
        miss_drifts_1d = [e.drift_1d for e in events
                         if e.result == "Miss" and e.drift_1d is not None]

        avg_beat_d1 = round(np.mean(beat_drifts_1d), 2) if beat_drifts_1d else None
        avg_miss_d1 = round(np.mean(miss_drifts_1d), 2) if miss_drifts_1d else None

        return EarningsProfile(
            ticker=ticker,
            events=events,
            total_quarters=total,
            beats=beats,
            misses=misses,
            inlines=inlines,
            beat_rate=beat_rate,
            avg_surprise_pct=avg_surprise,
            avg_drift_1d=avg_d1,
            avg_drift_5d=avg_d5,
            avg_drift_20d=avg_d20,
            avg_beat_drift_1d=avg_beat_d1,
            avg_miss_drift_1d=avg_miss_d1,
            next_earnings_date=next_earnings,
        )

    except Exception as exc:
        warnings.warn(f"get_earnings_history({ticker}): {exc}")
        return None
