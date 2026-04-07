"""
models/signal.py — Standardisiertes Signal-Datenmodell für das MacroDashboard.

Persistenz: SQLAlchemy (SQLite → PostgreSQL ready).
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from database import get_session, SignalRecord


# ---------------------------------------------------------------------------
# Signal-Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """Ein einzelnes Analyse-Signal mit allen relevanten Daten."""

    # Kernfelder
    ticker: str = ""
    timestamp: str = ""                    # ISO-Format: "2024-01-15T14:30:00"
    signal_type: str = "hold"              # "buy", "sell", "hold"
    confidence: float = 50.0               # 0-100, aus Scoring Engine

    # Score-Details
    score_label: str = ""
    confidence_label: str = ""
    cat_scores: dict = field(default_factory=dict)
    cat_max: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)

    # Marktdaten zum Signal-Zeitpunkt
    price_at_signal: float = 0.0
    rsi_at_signal: Optional[float] = None
    volume_spike: bool = False

    # Kontext
    contributing_factors: list = field(default_factory=list)
    macro_text: str = ""
    actionable_text: str = ""

    # Nachverfolgung
    price_1w_later: Optional[float] = None
    price_1m_later: Optional[float] = None
    price_3m_later: Optional[float] = None
    was_successful: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Signal":
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    @classmethod
    def from_db(cls, row: SignalRecord) -> "Signal":
        """Erstellt ein Signal aus einem DB-Row."""
        return cls(
            ticker=row.ticker or "",
            timestamp=row.timestamp or "",
            signal_type=row.signal_type or "hold",
            confidence=row.confidence or 50.0,
            score_label=row.score_label or "",
            confidence_label=row.confidence_label or "",
            cat_scores=json.loads(row.cat_scores_json) if row.cat_scores_json else {},
            cat_max=json.loads(row.cat_max_json) if row.cat_max_json else {},
            weights=json.loads(row.weights_json) if row.weights_json else {},
            price_at_signal=row.price_at_signal or 0.0,
            rsi_at_signal=row.rsi_at_signal,
            volume_spike=bool(row.volume_spike),
            contributing_factors=json.loads(row.contributing_factors_json) if row.contributing_factors_json else [],
            macro_text=row.macro_text or "",
            actionable_text=row.actionable_text or "",
            price_1w_later=row.price_1w_later,
            price_1m_later=row.price_1m_later,
            price_3m_later=row.price_3m_later,
            was_successful=row.was_successful,
        )

    @classmethod
    def from_score_result(cls, ticker: str, score_result, price: float = 0.0) -> "Signal":
        """Erstellt ein Signal aus einem ScoreResult (von scoring.py)."""
        if score_result.confidence >= 65:
            signal_type = "buy"
        elif score_result.confidence <= 35:
            signal_type = "sell"
        else:
            signal_type = "hold"

        factors = []
        for entry in score_result.checklist:
            signal_text = entry.get("Signal", "")
            if "🟢" in signal_text or "↑" in signal_text:
                factors.append(f"✅ {entry.get('Indikator', '')}: {signal_text}")
            elif "🔴" in signal_text or "↓" in signal_text:
                factors.append(f"❌ {entry.get('Indikator', '')}: {signal_text}")

        return cls(
            ticker=ticker.upper(),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            signal_type=signal_type,
            confidence=score_result.confidence,
            score_label=score_result.score_label,
            confidence_label=score_result.confidence_label,
            cat_scores=dict(score_result.cat_scores),
            cat_max=dict(score_result.cat_max),
            weights=dict(score_result.weights),
            price_at_signal=round(price, 2),
            rsi_at_signal=score_result.signals.get("rsi_val"),
            contributing_factors=factors,
        )


# ---------------------------------------------------------------------------
# Signal-Store (SQLAlchemy Persistenz)
# ---------------------------------------------------------------------------

class SignalStore:
    """Persistente Speicherung von Signalen in der Datenbank."""

    @classmethod
    def save(cls, signal: Signal) -> None:
        """Speichert ein neues Signal."""
        session = get_session()
        try:
            row = SignalRecord(
                ticker=signal.ticker,
                timestamp=signal.timestamp,
                signal_type=signal.signal_type,
                confidence=signal.confidence,
                score_label=signal.score_label,
                confidence_label=signal.confidence_label,
                cat_scores_json=json.dumps(signal.cat_scores),
                cat_max_json=json.dumps(signal.cat_max),
                weights_json=json.dumps(signal.weights),
                price_at_signal=signal.price_at_signal,
                rsi_at_signal=signal.rsi_at_signal,
                volume_spike=signal.volume_spike,
                contributing_factors_json=json.dumps(signal.contributing_factors),
                macro_text=signal.macro_text,
                actionable_text=signal.actionable_text,
                price_1w_later=signal.price_1w_later,
                price_1m_later=signal.price_1m_later,
                price_3m_later=signal.price_3m_later,
                was_successful=signal.was_successful,
            )
            session.add(row)
            session.commit()
        finally:
            session.close()

    @classmethod
    def get_all(cls, ticker: str = None, limit: int = None) -> list[Signal]:
        """Lädt Signale, optional gefiltert nach Ticker."""
        session = get_session()
        try:
            query = session.query(SignalRecord)
            if ticker:
                query = query.filter(SignalRecord.ticker == ticker.upper())
            query = query.order_by(SignalRecord.timestamp.desc())
            if limit:
                query = query.limit(limit)
            return [Signal.from_db(r) for r in query.all()]
        finally:
            session.close()

    @classmethod
    def get_latest(cls, ticker: str) -> Signal | None:
        """Gibt das neueste Signal für einen Ticker zurück."""
        signals = cls.get_all(ticker=ticker, limit=1)
        return signals[0] if signals else None

    @classmethod
    def count(cls, ticker: str = None) -> int:
        """Zählt gespeicherte Signale."""
        session = get_session()
        try:
            query = session.query(SignalRecord)
            if ticker:
                query = query.filter(SignalRecord.ticker == ticker.upper())
            return query.count()
        finally:
            session.close()

    @classmethod
    def update_outcome(cls, ticker: str, timestamp: str,
                       price_1w: float = None, price_1m: float = None,
                       price_3m: float = None) -> bool:
        """Aktualisiert die Nachverfolgung eines Signals."""
        session = get_session()
        try:
            row = session.query(SignalRecord).filter_by(
                ticker=ticker.upper(), timestamp=timestamp
            ).first()
            if not row:
                return False

            if price_1w is not None:
                row.price_1w_later = round(price_1w, 2)
            if price_1m is not None:
                row.price_1m_later = round(price_1m, 2)
            if price_3m is not None:
                row.price_3m_later = round(price_3m, 2)

            # Erfolgsberechnung
            entry_price = row.price_at_signal or 0
            signal_type = row.signal_type or "hold"
            check_price = price_1m or price_1w

            if entry_price > 0 and check_price and signal_type != "hold":
                if signal_type == "buy":
                    row.was_successful = check_price > entry_price
                elif signal_type == "sell":
                    row.was_successful = check_price < entry_price

            session.commit()
            return True
        finally:
            session.close()
