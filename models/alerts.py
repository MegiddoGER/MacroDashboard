"""
models/alerts.py — Datenmodell & Speicherung für Trading-Alerts.

Persistenz: SQLAlchemy (SQLite → PostgreSQL ready).
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from uuid import uuid4

from database import get_session, AlertRecord


@dataclass
class AlertConfig:
    """Repräsentiert einen Trading-Alert."""
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    ticker: str = ""
    alert_type: str = "price_below"
    threshold: float = 0.0
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    triggered_at: str | None = None
    trigger_value: float | None = None

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_db(cls, row: AlertRecord):
        """Erstellt AlertConfig aus einem DB-Row."""
        return cls(
            id=row.id, ticker=row.ticker or "", alert_type=row.alert_type or "price_below",
            threshold=row.threshold or 0.0, status=row.status or "active",
            created_at=row.created_at or "", triggered_at=row.triggered_at,
            trigger_value=row.trigger_value,
        )


class AlertStore:
    """Verwaltet das Laden und Speichern von Alerts via SQLAlchemy."""

    @classmethod
    def get_all(cls) -> list[AlertConfig]:
        """Gibt alle Alerts sortiert nach Erstellungsdatum zurück."""
        session = get_session()
        try:
            rows = session.query(AlertRecord).order_by(
                AlertRecord.created_at.desc()
            ).all()
            return [AlertConfig.from_db(r) for r in rows]
        finally:
            session.close()

    @classmethod
    def get_active(cls) -> list[AlertConfig]:
        session = get_session()
        try:
            rows = session.query(AlertRecord).filter_by(status="active").order_by(
                AlertRecord.created_at.desc()
            ).all()
            return [AlertConfig.from_db(r) for r in rows]
        finally:
            session.close()

    @classmethod
    def get_triggered_unacknowledged(cls) -> list[AlertConfig]:
        session = get_session()
        try:
            rows = session.query(AlertRecord).filter_by(status="triggered").all()
            return [AlertConfig.from_db(r) for r in rows]
        finally:
            session.close()

    @classmethod
    def get_acknowledged(cls) -> list[AlertConfig]:
        session = get_session()
        try:
            rows = session.query(AlertRecord).filter_by(status="acknowledged").all()
            return [AlertConfig.from_db(r) for r in rows]
        finally:
            session.close()

    @classmethod
    def save(cls, alert: AlertConfig):
        """Speichert einen neuen Alert oder überschreibt ihn."""
        session = get_session()
        try:
            existing = session.query(AlertRecord).filter_by(id=alert.id).first()
            if existing:
                existing.ticker = alert.ticker
                existing.alert_type = alert.alert_type
                existing.threshold = alert.threshold
                existing.status = alert.status
                existing.created_at = alert.created_at
                existing.triggered_at = alert.triggered_at
                existing.trigger_value = alert.trigger_value
            else:
                row = AlertRecord(
                    id=alert.id, ticker=alert.ticker, alert_type=alert.alert_type,
                    threshold=alert.threshold, status=alert.status,
                    created_at=alert.created_at, triggered_at=alert.triggered_at,
                    trigger_value=alert.trigger_value,
                )
                session.add(row)
            session.commit()
        finally:
            session.close()

    @classmethod
    def acknowledge_alert(cls, alert_id: str):
        """Markiert einen ausgelösten Alarm als 'gelesen'."""
        session = get_session()
        try:
            row = session.query(AlertRecord).filter_by(id=alert_id).first()
            if row:
                row.status = "acknowledged"
                session.commit()
                return True
            return False
        finally:
            session.close()

    @classmethod
    def delete_alert(cls, alert_id: str):
        """Löscht einen Alert."""
        session = get_session()
        try:
            row = session.query(AlertRecord).filter_by(id=alert_id).first()
            if row:
                session.delete(row)
                session.commit()
                return True
            return False
        finally:
            session.close()
