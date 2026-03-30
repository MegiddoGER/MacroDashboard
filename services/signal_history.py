"""
services/signal_history.py — Automatische Signal-Historisierung & Trefferquoten.

Nutzt das bestehende models/signal.py (Signal + SignalStore) und erweitert es um:
- Automatische Aufzeichnung bei Score-Berechnung
- Batch-Update der Outcomes (1W/1M/3M)
- Trefferquoten-Berechnung
- Confidence-Kalibrierung (Confidence vs. tatsächliche Win-Rate)
- 1-Jahr Retention Policy (alte Signale löschen)
"""

import warnings
from datetime import datetime, timedelta

import numpy as np
import yfinance as yf

from models.signal import Signal, SignalStore


# ---------------------------------------------------------------------------
# Automatische Signal-Aufzeichnung
# ---------------------------------------------------------------------------

def record_signal(ticker: str, score_result, current_price: float = 0.0) -> Signal | None:
    """Speichert ein Signal automatisch bei Score-Berechnung.

    Prüft vorher, ob für den gleichen Ticker innerhalb der letzten 4 Stunden
    bereits ein Signal gespeichert wurde (Deduplizierung).

    Args:
        ticker: Aktien-Ticker
        score_result: ScoreResult von services/scoring.py
        current_price: Aktueller Kurs

    Returns:
        Das gespeicherte Signal, oder None wenn dedupliziert.
    """
    if score_result is None:
        return None

    # Deduplizierung: Kein neues Signal wenn innerhalb von 4h schon eines existiert
    latest = SignalStore.get_latest(ticker)
    if latest and latest.timestamp:
        try:
            last_time = datetime.fromisoformat(latest.timestamp)
            if datetime.now() - last_time < timedelta(hours=4):
                return None  # Zu kürzlich — kein neues Signal
        except ValueError:
            pass

    # Signal erstellen und speichern
    signal = Signal.from_score_result(ticker, score_result, current_price)
    SignalStore.save(signal)
    return signal


# ---------------------------------------------------------------------------
# Batch-Update: Outcomes für ältere Signale bewerten
# ---------------------------------------------------------------------------

def update_stale_signals(max_signals: int = 50) -> dict:
    """Aktualisiert Outcomes für Signale die alt genug sind.

    Prüft:
    - Signale > 7 Tage alt → price_1w_later
    - Signale > 30 Tage alt → price_1m_later
    - Signale > 90 Tage alt → price_3m_later

    Returns:
        Dict mit updated_count, checked_count
    """
    all_signals = SignalStore.get_all(limit=max_signals)
    now = datetime.now()
    updated = 0
    checked = 0

    for signal in all_signals:
        if not signal.timestamp or not signal.ticker or signal.price_at_signal <= 0:
            continue

        try:
            signal_time = datetime.fromisoformat(signal.timestamp)
        except ValueError:
            continue

        age_days = (now - signal_time).days
        needs_update = False

        # Prüfe welche Zeiträume aktualisiert werden müssen
        update_1w = age_days >= 7 and signal.price_1w_later is None
        update_1m = age_days >= 30 and signal.price_1m_later is None
        update_3m = age_days >= 90 and signal.price_3m_later is None

        if not (update_1w or update_1m or update_3m):
            continue

        checked += 1

        # Aktuelle/historische Kurse laden
        try:
            hist = yf.Ticker(signal.ticker).history(
                start=(signal_time - timedelta(days=1)).strftime("%Y-%m-%d"),
                end=(now + timedelta(days=1)).strftime("%Y-%m-%d"),
            )
            if hist.empty:
                continue
        except Exception:
            continue

        price_1w = None
        price_1m = None
        price_3m = None

        if update_1w:
            target_date = signal_time + timedelta(days=7)
            price_1w = _get_price_at_date(hist, target_date)

        if update_1m:
            target_date = signal_time + timedelta(days=30)
            price_1m = _get_price_at_date(hist, target_date)

        if update_3m:
            target_date = signal_time + timedelta(days=90)
            price_3m = _get_price_at_date(hist, target_date)

        if price_1w is not None or price_1m is not None or price_3m is not None:
            success = SignalStore.update_outcome(
                ticker=signal.ticker,
                timestamp=signal.timestamp,
                price_1w=price_1w,
                price_1m=price_1m,
                price_3m=price_3m,
            )
            if success:
                updated += 1

    return {"updated_count": updated, "checked_count": checked}


