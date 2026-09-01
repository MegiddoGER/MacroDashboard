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
from typing import Optional

from sqlalchemy import (
    create_engine, DateTime, Integer, Float, Text, Boolean,
    ForeignKey, UniqueConstraint, event,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, sessionmaker, relationship,
)

import config  # lädt .env, bevor DATABASE_URL gelesen wird


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

# Vorgabe: lokale SQLite-Datei. Überschreibbar via DATABASE_URL in .env,
# z. B. postgresql://user:pass@localhost/macrodashboard
DATABASE_URL = config.DATABASE_URL or f"sqlite:///{_DB_FILE}"

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

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    display: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text, default="Beobachtet")

    positions: Mapped[list["Position"]] = relationship(
        "Position", back_populates="watchlist_item",
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

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("watchlist.ticker", ondelete="CASCADE"), nullable=False)
    buy_date: Mapped[Optional[str]] = mapped_column(Text)
    buy_price: Mapped[Optional[float]] = mapped_column(Float)
    quantity: Mapped[Optional[float]] = mapped_column(Float)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float)
    take_profit: Mapped[Optional[float]] = mapped_column(Float)
    fees: Mapped[Optional[float]] = mapped_column(Float, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    sell_date: Mapped[Optional[str]] = mapped_column(Text)
    sell_price: Mapped[Optional[float]] = mapped_column(Float)
    sell_fees: Mapped[Optional[float]] = mapped_column(Float)

    watchlist_item: Mapped["WatchlistItem"] = relationship("WatchlistItem", back_populates="positions")

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

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    ticker: Mapped[Optional[str]] = mapped_column(Text)
    trade_type: Mapped[Optional[str]] = mapped_column(Text, default="Long")
    setup_type: Mapped[Optional[str]] = mapped_column(Text)
    entry_date: Mapped[Optional[str]] = mapped_column(Text)
    entry_price: Mapped[Optional[float]] = mapped_column(Float)
    conviction: Mapped[Optional[int]] = mapped_column(Integer, default=3)
    entry_notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text, default="Offen")
    exit_date: Mapped[Optional[str]] = mapped_column(Text)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    pnl_eur: Mapped[Optional[float]] = mapped_column(Float)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float)
    review_notes: Mapped[Optional[str]] = mapped_column(Text)


class SignalRecord(Base):
    """DEPRECATED — abgelöst durch snapshot_engine (Signal-Qualitäts-Engine).

    Die Daten werden einmalig nach analyse_snapshots/-outcomes migriert
    (snapshot_engine/models.py::_migrate_legacy_signal_data). Tabelle bleibt
    vorerst als Migrations-Absicherung bestehen und wird später entfernt.
    Kein neuer Code darf hierauf schreiben.
    """
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[Optional[str]] = mapped_column(Text, index=True)
    timestamp: Mapped[Optional[str]] = mapped_column(Text)
    signal_type: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    score_label: Mapped[Optional[str]] = mapped_column(Text)
    confidence_label: Mapped[Optional[str]] = mapped_column(Text)
    cat_scores_json: Mapped[Optional[str]] = mapped_column(Text)       # JSON-String
    cat_max_json: Mapped[Optional[str]] = mapped_column(Text)          # JSON-String
    weights_json: Mapped[Optional[str]] = mapped_column(Text)          # JSON-String
    price_at_signal: Mapped[Optional[float]] = mapped_column(Float)
    rsi_at_signal: Mapped[Optional[float]] = mapped_column(Float)
    volume_spike: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    contributing_factors_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON-String
    macro_text: Mapped[Optional[str]] = mapped_column(Text)
    actionable_text: Mapped[Optional[str]] = mapped_column(Text)
    price_1w_later: Mapped[Optional[float]] = mapped_column(Float)
    price_1m_later: Mapped[Optional[float]] = mapped_column(Float)
    price_3m_later: Mapped[Optional[float]] = mapped_column(Float)
    was_successful: Mapped[Optional[bool]] = mapped_column(Boolean)


