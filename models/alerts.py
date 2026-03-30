"""
models/alerts.py — Datenmodell & Speicherung für Trading-Alerts.

Erstellt, lädt und speichert Preis-, Indikator- und Score-Benachrichtigungen.
"""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from uuid import uuid4


DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "alerts.json")

os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)


@dataclass
class AlertConfig:
    """Repräsentiert einen Trading-Alert."""
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    ticker: str = ""
    # Typen: 'price_above', 'price_below', 'rsi_above', 'rsi_below', 'score_above', 'score_below'
    alert_type: str = "price_below"
    threshold: float = 0.0
    status: str = "active"  # "active", "triggered", "acknowledged"
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    triggered_at: str | None = None
    trigger_value: float | None = None  # Der Wert, der den Alarm ausgelöst hat

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AlertStore:
    """Verwaltet das Laden und Speichern von Alerts."""

    @staticmethod
    def _load_all() -> list[dict]:
        if not os.path.exists(DATA_FILE):
            return []
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    @staticmethod
    def _save_all(data: list[dict]):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @classmethod
    def get_all(cls) -> list[AlertConfig]:
        """Gibt alle Alerts sortiert nach Erstellungsdatum zurück."""
        data = cls._load_all()
        alerts = [AlertConfig.from_dict(a) for a in data]
        
        def get_date(a):
            try:
                return datetime.strptime(a.created_at, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return datetime.min
                
        alerts.sort(key=get_date, reverse=True)
        return alerts

    @classmethod
    def get_active(cls) -> list[AlertConfig]:
        return [a for a in cls.get_all() if a.status == "active"]

    @classmethod
    def get_triggered_unacknowledged(cls) -> list[AlertConfig]:
        return [a for a in cls.get_all() if a.status == "triggered"]

    @classmethod
    def save(cls, alert: AlertConfig):
        """Speichert einen neuen Alert oder überschreibt ihn."""
        all_data = cls._load_all()
        found = False
        
        alert_dict = asdict(alert)
        for i, existing in enumerate(all_data):
            if existing.get("id") == alert.id:
                all_data[i] = alert_dict
                found = True
                break
                
        if not found:
            all_data.append(alert_dict)
            
        cls._save_all(all_data)

    @classmethod
    def acknowledge_alert(cls, alert_id: str):
        """Markiert einen ausgelösten Alarm als 'gelesen' (acknowledged)."""
        alerts = cls.get_all()
        for a in alerts:
            if a.id == alert_id:
                a.status = "acknowledged"
                cls.save(a)
                return True
        return False

    @classmethod
    def delete_alert(cls, alert_id: str):
        """Löscht einen Alert."""
        all_data = cls._load_all()
        filtered = [a for a in all_data if a.get("id") != alert_id]
        if len(filtered) < len(all_data):
            cls._save_all(filtered)
            return True
        return False