def _get_price_at_date(hist, target_date: datetime) -> float | None:
    """Findet den Schlusskurs am nächsten verfügbaren Handelstag."""
    if hist.empty:
        return None

    target_ts = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Index tz-naive machen
    idx = hist.index.tz_localize(None) if hist.index.tz else hist.index

    # Nächsten verfügbaren Tag finden (±3 Tage Toleranz)
    for offset in range(0, 4):
        for delta in [timedelta(days=offset), timedelta(days=-offset)]:
            check = target_ts + delta
            mask = (idx.date == check.date())
            if mask.any():
                return float(hist.loc[hist.index[mask][-1], "Close"])

    return None


# ---------------------------------------------------------------------------
# Trefferquoten-Berechnung
# ---------------------------------------------------------------------------

def calc_hit_rate(days: int = 90) -> dict:
    """Berechnet die Trefferquote der Signale.

    Args:
        days: Zeitraum in Tagen (Default: 90 Tage)

    Returns:
        Dict mit total, evaluated, buy_signals, sell_signals,
        buy_hit_rate, sell_hit_rate, overall_hit_rate
    """
    all_signals = SignalStore.get_all()
    cutoff = datetime.now() - timedelta(days=days)

    # Nur Signale im Zeitraum
    recent = []
    for s in all_signals:
        try:
            ts = datetime.fromisoformat(s.timestamp)
            if ts >= cutoff:
                recent.append(s)
        except (ValueError, AttributeError):
            pass

    total = len(recent)
    evaluated = [s for s in recent if s.was_successful is not None]
    buy_signals = [s for s in evaluated if s.signal_type == "buy"]
    sell_signals = [s for s in evaluated if s.signal_type == "sell"]

    buy_wins = len([s for s in buy_signals if s.was_successful])
    sell_wins = len([s for s in sell_signals if s.was_successful])
    total_wins = buy_wins + sell_wins

    return {
        "total": total,
        "evaluated": len(evaluated),
        "buy_signals_count": len(buy_signals),
        "sell_signals_count": len(sell_signals),
        "buy_hit_rate": round(buy_wins / len(buy_signals) * 100, 1) if buy_signals else None,
        "sell_hit_rate": round(sell_wins / len(sell_signals) * 100, 1) if sell_signals else None,
        "overall_hit_rate": round(total_wins / len(evaluated) * 100, 1) if evaluated else None,
        "buy_wins": buy_wins,
        "sell_wins": sell_wins,
    }


# ---------------------------------------------------------------------------
# Confidence-Kalibrierung
# ---------------------------------------------------------------------------

def calc_calibration_chart() -> list[dict]:
    """Berechnet Confidence vs. tatsächliche Win-Rate in Buckets.

    Buckets: 0-20, 20-40, 40-60, 60-80, 80-100

    Returns:
        Liste von dicts [{bucket, confidence_range, count, wins, hit_rate}, ...]
    """
    all_signals = SignalStore.get_all()
    evaluated = [s for s in all_signals if s.was_successful is not None]

    buckets = [
        (0, 20, "0-20"),
        (20, 40, "20-40"),
        (40, 60, "40-60"),
        (60, 80, "60-80"),
        (80, 100, "80-100"),
    ]

    result = []
    for low, high, label in buckets:
        in_bucket = [s for s in evaluated if low <= s.confidence < high]
        wins = len([s for s in in_bucket if s.was_successful])
        count = len(in_bucket)

        result.append({
            "bucket": label,
            "confidence_range": f"{low}-{high}%",
            "count": count,
            "wins": wins,
            "hit_rate": round(wins / count * 100, 1) if count > 0 else None,
        })

    return result


# ---------------------------------------------------------------------------
# Statistiken
# ---------------------------------------------------------------------------