class AlertRecord(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    ticker: Mapped[Optional[str]] = mapped_column(Text)
    alert_type: Mapped[Optional[str]] = mapped_column(Text)
    threshold: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[Optional[str]] = mapped_column(Text, default="active")
    created_at: Mapped[Optional[str]] = mapped_column(Text)
    triggered_at: Mapped[Optional[str]] = mapped_column(Text)
    trigger_value: Mapped[Optional[float]] = mapped_column(Float)


class PositionStopHistorie(Base):
    """Jede Stop-Loss-Setzung einer Position, in der Reihenfolge ihres Entstehens (P3-01).

    Ohne diese Historie ist der ursprünglich eingegangene Betrag nicht mehr
    feststellbar, sobald der Stop einmal nachgezogen wurde — und damit sind
    R-Multiple, MAE und MFE unberechenbar. Die Positionstabelle kennt nur den
    AKTUELLEN Stop; ein nachgezogener überschreibt den ursprünglichen
    spurlos.

    `quelle` unterscheidet, wie belastbar ein Eintrag ist:

        EROEFFNUNG   beim Anlegen der Position gesetzt — der echte
                     Einstiegs-Stop, auf dem das R-Multiple beruhen darf
        AENDERUNG    späteres Nachziehen
        ALTBESTAND   nachträglich vermerkt, weil die Position schon vor
                     Einführung dieser Historie bestand. Der Wert ist der
                     zuletzt bekannte, NICHT der ursprüngliche — deshalb
                     taugt er nicht als Bezugsgröße für das R-Multiple.
    """
    __tablename__ = "position_stop_historie"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(
        Text, ForeignKey("positions.id", ondelete="CASCADE"),
        nullable=False, index=True)
    stop: Mapped[float] = mapped_column(Float, nullable=False)
    quelle: Mapped[str] = mapped_column(Text, nullable=False)
    gesetzt_am: Mapped[Optional[str]] = mapped_column(Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "position_id": self.position_id,
            "stop": self.stop,
            "quelle": self.quelle,
            "gesetzt_am": self.gesetzt_am,
        }


class EarningsEvent(Base):
    """Eine veröffentlichte Quartalszahl mit ihrer Abweichung von der Schätzung (P2-06).

    Grundlage für die PEAD-Messung (Post-Earnings-Announcement Drift). Die
    Tabelle existiert, weil der Abruf teuer und das Ergebnis unveränderlich
    ist: rund 20.000 Ereignisse über 600 Ticker kosten einen Lauf von
    Stunden, und ein Quartalsergebnis von 2019 ändert sich nicht mehr. Ein
    TTL-Cache wie bei den Index-Aufnahmedaten wäre hier das falsche Mittel —
    er würde bei jedem Neustart erneut Stunden verbrauchen.

    `surprise_pct` ist ein Verhältnis und damit immun gegen die rückwirkende
    Split-Anpassung, die Yahoo auf `eps_actual` und `eps_estimate` anwendet:
    beide werden im selben Maß angepasst, ihr Quotient bleibt gleich. Genau
    deshalb ist die Abweichung und nicht der EPS-Betrag die Messgröße.

    **Der Zeitstempel ist der wunde Punkt.** Yahoo liefert ihn mit Uhrzeit und
    Zeitzone, aber ohne verlässliche Angabe, ob vor Handelsbeginn oder nach
    Handelsschluss berichtet wurde. Wer ein Ereignis demselben Handelstag
    zurechnet, riskiert deshalb, eine Zahl zu verwenden, die zu diesem
    Zeitpunkt noch nicht öffentlich war. Auswertungen halten daher einen
    Sicherheitsabstand ein (`pead.MIN_ABSTAND_TAGE`), statt sich auf die
    Uhrzeit zu verlassen.
    """
    __tablename__ = "earnings_events"
    __table_args__ = (
        UniqueConstraint("ticker", "datum", name="uq_earnings_ticker_datum"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    datum: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    eps_actual: Mapped[Optional[float]] = mapped_column(Float)
    eps_estimate: Mapped[Optional[float]] = mapped_column(Float)
    # (actual - estimate) / |estimate| * 100, wie von der Quelle geliefert.
    surprise_pct: Mapped[Optional[float]] = mapped_column(Float)

    quelle: Mapped[str] = mapped_column(Text, nullable=False, default="yfinance")
    geladen_am: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "datum": self.datum.isoformat() if self.datum else None,
            "eps_actual": self.eps_actual,
            "eps_estimate": self.eps_estimate,
            "surprise_pct": self.surprise_pct,
            "quelle": self.quelle,
        }


class AnalystenRevision(Base):
    """Eine Analystenhandlung: Rating-Wechsel und/oder Kurszielaenderung (P2-06).

    Zweite Signalfamilie nach PEAD, und wie dort gilt: der Wert liegt in der
    Herkunft. Eine Kurszielrevision ist aus keiner Kursreihe ableitbar.

    **Was hier NICHT steht, und warum.** Der klassische Revisionsindikator ist
    die Aenderung der Konsens-Gewinnschaetzung. Die ist bei dieser Quelle
    historisch nicht zu haben: `eps_trend`, `eps_revisions`, `earnings_estimate`
    und `recommendations` liefern samtlich nur ein rollierendes Fenster ohne
    Datumsachse (aktuell / vor 7 / 30 / 60 / 90 Tagen) und lassen sich deshalb
    nur live lesen, nie rueckwirkend. Historisch verwertbar ist allein das
    Ereignisprotokoll `upgrades_downgrades` — Rating-Wechsel und Kursziele mit
    Datum, bei US-Titeln zurueck bis 2012.

    **Die Nullfalle.** `priorPriceTarget` ist `0.0`, nicht `NULL`, wenn es kein
    Vorziel gibt — bei rund einem Fuenftel der Zeilen (Erstabdeckung, reine
    Rating-Meldungen). Wer auf `notna()` prueft, haelt diese Zeilen faelschlich
    fuer brauchbar und rechnet anschliessend gegen einen Nenner von null. Beim
    Schreiben wird die Null deshalb zu `None` gemacht: hier steht ein Kursziel
    oder gar keines.

    **Optimismus-Neigung.** Der Median der Zielrevisionen liegt bei rund
    +2 Prozent — Analysten heben haeufiger an, als sie senken. Eine absolute
    Schwelle ("Ziel um 5 Prozent erhoeht") misst deshalb ueberwiegend den
    allgemeinen Drift der Schaetzungen. Auswertungen rangen im Querschnitt.
    """
    __tablename__ = "analysten_revisionen"
    __table_args__ = (
        UniqueConstraint("ticker", "datum", "firma",
                         name="uq_revision_ticker_datum_firma"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    datum: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    firma: Mapped[str] = mapped_column(Text, nullable=False)

    # up / down / main / init / reit — Yahoos Bezeichner, unveraendert
    # uebernommen, damit eine spaetere Nachfrage an der Quelle moeglich bleibt.
    aktion: Mapped[Optional[str]] = mapped_column(Text)
    # Raises / Lowers / Maintains / Announces / Removes
    ziel_aktion: Mapped[Optional[str]] = mapped_column(Text)

    note_neu: Mapped[Optional[str]] = mapped_column(Text)
    note_alt: Mapped[Optional[str]] = mapped_column(Text)

    # None heisst "kein Kursziel", nie "Kursziel null" — siehe Nullfalle oben.
    ziel_neu: Mapped[Optional[float]] = mapped_column(Float)
    ziel_alt: Mapped[Optional[float]] = mapped_column(Float)

    quelle: Mapped[str] = mapped_column(Text, nullable=False, default="yfinance")
    geladen_am: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "datum": self.datum.isoformat() if self.datum else None,
            "firma": self.firma,
            "aktion": self.aktion,
            "ziel_aktion": self.ziel_aktion,
            "note_neu": self.note_neu,
            "note_alt": self.note_alt,
            "ziel_neu": self.ziel_neu,
            "ziel_alt": self.ziel_alt,
        }


class Setting(Base):
    """Key-Value-Store für Dashboard-Einstellungen (z.B. API-Keys)."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Settings-API (Key-Value)
# ---------------------------------------------------------------------------

def get_setting(key: str, default: Optional[str] = None) -> str | None:
    """Lädt eine Einstellung aus der Datenbank."""
    session = get_session()
    try:
        setting = session.query(Setting).filter(Setting.key == key).first()
        if setting:
            return setting.value
        return default
    except Exception:
        return default
    finally:
        session.close()


def set_setting(key: str, value: str):
    """Speichert eine Einstellung in der Datenbank (upsert)."""
    session = get_session()
    try:
        setting = session.query(Setting).filter(Setting.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            session.add(setting)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Setting '{key}' konnte nicht gespeichert werden: {e}")
    finally:
        session.close()


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
                print(f"Watchlist migriert: {len(wl_data)} Einträge")
            except Exception as e:
                print(f"Watchlist-Migration fehlgeschlagen: {e}")

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
                print(f"Journal migriert: {len(journal_data)} Einträge")
            except Exception as e:
                print(f"Journal-Migration fehlgeschlagen: {e}")

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
                print(f"Signale migriert: {len(sig_data)} Einträge")
            except Exception as e:
                print(f"Signal-Migration fehlgeschlagen: {e}")

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
                print(f"Alerts migriert: {len(alert_data)} Einträge")
            except Exception as e:
                print(f"Alert-Migration fehlgeschlagen: {e}")

        if migrated_any:
            session.commit()
            print("JSON → SQLite Migration abgeschlossen!")
        else:
            print("Keine JSON-Daten zum Migrieren gefunden.")

    except Exception as e:
        session.rollback()
        print(f"Migration fehlgeschlagen: {e}")
    finally:
        session.close()
