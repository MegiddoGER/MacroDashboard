"""
database.py — Zentrale Datenbankschicht (SQLAlchemy).

Definiert alle Tabellen-Modelle und stellt die Session-Factory bereit.
Aktuell: SQLite (lokale Datei). Später: PostgreSQL (1 Zeile ändern).

Architektur:
  database.py       → Engine, Session, ORM-Modelle, Migration
  models/*.py       → Nutzen get_session() für CRUD-Operationen
  services/*.py     → Nutzen models/*.py (kein direkter DB-Zugriff)
"""

import json
import os
from datetime import datetime

from sqlalchemy import (
    create_engine, Column, Integer, Float, Text, Boolean,
    ForeignKey, event,
)
from sqlalchemy.orm import (
    DeclarativeBase, sessionmaker, relationship,
)


# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_DB_FILE = os.path.join(_DATA_DIR, "macrodashboard.db")

os.makedirs(_DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Engine & Session
# ---------------------------------------------------------------------------

# ↓↓↓ DIESE EINE ZEILE ÄNDERN FÜR POSTGRESQL ↓↓↓
DATABASE_URL = f"sqlite:///{_DB_FILE}"
# Beispiel PostgreSQL: DATABASE_URL = "postgresql://user:pass@localhost/macrodashboard"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

# Enable WAL mode & foreign keys for SQLite
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    """Gibt eine neue DB-Session zurück. Immer mit `with` oder try/finally nutzen."""
    return SessionLocal()


# ---------------------------------------------------------------------------
# Base Model
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM-Modelle
# ---------------------------------------------------------------------------

class WatchlistItem(Base):
    __tablename__ = "watchlist"

    ticker = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    display = Column(Text)
    status = Column(Text, default="Beobachtet")

    positions = relationship("Position", back_populates="watchlist_item",
                             cascade="all, delete-orphan", lazy="joined")

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "display": self.display or self.ticker,
            "status": self.status or "Beobachtet",
            "positions": [p.to_dict() for p in (self.positions or [])],
        }


class Position(Base):
    __tablename__ = "positions"

    id = Column(Text, primary_key=True)
    ticker = Column(Text, ForeignKey("watchlist.ticker", ondelete="CASCADE"), nullable=False)
    buy_date = Column(Text)
    buy_price = Column(Float)
    quantity = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    fees = Column(Float, default=0)
    notes = Column(Text)
    sell_date = Column(Text)
    sell_price = Column(Float)
    sell_fees = Column(Float)

    watchlist_item = relationship("WatchlistItem", back_populates="positions")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "buy_date": self.buy_date,
            "buy_price": self.buy_price,
            "quantity": self.quantity,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "fees": self.fees or 0,
            "notes": self.notes or "",
            "sell_date": self.sell_date,
            "sell_price": self.sell_price,
            "sell_fees": self.sell_fees,
        }


class JournalEntry(Base):
    __tablename__ = "journal"

    id = Column(Text, primary_key=True)
    ticker = Column(Text)
    trade_type = Column(Text, default="Long")
    setup_type = Column(Text)
    entry_date = Column(Text)
    entry_price = Column(Float)
    conviction = Column(Integer, default=3)
    entry_notes = Column(Text)
    status = Column(Text, default="Offen")
    exit_date = Column(Text)
    exit_price = Column(Float)
    pnl_eur = Column(Float)
    pnl_pct = Column(Float)
    review_notes = Column(Text)