def get_signal_statistics() -> dict:
    """Gibt aggregierte Signal-Statistiken zurück.

    Returns:
        Dict mit total, by_type, best_ticker, worst_ticker, etc.
    """
    all_signals = SignalStore.get_all()
    evaluated = [s for s in all_signals if s.was_successful is not None]

    # Ticker-Performance
    ticker_stats = {}
    for s in evaluated:
        if s.ticker not in ticker_stats:
            ticker_stats[s.ticker] = {"total": 0, "wins": 0}
        ticker_stats[s.ticker]["total"] += 1
        if s.was_successful:
            ticker_stats[s.ticker]["wins"] += 1

    # Best/Worst Ticker
    best_ticker = None
    worst_ticker = None
    best_rate = -1
    worst_rate = 101

    for ticker, stats in ticker_stats.items():
        if stats["total"] >= 2:  # Mindestens 2 Signale für Relevanz
            rate = stats["wins"] / stats["total"] * 100
            if rate > best_rate:
                best_rate = rate
                best_ticker = (ticker, round(rate, 1), stats["total"])
            if rate < worst_rate:
                worst_rate = rate
                worst_ticker = (ticker, round(rate, 1), stats["total"])

    # Durchschnittlicher Confidence-Score
    avg_confidence = round(np.mean([s.confidence for s in all_signals]), 1) if all_signals else 0

    # Signal-Alter (neuestes und ältestes)
    newest = all_signals[0].timestamp if all_signals else None
    oldest = all_signals[-1].timestamp if all_signals else None

    # Top & Flop Individual Signals berechnen
    signal_returns = []
    for s in evaluated:
        if s.price_at_signal <= 0:
            continue
        
        # Nimm den jüngsten/längsten verfügbaren Schlusskurs für die Performance
        final_price = None
        if s.price_3m_later is not None:
            final_price = s.price_3m_later
        elif s.price_1m_later is not None:
            final_price = s.price_1m_later
        elif s.price_1w_later is not None:
            final_price = s.price_1w_later
            
        if final_price:
            pct_change = ((final_price - s.price_at_signal) / s.price_at_signal) * 100
            
            # Hatten wir Buy oder Sell?
            if s.signal_type == "sell":
                pct_change = -pct_change  # Bei Short ist ein Kursverfall ein Gewinn
                
            signal_returns.append({
                "ticker": s.ticker,
                "timestamp": s.timestamp,
                "type": s.signal_type,
                "confidence": s.confidence,
                "return_pct": pct_change,
                "was_successful": s.was_successful
            })
            
    signal_returns.sort(key=lambda x: x["return_pct"], reverse=True)
    top_3_signals = signal_returns[:3] if signal_returns else []
    flop_3_signals = signal_returns[-3:] if len(signal_returns) >= 3 else []
    flop_3_signals.reverse() # Schlechtester zuerst

    return {
        "total_signals": len(all_signals),
        "evaluated_signals": len(evaluated),
        "pending_signals": len(all_signals) - len(evaluated),
        "avg_confidence": avg_confidence,
        "best_ticker": best_ticker,   # (ticker, hit_rate, count) or None
        "worst_ticker": worst_ticker,
        "newest_signal": newest,
        "oldest_signal": oldest,
        "ticker_count": len(ticker_stats),
        "top_signals": top_3_signals,
        "flop_signals": flop_3_signals,
    }


# ---------------------------------------------------------------------------
# Retention: Alte Signale löschen (> 1 Jahr)
# ---------------------------------------------------------------------------

def cleanup_old_signals() -> int:
    """Löscht Signale die älter als 1 Jahr sind.

    Returns:
        Anzahl gelöschter Signale
    """
    all_raw = SignalStore._load_all()
    cutoff = datetime.now() - timedelta(days=365)
    original_count = len(all_raw)

    filtered = []
    for s in all_raw:
        ts_str = s.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts >= cutoff:
                filtered.append(s)
        except (ValueError, AttributeError):
            filtered.append(s)  # Behalte bei ungültigem Timestamp

    deleted = original_count - len(filtered)
    if deleted > 0:
        SignalStore._save_all(filtered)

    return deleted
