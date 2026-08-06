"""
snapshot_engine/models.py — Datenbankmodelle für die Snapshot Engine.

Definiert AnalyseSnapshot und SnapshotKonfiguration als SQLAlchemy-Modelle.
Nutzt die bestehende Engine/Base aus database.py — erstellt keine zweite Verbindung.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import Integer, Float, Text, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, Session

from database import Base, engine, get_session


# ---------------------------------------------------------------------------
# ORM-Modelle
# ---------------------------------------------------------------------------

class AnalyseSnapshot(Base):
    """Eingefrorener Analyse-Zustand zu einem bestimmten Zeitpunkt."""
    __tablename__ = "analyse_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    snapshot_zeitpunkt: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kurs_bei_snapshot: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)           # 0–100
    confidence_label: Mapped[Optional[str]] = mapped_column(Text)              # z.B. "Hohe Confidence"
    richtungssignal: Mapped[str] = mapped_column(Text, nullable=False)         # "KAUF" / "NEUTRAL" / "VERKAUF"
    indikator_json: Mapped[Optional[str]] = mapped_column(Text)                # JSON-serialisiertes cat_scores-Dict
    zeitfenster_tage: Mapped[Optional[int]] = mapped_column(Integer, default=7)

    # Outcome-Felder (werden nachträglich befüllt)
    outcome_kurs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)        # in Prozent
    outcome_zeitpunkt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ausgewertet: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "snapshot_zeitpunkt": self.snapshot_zeitpunkt.isoformat() if self.snapshot_zeitpunkt else None,
            "kurs_bei_snapshot": self.kurs_bei_snapshot,
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "richtungssignal": self.richtungssignal,
            "indikator_json": self.indikator_json,
            "zeitfenster_tage": self.zeitfenster_tage,
            "outcome_kurs": self.outcome_kurs,
            "outcome_return": self.outcome_return,
            "outcome_zeitpunkt": self.outcome_zeitpunkt.isoformat() if self.outcome_zeitpunkt else None,
            "ausgewertet": self.ausgewertet,
        }


class SnapshotKonfiguration(Base):
    """Konfiguration: Welche Ticker sollen täglich analysiert werden."""
    __tablename__ = "snapshot_konfiguration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    aktiv: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    zeitfenster_tage: Mapped[Optional[int]] = mapped_column(Integer, default=7)
    hinzugefuegt_am: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "aktiv": self.aktiv,
            "zeitfenster_tage": self.zeitfenster_tage,
            "hinzugefuegt_am": self.hinzugefuegt_am.isoformat() if self.hinzugefuegt_am else None,
        }


# ---------------------------------------------------------------------------
# Initialisierung
# ---------------------------------------------------------------------------

def init_snapshot_db():
    """Erstellt Tabellen und initialisiert Ticker aus watchlist.json falls nötig."""
    # Tabellen erstellen (falls nicht vorhanden)
    Base.metadata.create_all(engine)
    print("[Snapshot] Tabellen geprüft/erstellt.")

    # Ticker aus watchlist.json initialisieren falls SnapshotKonfiguration leer
    _ticker_initialisieren()


def _ticker_initialisieren():
    """Liest data/watchlist.json ein und legt alle Ticker als aktive Einträge an,
    falls die SnapshotKonfiguration-Tabelle noch leer ist."""
    session = get_session()
    try:
        vorhandene = session.query(SnapshotKonfiguration).count()
        if vorhandene > 0:
            return  # Bereits initialisiert

        watchlist_pfad = Path(__file__).parent.parent / "data" / "watchlist.json"
        if not watchlist_pfad.exists():
            print("[Snapshot] Keine watchlist.json gefunden — überspringe Initialisierung.")
            return

        try:
            with open(watchlist_pfad, "r", encoding="utf-8") as f:
                watchlist_daten = json.load(f)
        except Exception as e:
            print(f"[Snapshot] Fehler beim Lesen der watchlist.json: {e}")
            return

        anzahl = 0
        for eintrag in watchlist_daten:
            ticker = eintrag.get("ticker", "").strip()
            if not ticker:
                continue
            konfig = SnapshotKonfiguration(
                ticker=ticker,
                aktiv=True,
                zeitfenster_tage=7,
                hinzugefuegt_am=datetime.utcnow(),
            )
            session.add(konfig)
            anzahl += 1

        session.commit()
        print(f"[Snapshot] {anzahl} Ticker aus watchlist.json initialisiert.")

    except Exception as e:
        session.rollback()
        print(f"[Snapshot] Ticker-Initialisierung fehlgeschlagen: {e}")
    finally:
        session.close()