class SignalRecord(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(Text, index=True)
    timestamp = Column(Text)
    signal_type = Column(Text)
    confidence = Column(Float)
    score_label = Column(Text)
    confidence_label = Column(Text)
    cat_scores_json = Column(Text)       # JSON-String
    cat_max_json = Column(Text)          # JSON-String
    weights_json = Column(Text)          # JSON-String
    price_at_signal = Column(Float)
    rsi_at_signal = Column(Float)
    volume_spike = Column(Boolean, default=False)
    contributing_factors_json = Column(Text)  # JSON-String
    macro_text = Column(Text)
    actionable_text = Column(Text)
    price_1w_later = Column(Float)
    price_1m_later = Column(Float)
    price_3m_later = Column(Float)
    was_successful = Column(Boolean)


class AlertRecord(Base):
    __tablename__ = "alerts"

    id = Column(Text, primary_key=True)
    ticker = Column(Text)
    alert_type = Column(Text)
    threshold = Column(Float)
    status = Column(Text, default="active")
    created_at = Column(Text)
    triggered_at = Column(Text)
    trigger_value = Column(Float)


# ---------------------------------------------------------------------------
# Initialisierung & Migration
# ---------------------------------------------------------------------------

def init_db():
    """Erstellt alle Tabellen (falls nicht vorhanden) und migriert JSON-Daten."""
    Base.metadata.create_all(engine)
    _migrate_json_if_needed()


def _migrate_json_if_needed():
    """Einmalige Migration: Liest bestehende JSON-Dateien und importiert sie in die DB."""
    session = get_session()
    try:
        # Prüfe ob Migration schon gelaufen ist (Watchlist hat Daten)
        existing_count = session.query(WatchlistItem).count()
        if existing_count > 0:
            return  # Bereits migriert

        migrated_any = False

        # ── Watchlist + Positionen ───────────────────────────────────
        wl_file = os.path.join(_DATA_DIR, "watchlist.json")
        if os.path.exists(wl_file):
            try:
                with open(wl_file, "r", encoding="utf-8") as f:
                    wl_data = json.load(f)
                for item in wl_data:
                    wl = WatchlistItem(
                        ticker=item["ticker"],
                        name=item.get("name", ""),
                        display=item.get("display"),
                        status=item.get("status", "Beobachtet"),
                    )
                    session.add(wl)
                    for pos in item.get("positions", []):
                        p = Position(
                            id=pos.get("id", ""),
                            ticker=item["ticker"],
                            buy_date=pos.get("buy_date"),
                            buy_price=pos.get("buy_price"),
                            quantity=pos.get("quantity"),
                            stop_loss=pos.get("stop_loss"),
                            take_profit=pos.get("take_profit"),
                            fees=pos.get("fees", 0),
                            notes=pos.get("notes", ""),
                            sell_date=pos.get("sell_date"),
                            sell_price=pos.get("sell_price"),
                            sell_fees=pos.get("sell_fees"),
                        )
                        session.add(p)
                migrated_any = True
                print(f"✅ Watchlist migriert: {len(wl_data)} Einträge")
            except Exception as e:
                print(f"⚠️ Watchlist-Migration fehlgeschlagen: {e}")

        # ── Journal ──────────────────────────────────────────────────
        journal_file = os.path.join(_DATA_DIR, "journal.json")
        if os.path.exists(journal_file):
            try:
                with open(journal_file, "r", encoding="utf-8") as f:
                    journal_data = json.load(f)
                for entry in journal_data:
                    je = JournalEntry(
                        id=entry.get("id", ""),
                        ticker=entry.get("ticker", ""),
                        trade_type=entry.get("trade_type", "Long"),
                        setup_type=entry.get("setup_type"),
                        entry_date=entry.get("entry_date"),
                        entry_price=entry.get("entry_price"),
                        conviction=entry.get("conviction", 3),
                        entry_notes=entry.get("entry_notes"),
                        status=entry.get("status", "Offen"),
                        exit_date=entry.get("exit_date"),
                        exit_price=entry.get("exit_price"),
                        pnl_eur=entry.get("pnl_eur"),
                        pnl_pct=entry.get("pnl_pct"),
                        review_notes=entry.get("review_notes"),
                    )
                    session.add(je)
                migrated_any = True
                print(f"✅ Journal migriert: {len(journal_data)} Einträge")
            except Exception as e:
                print(f"⚠️ Journal-Migration fehlgeschlagen: {e}")

        # ── Signale ──────────────────────────────────────────────────
        signals_file = os.path.join(_DATA_DIR, "signals.json")
        if os.path.exists(signals_file):
            try:
                with open(signals_file, "r", encoding="utf-8") as f:
                    sig_data = json.load(f)
                for s in sig_data:
                    sr = SignalRecord(
                        ticker=s.get("ticker"),
                        timestamp=s.get("timestamp"),
                        signal_type=s.get("signal_type"),
                        confidence=s.get("confidence"),
                        score_label=s.get("score_label"),
                        confidence_label=s.get("confidence_label"),
                        cat_scores_json=json.dumps(s.get("cat_scores", {})),
                        cat_max_json=json.dumps(s.get("cat_max", {})),
                        weights_json=json.dumps(s.get("weights", {})),
                        price_at_signal=s.get("price_at_signal"),
                        rsi_at_signal=s.get("rsi_at_signal"),
                        volume_spike=s.get("volume_spike", False),
                        contributing_factors_json=json.dumps(s.get("contributing_factors", [])),
                        macro_text=s.get("macro_text"),
                        actionable_text=s.get("actionable_text"),
                        price_1w_later=s.get("price_1w_later"),
                        price_1m_later=s.get("price_1m_later"),
                        price_3m_later=s.get("price_3m_later"),
                        was_successful=s.get("was_successful"),
                    )
                    session.add(sr)
                migrated_any = True
                print(f"✅ Signale migriert: {len(sig_data)} Einträge")
            except Exception as e:
                print(f"⚠️ Signal-Migration fehlgeschlagen: {e}")

        # ── Alerts ───────────────────────────────────────────────────
        alerts_file = os.path.join(_DATA_DIR, "alerts.json")
        if os.path.exists(alerts_file):
            try:
                with open(alerts_file, "r", encoding="utf-8") as f:
                    alert_data = json.load(f)
                for a in alert_data:
                    ar = AlertRecord(
                        id=a.get("id", ""),
                        ticker=a.get("ticker"),
                        alert_type=a.get("alert_type"),
                        threshold=a.get("threshold"),
                        status=a.get("status", "active"),
                        created_at=a.get("created_at"),
                        triggered_at=a.get("triggered_at"),
                        trigger_value=a.get("trigger_value"),
                    )
                    session.add(ar)
                migrated_any = True
                print(f"✅ Alerts migriert: {len(alert_data)} Einträge")
            except Exception as e:
                print(f"⚠️ Alert-Migration fehlgeschlagen: {e}")

        if migrated_any:
            session.commit()
            print("✅ JSON → SQLite Migration abgeschlossen!")
        else:
            print("ℹ️ Keine JSON-Daten zum Migrieren gefunden.")

    except Exception as e:
        session.rollback()
        print(f"❌ Migration fehlgeschlagen: {e}")
    finally:
        session.close()
