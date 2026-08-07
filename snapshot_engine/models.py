"""
snapshot_engine/models.py — Datenbankmodelle für die Signal-Qualitäts-Engine.

Definiert das Datenmodell für die Messung der Prognose-Qualität:
  AnalyseSnapshot            → eingefrorener Analyse-Zustand zu einem Zeitpunkt
  AnalyseSnapshotIndikator   → ein Datensatz pro Einzelindikator je Snapshot
  AnalyseSnapshotOutcome     → ein Datensatz pro (Snapshot, Zeithorizont)
  SnapshotKonfiguration      → manuelle Einschluss-/Ausschluss-Overrides
  SignalBackfillJob          → Fortschritt eines historischen Backfill-Laufs
  SignalBackfillTickerStatus → Fortschritt je Ticker innerhalb eines Backfills

Nutzt die bestehende Engine/Base aus database.py — erstellt keine zweite Verbindung.

WICHTIG — Look-Ahead-Bias:
    `datenmodus` unterscheidet LIVE (alle 5 Kategorien, echte Live-Daten) von
    HISTORISCH (nur OHLCV-berechenbare Kategorien: trend/volume/oscillator).
    Fundamental- und Sentiment-Daten stammen IMMER aus der Gegenwart
    (`get_stock_details()`), unabhängig vom replayten Datum — sie dürfen daher
    NIEMALS in einem historischen Replay berechnet werden. Jeder Lesepfad
    (Auswertung, UI, CSV-Export) MUSS nach `datenmodus` unterscheiden.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Integer, Float, Text, Boolean, DateTime, ForeignKey, Index, inspect, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base, engine, get_session, get_setting, set_setting

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

class AnalyseModus:
    """Welcher Analyse-Typ wurde bewertet."""
    NEUE_POSITION = "NEUE_POSITION"        # /analysis/new — Phase 1
    # Phase 2 (später): BESTEHENDE_POSITION = "BESTEHENDE_POSITION"


class Datenmodus:
    """Datenherkunft — entscheidend für Look-Ahead-Bias-Freiheit."""
    LIVE = "LIVE"                # Alle 5 Kategorien, echte Daten von "jetzt"
    HISTORISCH = "HISTORISCH"    # Nur trend/volume/oscillator (+SMC) aus OHLCV


class ErstelltVon:
    """Provenienz eines Snapshots (Debugging + Kadenz-Logik)."""
    SCHEDULER = "SCHEDULER"
    BACKFILL = "BACKFILL"
    MANUELL = "MANUELL"
    ANALYSE_SEITE = "ANALYSE_SEITE"
    MIGRATION = "MIGRATION"


class Granularitaet:
    """Detailgrad eines Indikator-Datensatzes."""
    INDIKATOR = "INDIKATOR"      # Echter Einzelindikator (RSI, MACD, FVG, ...)
    KATEGORIE = "KATEGORIE"      # Nur Kategorie-Ebene (migrierte Altdaten)


class BackfillStatus:
    AUSSTEHEND = "AUSSTEHEND"
    LAEUFT = "LAEUFT"
    FERTIG = "FERTIG"
    FEHLER = "FEHLER"
    ZU_WENIG_HISTORIE = "ZU_WENIG_HISTORIE"
    ABGEBROCHEN = "ABGEBROCHEN"


class KonfigModus:
    EINSCHLIESSEN = "EINSCHLIESSEN"   # Zusätzlich zum Screener-Universum tracken
    AUSSCHLIESSEN = "AUSSCHLIESSEN"   # Aus dem Universum ausschließen (Blacklist)


# Auswertungs-Horizonte in Tagen. Ersetzt sowohl das alte Einzelfenster
# (zeitfenster_tage) als auch die 1W/1M/3M-Logik der abgelösten signal_history.
HORIZONTE_TAGE: tuple[int, ...] = (7, 30, 90)

# Mindest-Kursbewegung, ab der ein Outcome überhaupt als Treffer/Fehlschlag
# gewertet wird (deckt Transaktionskosten + Slippage ab; aus signal_history
# übernommen, damit migrierte und neue Daten identisch bewertet werden).
MIN_BEWEGUNG_PCT = 0.3


# ---------------------------------------------------------------------------
# ORM-Modelle
# ---------------------------------------------------------------------------

class AnalyseSnapshot(Base):
    """Eingefrorener Analyse-Zustand zu einem bestimmten Zeitpunkt.

    Ein Snapshot ist die "Prognose". Die zugehörigen AnalyseSnapshotOutcome-Zeilen
    sind das "was tatsächlich passiert ist" — bewusst getrennt, damit dieselbe
    Prognose über mehrere Zeithorizonte bewertet werden kann.
    """
    __tablename__ = "analyse_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    snapshot_zeitpunkt: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    kurs_bei_snapshot: Mapped[float] = mapped_column(Float, nullable=False)

    # Prognose
    confidence: Mapped[float] = mapped_column(Float, nullable=False)           # 0–100
    confidence_label: Mapped[Optional[str]] = mapped_column(Text)
    richtungssignal: Mapped[str] = mapped_column(Text, nullable=False)         # KAUF/NEUTRAL/VERKAUF

    # Score-Details (JSON). indikator_json enthält die 5 Kategorie-Scores;
    # cat_max_json ist nötig, um "0 = neutral bewertet" von "0 = keine Daten"
    # zu unterscheiden — kritisch bei datenmodus=HISTORISCH.
    indikator_json: Mapped[Optional[str]] = mapped_column(Text)                # cat_scores
    cat_max_json: Mapped[Optional[str]] = mapped_column(Text)
    weights_json: Mapped[Optional[str]] = mapped_column(Text)
    checklist_json: Mapped[Optional[str]] = mapped_column(Text)                # volle Checkliste

    # Klassifizierung
    analyse_modus: Mapped[str] = mapped_column(
        Text, nullable=False, default=AnalyseModus.NEUE_POSITION, index=True)
    datenmodus: Mapped[str] = mapped_column(
        Text, nullable=False, default=Datenmodus.LIVE, index=True)
    erstellt_von: Mapped[Optional[str]] = mapped_column(Text)
    backfill_job_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("signal_backfill_jobs.id", ondelete="SET NULL"), nullable=True)

    outcomes: Mapped[list["AnalyseSnapshotOutcome"]] = relationship(
        "AnalyseSnapshotOutcome", back_populates="snapshot",
        cascade="all, delete-orphan")
    indikatoren: Mapped[list["AnalyseSnapshotIndikator"]] = relationship(
        "AnalyseSnapshotIndikator", back_populates="snapshot",
        cascade="all, delete-orphan")

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
            "analyse_modus": self.analyse_modus,
            "datenmodus": self.datenmodus,
            "erstellt_von": self.erstellt_von,
            "outcomes": [o.to_dict() for o in (self.outcomes or [])],
        }


class AnalyseSnapshotIndikator(Base):
    """Ein Einzelindikator (RSI, MACD, FVG, DCF, ...) eines Snapshots.

    Normalisiert aus ScoreResult.checklist — ermöglicht Auswertung auf
    Indikator-Ebene ("funktioniert RSI überhaupt?") statt nur auf
    Kategorie-Ebene.
    """
    __tablename__ = "analyse_snapshot_indikatoren"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analyse_snapshots.id", ondelete="CASCADE"),
        nullable=False, index=True)

    indikator_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    kategorie: Mapped[Optional[str]] = mapped_column(Text, index=True)
    wert: Mapped[Optional[str]] = mapped_column(Text)
    signal_text: Mapped[Optional[str]] = mapped_column(Text)

    # Roher Beitrag-String aus scoring.py ("+1", "-0.5", "Info", "0")
    beitrag_raw: Mapped[Optional[str]] = mapped_column(Text)
    # Numerisch geparst; None bei "Info"-Indikatoren (fließen nicht in den Score)
    beitrag_numeric: Mapped[Optional[float]] = mapped_column(Float)

    granularitaet: Mapped[str] = mapped_column(
        Text, nullable=False, default=Granularitaet.INDIKATOR)

    snapshot: Mapped["AnalyseSnapshot"] = relationship(
        "AnalyseSnapshot", back_populates="indikatoren")

    def to_dict(self) -> dict:
        return {
            "indikator_name": self.indikator_name,
            "kategorie": self.kategorie,
            "wert": self.wert,
            "signal_text": self.signal_text,
            "beitrag_raw": self.beitrag_raw,
            "beitrag_numeric": self.beitrag_numeric,
            "granularitaet": self.granularitaet,
        }


class AnalyseSnapshotOutcome(Base):
    """Tatsächliches Ergebnis eines Snapshots nach `horizont_tage` Tagen.

    Eine Zeile je (Snapshot, Horizont). Das Nachtragen fälliger Outcomes ist
    dadurch eine einzige Query über diese Tabelle — unabhängig davon, zu
    welchem Snapshot sie gehören. Genau das macht sowohl den Live- als auch
    den Backfill-Lauf trivial wiederaufnehmbar.
    """
    __tablename__ = "analyse_snapshot_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analyse_snapshots.id", ondelete="CASCADE"),
        nullable=False, index=True)

    horizont_tage: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    faellig_am: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    outcome_kurs: Mapped[Optional[float]] = mapped_column(Float)
    outcome_return: Mapped[Optional[float]] = mapped_column(Float)      # in Prozent
    outcome_zeitpunkt: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ausgewertet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # None = nicht bewertbar (NEUTRAL-Signal oder Bewegung < MIN_BEWEGUNG_PCT)
    war_erfolgreich: Mapped[Optional[bool]] = mapped_column(Boolean)
    # Fehlversuche beim Nachtragen. Verhindert, dass delistete Ticker bei jedem
    # Drain-Lauf endlos erneut abgefragt werden.
    versuche: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    snapshot: Mapped["AnalyseSnapshot"] = relationship(
        "AnalyseSnapshot", back_populates="outcomes")

    def to_dict(self) -> dict:
        return {
            "horizont_tage": self.horizont_tage,
            "faellig_am": self.faellig_am.isoformat() if self.faellig_am else None,
            "outcome_kurs": self.outcome_kurs,
            "outcome_return": self.outcome_return,
            "outcome_zeitpunkt": self.outcome_zeitpunkt.isoformat() if self.outcome_zeitpunkt else None,
            "ausgewertet": self.ausgewertet,
            "war_erfolgreich": self.war_erfolgreich,
        }


# Index für die zentrale "welche Outcomes sind fällig?"-Abfrage
Index("ix_outcome_faellig", AnalyseSnapshotOutcome.ausgewertet,
      AnalyseSnapshotOutcome.faellig_am)


class SnapshotKonfiguration(Base):
    """Manuelle Overrides zum Ticker-Universum.

    Das Standard-Universum ist das Screener-Universum (S&P 500 + DAX/MDAX,
    siehe services/screener.py). Diese Tabelle ergänzt es nur:
      EINSCHLIESSEN → zusätzlich tracken (z.B. eigene Watchlist-Werte)
      AUSSCHLIESSEN → überspringen (delisted, dauerhaft schlechte Daten)
    """
    __tablename__ = "snapshot_konfiguration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    aktiv: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    modus: Mapped[str] = mapped_column(
        Text, nullable=False, default=KonfigModus.EINSCHLIESSEN)
    grund: Mapped[Optional[str]] = mapped_column(Text)
    zeitfenster_tage: Mapped[Optional[int]] = mapped_column(Integer, default=7)
    hinzugefuegt_am: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "aktiv": self.aktiv,
            "modus": self.modus,
            "grund": self.grund,
            "hinzugefuegt_am": self.hinzugefuegt_am.isoformat() if self.hinzugefuegt_am else None,
        }


class SignalLiveQueue(Base):
    """Warteschlange für den teuren Teil des Live-Laufs.

    Phase A (günstig, Batch) entscheidet, welche Ticker fällig sind, und legt
    sie hier ab. Phase B (teuer, ein Voll-Abruf je Ticker) arbeitet die
    Schlange in kleinen Häppchen ab. Dadurch bleibt der 18:30-Lauf kurz und
    der Fortschritt übersteht einen Neustart der App.
    """
    __tablename__ = "signal_live_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    eingereiht_am: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BackfillStatus.AUSSTEHEND, index=True)
    versuche: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fehlermeldung: Mapped[Optional[str]] = mapped_column(Text)
    # Technisches Richtungssignal aus Phase A — dient als Vergleichswert für
    # die Kadenz-Regel (Neu-Snapshot bei Richtungswechsel).
    richtung_gating: Mapped[Optional[str]] = mapped_column(Text)


class SignalBackfillJob(Base):
    """Ein historischer Backfill-Lauf.

    Der Fortschritt liegt bewusst in der DB (nicht im Speicher): der Drain-Job
    arbeitet je Tick nur eine begrenzte Scheibe ab, ein Neustart der App setzt
    denselben Lauf einfach fort.
    """
    __tablename__ = "signal_backfill_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BackfillStatus.AUSSTEHEND, index=True)
    gestartet_am: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    beendet_am: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Eingefrorenes Ticker-Universum — macht den Lauf deterministisch, auch wenn
    # sich das Screener-Universum während der Laufzeit ändert.
    ticker_liste_json: Mapped[Optional[str]] = mapped_column(Text)
    historie_jahre: Mapped[Optional[int]] = mapped_column(Integer, default=5)
    # SMC (FVG/EQH/EQL) kostet im Replay rund das Zehnfache an Rechenzeit
    # (~79 ms statt ~8 ms je Fenster). Mit SMC entspricht der historische
    # Trend-Score exakt dem der Live-Analyse; ohne SMC läuft der Backfill
    # deutlich schneller, weicht aber semantisch leicht ab.
    include_smc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ticker_gesamt: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    ticker_fertig: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    ticker_fehler: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    snapshots_erstellt: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    letzter_fehler: Mapped[Optional[str]] = mapped_column(Text)

    def to_dict(self) -> dict:
        gesamt = self.ticker_gesamt or 0
        erledigt = (self.ticker_fertig or 0) + (self.ticker_fehler or 0)
        return {
            "id": self.id,
            "status": self.status,
            "gestartet_am": self.gestartet_am.isoformat() if self.gestartet_am else None,
            "beendet_am": self.beendet_am.isoformat() if self.beendet_am else None,
            "historie_jahre": self.historie_jahre,
            "ticker_gesamt": gesamt,
            "ticker_fertig": self.ticker_fertig or 0,
            "ticker_fehler": self.ticker_fehler or 0,
            "snapshots_erstellt": self.snapshots_erstellt or 0,
            "fortschritt_pct": round(erledigt / gesamt * 100, 1) if gesamt else 0.0,
            "letzter_fehler": self.letzter_fehler,
        }


class SignalBackfillTickerStatus(Base):
    """Fortschritt eines einzelnen Tickers innerhalb eines Backfill-Laufs."""
    __tablename__ = "signal_backfill_ticker_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("signal_backfill_jobs.id", ondelete="CASCADE"),
        nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BackfillStatus.AUSSTEHEND, index=True)
    snapshots_erstellt: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    fehlermeldung: Mapped[Optional[str]] = mapped_column(Text)
    bearbeitet_am: Mapped[Optional[datetime]] = mapped_column(DateTime)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def beitrag_parsen(beitrag_raw) -> Optional[float]:
    """Parst den Beitrag-String aus scoring.py ("+1", "-0.5", "0", "Info").

    Returns:
        Float-Wert, oder None wenn der Indikator rein informativ ist
        (fließt dann nicht in die Score-Attribution ein).
    """
    if beitrag_raw is None:
        return None
    text_wert = str(beitrag_raw).strip().replace("+", "")
    if not text_wert:
        return None
    try:
        return float(text_wert)
    except ValueError:
        return None  # "Info" und Ähnliches


def erfolg_bewerten(richtungssignal: str, kurs_start: float,
                    kurs_ende: float) -> Optional[bool]:
    """Bewertet, ob ein Richtungssignal eingetroffen ist.

    NEUTRAL wird bewusst nie bewertet. Bewegungen unter MIN_BEWEGUNG_PCT
    gelten als Rauschen und bleiben unbewertet (None).
    """
    if not kurs_start or kurs_start <= 0 or not kurs_ende:
        return None
    if richtungssignal not in ("KAUF", "VERKAUF"):
        return None

    veraenderung_pct = abs((kurs_ende - kurs_start) / kurs_start) * 100
    if veraenderung_pct < MIN_BEWEGUNG_PCT:
        return None

    if richtungssignal == "KAUF":
        return kurs_ende > kurs_start
    return kurs_ende < kurs_start


def outcomes_anlegen(snapshot: AnalyseSnapshot,
                     horizonte: tuple[int, ...] = HORIZONTE_TAGE
                     ) -> list[AnalyseSnapshotOutcome]:
    """Erzeugt die (noch offenen) Outcome-Zeilen für einen Snapshot."""
    return [
        AnalyseSnapshotOutcome(
            snapshot=snapshot,
            horizont_tage=h,
            faellig_am=snapshot.snapshot_zeitpunkt + timedelta(days=h),
            ausgewertet=False,
        )
        for h in horizonte
    ]


# ---------------------------------------------------------------------------
# Initialisierung
# ---------------------------------------------------------------------------

def init_snapshot_db():
    """Erstellt/migriert alle Tabellen der Signal-Qualitäts-Engine.

    Reihenfolge ist zwingend:
      1. Schema-Migration (Altbestand anpassen, BEVOR create_all läuft)
      2. create_all (fehlende Tabellen anlegen)
      3. Einmalige Datenmigration aus der abgelösten signal_history
    """
    _schema_migrieren()
    Base.metadata.create_all(engine)
    logger.info("Signal-Engine: Tabellen geprüft/erstellt.")
    _konfiguration_initialisieren()
    _migrate_legacy_signal_data()


def _schema_migrieren():
    """Passt bestehende Tabellen an das neue Schema an.

    Es gibt kein Alembic im Projekt und `create_all()` fügt bestehenden
    Tabellen keine Spalten hinzu — daher hier von Hand:

      analyse_snapshots      → wird neu aufgebaut (enthielt nur eine
                               Wegwerf-Testzeile und trüge sonst tote
                               Einzel-Horizont-Spalten mit sich herum)
      snapshot_konfiguration → enthält echte Daten, daher additive
                               ALTER TABLE ADD COLUMN
    """
    inspector = inspect(engine)
    vorhandene_tabellen = set(inspector.get_table_names())

    # ── analyse_snapshots: Altschema erkennen und neu aufbauen ──────
    if "analyse_snapshots" in vorhandene_tabellen:
        spalten = {c["name"] for c in inspector.get_columns("analyse_snapshots")}
        if "datenmodus" not in spalten:
            with engine.begin() as conn:
                anzahl = conn.execute(
                    text("SELECT COUNT(*) FROM analyse_snapshots")).scalar() or 0
                conn.execute(text("DROP TABLE analyse_snapshots"))
            logger.warning(
                "Signal-Engine: Altes analyse_snapshots-Schema entfernt "
                "(%d Testzeile(n) verworfen) — wird neu aufgebaut.", anzahl)

    # ── Spalten additiv ergänzen (Daten bleiben erhalten) ───────────
    additive_spalten = {
        "snapshot_konfiguration": {
            "modus": f"TEXT DEFAULT '{KonfigModus.EINSCHLIESSEN}'",
            "grund": "TEXT",
        },
        "analyse_snapshot_outcomes": {
            "versuche": "INTEGER DEFAULT 0",
        },
        "signal_backfill_jobs": {
            "include_smc": "BOOLEAN DEFAULT 1",
        },
    }
    for tabelle, spalten_definitionen in additive_spalten.items():
        if tabelle not in vorhandene_tabellen:
            continue
        spalten = {c["name"] for c in inspector.get_columns(tabelle)}
        with engine.begin() as conn:
            for name, definition in spalten_definitionen.items():
                if name not in spalten:
                    conn.execute(text(
                        f"ALTER TABLE {tabelle} ADD COLUMN {name} {definition}"))
                    logger.info("Signal-Engine: Spalte %s zu %s ergänzt.", name, tabelle)


def _konfiguration_initialisieren():
    """Setzt `modus` für Altbestände und seedet einmalig aus watchlist.json.

    Das Ticker-Universum kommt inzwischen aus dem Screener (S&P 500 +
    DAX/MDAX); diese Tabelle ergänzt es nur noch um manuelle Overrides.
    """
    session = get_session()
    try:
        # Altbestände ohne modus auf EINSCHLIESSEN setzen
        ohne_modus = session.query(SnapshotKonfiguration).filter(
            SnapshotKonfiguration.modus.is_(None)).all()
        for eintrag in ohne_modus:
            eintrag.modus = KonfigModus.EINSCHLIESSEN
        if ohne_modus:
            session.commit()
            logger.info("Signal-Engine: %d Konfigurations-Einträge auf EINSCHLIESSEN gesetzt.",
                        len(ohne_modus))

        if session.query(SnapshotKonfiguration).count() > 0:
            return  # Bereits befüllt

        watchlist_pfad = Path(__file__).parent.parent / "data" / "watchlist.json"
        if not watchlist_pfad.exists():
            return

        try:
            with open(watchlist_pfad, "r", encoding="utf-8") as f:
                watchlist_daten = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Signal-Engine: watchlist.json nicht lesbar: %s", e)
            return

        anzahl = 0
        for eintrag in watchlist_daten:
            ticker = (eintrag.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            session.add(SnapshotKonfiguration(
                ticker=ticker,
                aktiv=True,
                modus=KonfigModus.EINSCHLIESSEN,
                grund="Aus watchlist.json initialisiert",
                hinzugefuegt_am=datetime.utcnow(),
            ))
            anzahl += 1

        session.commit()
        logger.info("Signal-Engine: %d Ticker aus watchlist.json übernommen.", anzahl)

    except Exception as e:
        session.rollback()
        logger.error("Signal-Engine: Konfigurations-Initialisierung fehlgeschlagen: %s",
                     e, exc_info=True)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Einmalige Migration aus der abgelösten signal_history
# ---------------------------------------------------------------------------

_MIGRATIONS_FLAG = "signal_engine_migrated_v2"

# signal_type (5-stufig) → richtungssignal (3-stufig)
_SIGNALTYP_MAPPING = {
    "buy": "KAUF",
    "watch": "KAUF",
    "hold": "NEUTRAL",
    "avoid": "VERKAUF",
    "sell": "VERKAUF",
}

# SignalRecord-Spalte → Horizont in Tagen
_LEGACY_HORIZONTE = (
    ("price_1w_later", 7),
    ("price_1m_later", 30),
    ("price_3m_later", 90),
)


def _migrate_legacy_signal_data():
    """Übernimmt die Altdaten aus der `signals`-Tabelle (SignalRecord).

    Läuft genau einmal, abgesichert über einen Setting-Flag — analog zu
    database.py::_migrate_json_if_needed().

    Die Altdaten kennen nur Kategorie-Scores, nie die volle Indikator-
    Checkliste. Sie werden daher mit granularitaet=KATEGORIE markiert, damit
    die Auswertung sie nicht fälschlich als Einzelindikator-Evidenz zählt.
    """
    if get_setting(_MIGRATIONS_FLAG):
        return

    from database import SignalRecord

    session = get_session()
    try:
        alt_signale = session.query(SignalRecord).all()
        if not alt_signale:
            set_setting(_MIGRATIONS_FLAG, datetime.utcnow().isoformat(timespec="seconds"))
            logger.info("Signal-Engine: Keine Altdaten zu migrieren.")
            return

        migriert = 0
        outcomes_gesamt = 0

        for alt in alt_signale:
            zeitpunkt = _zeitstempel_parsen(alt.timestamp)
            if zeitpunkt is None:
                continue

            kurs = alt.price_at_signal or 0.0
            if kurs <= 0:
                continue  # Ohne Einstiegskurs ist kein Return berechenbar

            richtung = _SIGNALTYP_MAPPING.get(
                (alt.signal_type or "hold").lower(), "NEUTRAL")

            snapshot = AnalyseSnapshot(
                ticker=(alt.ticker or "").upper(),
                snapshot_zeitpunkt=zeitpunkt,
                kurs_bei_snapshot=kurs,
                confidence=alt.confidence if alt.confidence is not None else 50.0,
                confidence_label=alt.confidence_label,
                richtungssignal=richtung,
                indikator_json=alt.cat_scores_json,
                cat_max_json=alt.cat_max_json,
                weights_json=alt.weights_json,
                checklist_json=alt.contributing_factors_json,
                analyse_modus=AnalyseModus.NEUE_POSITION,
                datenmodus=Datenmodus.LIVE,   # Altdaten stammen aus Live-Läufen
                erstellt_von=ErstelltVon.MIGRATION,
            )
            session.add(snapshot)

            # Kategorie-Scores als grob granulare Indikator-Zeilen
            for kategorie, score in _json_dict_laden(alt.cat_scores_json).items():
                numerisch = _als_float(score)
                if numerisch is None:
                    continue
                session.add(AnalyseSnapshotIndikator(
                    snapshot=snapshot,
                    indikator_name=kategorie,
                    kategorie=kategorie,
                    beitrag_raw=str(score),
                    beitrag_numeric=numerisch,
                    granularitaet=Granularitaet.KATEGORIE,
                ))

            # Bereits ausgewertete Horizonte übernehmen
            for spalte, horizont in _LEGACY_HORIZONTE:
                outcome_kurs = getattr(alt, spalte, None)
                outcome = AnalyseSnapshotOutcome(
                    snapshot=snapshot,
                    horizont_tage=horizont,
                    faellig_am=zeitpunkt + timedelta(days=horizont),
                    ausgewertet=False,
                )
                if outcome_kurs:
                    outcome.outcome_kurs = outcome_kurs
                    outcome.outcome_return = round(
                        (outcome_kurs - kurs) / kurs * 100, 2)
                    outcome.outcome_zeitpunkt = zeitpunkt + timedelta(days=horizont)
                    outcome.ausgewertet = True
                    outcome.war_erfolgreich = erfolg_bewerten(
                        richtung, kurs, outcome_kurs)
                    outcomes_gesamt += 1
                session.add(outcome)

            migriert += 1

        session.commit()
        set_setting(_MIGRATIONS_FLAG, datetime.utcnow().isoformat(timespec="seconds"))
        logger.info(
            "Signal-Engine: %d Altsignale migriert (%d bereits ausgewertete Outcomes).",
            migriert, outcomes_gesamt)

    except Exception as e:
        session.rollback()
        logger.error("Signal-Engine: Migration der Altdaten fehlgeschlagen: %s",
                     e, exc_info=True)
    finally:
        session.close()


def _zeitstempel_parsen(wert) -> Optional[datetime]:
    """Parst den ISO-Zeitstempel der Altdaten (als Text gespeichert)."""
    if not wert:
        return None
    if isinstance(wert, datetime):
        return wert
    try:
        return datetime.fromisoformat(str(wert))
    except ValueError:
        return None


def _json_dict_laden(rohwert) -> dict:
    """Lädt ein JSON-Dict defensiv (Altdaten können leer/kaputt sein)."""
    if not rohwert:
        return {}
    try:
        daten = json.loads(rohwert)
        return daten if isinstance(daten, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _als_float(wert) -> Optional[float]:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None
