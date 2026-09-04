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
    """Ein Trade im Journal — seit der Automatisierung eine AUSGABE, keine Eingabe.

    Vorher war das Journal eine handgefuehrte Parallelaufzeichnung von etwas,
    das das System bereits wusste: die Position stand in `positions`, die
    Analyse im Snapshot, das Ergebnis im Kurs. Wer beides pflegen muss, pflegt
    am Ende keines — im Bestand standen 25 Testeintraege und kein echter Trade.

    Jetzt traegt der Nutzer die Position ein, und `services/watchlist.py`
    schreibt den Journaleintrag beim Kauf und schliesst ihn beim Verkauf.

    **Das eigentliche Ziel der Verknuepfung** ist `einstiegs_snapshot_id`: sie
    zeigt auf die NEUE_POSITION-Analyse, die die Entscheidung getragen hat.
    Erst damit wird die Frage beantwortbar, fuer die die Snapshot-Engine
    ueberhaupt gebaut wurde — nicht "wie oft trifft die Engine gegen den
    Markt", sondern **"wie sind MEINE Trades gelaufen, wenn die Engine dieses
    Signal gab"**. Diese Schleife war nie geschlossen.

    `einstiegs_analyse_alter_tage` haelt fest, wie alt diese Analyse beim Kauf
    war. Ohne die Angabe saehe eine drei Monate alte Analyse aus wie eine vom
    Kauftag, und die Auswertung waere still falsch.
    """
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

    # ── Automatisch gefuehrt (ab 2026-09-04) ─────────────────────────
    # "auto" oder "manuell". Trennt die vom Programm gefuehrten Eintraege von
    # handgeschriebenen — eine Auswertung ueber realisierte Ergebnisse darf
    # nicht beide mischen, weil nur die automatischen vollstaendig sind.
    quelle: Mapped[Optional[str]] = mapped_column(Text)
    position_id: Mapped[Optional[str]] = mapped_column(Text, index=True)

    # Die Analyse, die die Entscheidung getragen hat. Siehe Klassen-Docstring:
    # ohne sie misst die Engine nur gegen den Markt, nie gegen die eigenen
    # Trades.
    einstiegs_snapshot_id: Mapped[Optional[int]] = mapped_column(Integer)
    einstiegs_confidence: Mapped[Optional[float]] = mapped_column(Float)
    einstiegs_signal: Mapped[Optional[str]] = mapped_column(Text)
    # Alter der Analyse in Tagen zum Kaufzeitpunkt. NULL heisst "keine Analyse
    # gefunden", nicht "am selben Tag" — die Unterscheidung entscheidet, ob
    # ein Eintrag fuer die Auswertung taugt.
    einstiegs_analyse_alter_tage: Mapped[Optional[int]] = mapped_column(Integer)

    # Stop und Ziel bei Eroeffnung. Bewusst hier dupliziert und nicht nur in
    # `positions`: der initiale Stop wandert dort, sobald er nachgezogen wird,
    # und das R-Multiple braucht den urspruenglichen.
    stop_initial: Mapped[Optional[float]] = mapped_column(Float)
    ziel_initial: Mapped[Optional[float]] = mapped_column(Float)

    # Beim Abschluss berechnet.
    r_multiple: Mapped[Optional[float]] = mapped_column(Float)
    haltedauer_tage: Mapped[Optional[int]] = mapped_column(Integer)


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


class AccrualKennzahl(Base):
    """Periodenabgrenzungen eines Geschaeftsjahres, punkt-in-zeit datiert (P2-06).

    Accruals nach Sloan: (Jahresueberschuss - operativer Cashflow) /
    Bilanzsumme. Ein Gewinn, der nicht als Zahlung ankommt, ist Buchhaltung;
    die Erwartung der Literatur ist, dass hohe Abgrenzungen *schlechtere*
    Folgerenditen haben. Das Vorzeichen ist damit umgekehrt zu PEAD und den
    Analystenrevisionen — beim Lesen der Quintile ist unten gut.

    **Warum SEC und nicht yfinance.** yfinance liefert fuenf Jahres- und sieben
    Quartalsperioden, also Historie bis 2022. Fuer eine Messung ab 2017 ist das
    zu wenig.

    **Warum `companyconcept` und nicht `frames`.** Die Rahmen-Schnittstelle
    waere billiger — ein Abruf je Kennzahl und Periode fuer alle 5.700
    Unternehmen. Sie liefert aber die zuletzt berichtete Fassung, nicht die
    urspruengliche: fuer CY2020Q1 stammen nur 7,1 Prozent der Werte aus einer
    Einreichung des Jahres 2020, 84 Prozent aus 2021. Das sind
    Vergleichszahlen aus dem Folgejahr. Wer sie mit einem Aufschlag von drei
    Monaten als bekannt annimmt, misst mit Wissen, das damals ein Jahr in der
    Zukunft lag.

    `bekannt_ab` ist deshalb keine Schaetzung und kein pauschaler Aufschlag,
    sondern das spaeteste der drei Einreichungsdaten der drei Bestandteile:
    vorher war die Kennzahl nicht berechenbar. Der Median liegt bei rund 54
    Tagen nach Geschaeftsjahresende, einzelne Werte deutlich darueber, wenn
    ein Bestandteil erst spaeter ausgezeichnet wurde.
    """
    __tablename__ = "accrual_kennzahlen"
    __table_args__ = (
        UniqueConstraint("ticker", "periode_ende",
                         name="uq_accrual_ticker_periode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    cik: Mapped[Optional[str]] = mapped_column(Text)
    periode_ende: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Ab wann die Kennzahl berechenbar war — spaetestes Einreichungsdatum der
    # drei Bestandteile. Der Index sitzt hier und nicht auf periode_ende, weil
    # jede Auswertung nach diesem Datum filtert.
    bekannt_ab: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    netto_gewinn: Mapped[Optional[float]] = mapped_column(Float)
    operativer_cashflow: Mapped[Optional[float]] = mapped_column(Float)
    bilanzsumme: Mapped[Optional[float]] = mapped_column(Float)
    accrual: Mapped[Optional[float]] = mapped_column(Float)

    quelle: Mapped[str] = mapped_column(Text, nullable=False, default="sec-xbrl")
    geladen_am: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "periode_ende": self.periode_ende.isoformat() if self.periode_ende else None,
            "bekannt_ab": self.bekannt_ab.isoformat() if self.bekannt_ab else None,
            "netto_gewinn": self.netto_gewinn,
            "operativer_cashflow": self.operativer_cashflow,
            "bilanzsumme": self.bilanzsumme,
            "accrual": self.accrual,
        }


class InsiderGeschaeft(Base):
    """Ein offenes Insidergeschaeft aus SEC Form 4 (Auftrag B).

    Die Signalfamilie, die §2g offenlassen musste: yfinance'
    `insider_transactions` reicht bei allen fuenf geprueften Tickern nur bis
    September 2024 zurueck, der Trainingsteil endet aber am 2025-04-20 — der
    Holdout haette mehr Abdeckung gehabt als das Training. Quiver scheidet
    ausdruecklich aus: kein hinterlegtes Token, `/live/...`-Endpunkte ohne
    Historie, drei ungeprueft gebliebene Feldnamen.

    **Die Quelle sind die vierteljaehrlichen Form-345-Datensaetze der SEC** —
    ein ZIP je Quartal statt eines Abrufs je Einreichung. Gemessen an 2024Q1:
    67.671 Einreichungen und 111.404 Geschaefte in einer Datei von 13,9 MB.
    Der Weg ueber `submissions` + Form-4-XML haette denselben Bestand in rund
    300.000 Einzelabrufen geliefert.

    **`bekannt_ab` ist FILING_DATE, nie TRANS_DATE.** Der Meldeverzug betraegt
    im Median zwei Tage (2024Q1), im 90. Perzentil vier — aber der groesste
    gemessene Wert liegt bei **2.332 Tagen**, und sechs Zeilen tragen ein
    Einreichungsdatum VOR dem Handelstag. Wer nach `trans_datum` datiert,
    rechnet in Einzelfaellen mit Wissen, das erst sechs Jahre spaeter oeffentlich
    wurde. Der Handelstag bleibt trotzdem gespeichert: die Routine-Erkennung
    nach Cohen/Malloy/Pomorski braucht den Kalendermonat des Geschaefts.

    **`owner_cik` ist die eigentliche Neuerung gegenueber jeder frueheren
    Quelle.** Ohne die Historie je PERSON laesst sich die Trennung in
    routinemaessige und opportunistische Insider nicht bilden — und ohne sie
    misst man laut Cohen/Malloy/Pomorski (2012) ueberwiegend Rauschen:
    Routinegeschaefte tragen null, opportunistische 82 bp/Monat.

    Gespeichert werden nur `code` P und S, also Kaeufe und Verkaeufe am Markt.
    Zuteilungen (A), Optionsausuebungen (M), Steuereinbehalte (F) und
    Schenkungen (G) sind keine Entscheidung, zu diesem Kurs zu handeln.
    """
    __tablename__ = "insider_geschaefte"
    __table_args__ = (
        # NONDERIV_TRANS_SK ist der Flaechenschluessel der SEC und innerhalb
        # eines Quartals eindeutig (gemessen: 0 Doppel auf 111.404 Zeilen).
        # Ueber Quartale hinweg ist das nicht zugesichert, deshalb zusammen
        # mit der Einreichungsnummer.
        UniqueConstraint("accession", "sec_sk", name="uq_insider_accession_sk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    issuer_cik: Mapped[Optional[str]] = mapped_column(Text)
    accession: Mapped[str] = mapped_column(Text, nullable=False)
    sec_sk: Mapped[str] = mapped_column(Text, nullable=False)

    # Die meldende Person. 97,8 Prozent der Einreichungen tragen genau einen
    # Meldenden (gemessen: 66.198 von 67.671); bei Gemeinschaftsmeldungen
    # steht hier der alphabetisch erste und `mehrere_meldende` ist True.
    owner_cik: Mapped[Optional[str]] = mapped_column(Text, index=True)
    owner_name: Mapped[Optional[str]] = mapped_column(Text)
    beziehung: Mapped[Optional[str]] = mapped_column(Text)
    mehrere_meldende: Mapped[bool] = mapped_column(Boolean, default=False)

    trans_datum: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Der Index sitzt hier und nicht auf trans_datum: jede Auswertung filtert
    # nach dem Bekanntwerden. Dieselbe Begruendung wie bei AccrualKennzahl.
    bekannt_ab: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    code: Mapped[str] = mapped_column(Text, nullable=False)
    stueck: Mapped[Optional[float]] = mapped_column(Float)
    kurs: Mapped[Optional[float]] = mapped_column(Float)
    wert: Mapped[Optional[float]] = mapped_column(Float)
    # 10b5-1-Plan laut Einreichung. Erst ab 2023 verpflichtend anzukreuzen und
    # in vier Schreibweisen kodiert ('0'/'1'/'false'/'true'), deshalb optional
    # und NICHT als Routine-Kriterium verwendbar — dafuer waere die Spalte
    # ueber den halben Messzeitraum leer.
    plan_10b5_1: Mapped[Optional[bool]] = mapped_column(Boolean)

    quelle: Mapped[str] = mapped_column(Text, nullable=False, default="sec-form345")
    geladen_am: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "owner_cik": self.owner_cik,
            "owner_name": self.owner_name,
            "beziehung": self.beziehung,
            "trans_datum": self.trans_datum.isoformat() if self.trans_datum else None,
            "bekannt_ab": self.bekannt_ab.isoformat() if self.bekannt_ab else None,
            "code": self.code,
            "stueck": self.stueck,
            "kurs": self.kurs,
            "wert": self.wert,
            "plan_10b5_1": self.plan_10b5_1,
        }


class KursHistorie(Base):
    """Taegliche OHLCV-Reihe je Ticker — die Rohdaten hinter allem anderen.

    **Warum diese Tabelle existiert.** Der Backfill laedt je Ticker EINE
    Kursreihe und spielt sie ab; `calc_technical_score()` bekommt Open, High,
    Low, Close und Volume uebergeben und rechnet daraus jeden Indikator. Bis
    hierher wurde von diesen Rohdaten **nichts** festgehalten — nur das
    Ergebnis der Deutung (+1/-1) landete im Snapshot. Damit war jede spaetere
    Frage, die eine andere Aufloesung oder eine andere Kennzahl braucht, ein
    neuer Backfill mit neuen Abrufen.

    Gemessen an den Folgen: von acht Instrumenten der Einstiegsanalyse liessen
    sich genau zwei nachtraeglich stetig auswerten (Trend und SMA-Cross,
    §2h) — und nur deshalb, weil dort zufaellig `sma200_val`/`sma50_val` im
    Feld `wert` mitgeschrieben wurde. Fuer die uebrigen sechs stand nur das
    Vorzeichen im Bestand.

    Mit dieser Tabelle wird jede kuenftige Frage eine Abfrage statt eines
    Durchlaufs: eine andere Schwelle, ein neuer Indikator, echtes Volumen,
    Umsatzspitzen, Tagesspanne, Eroeffnungsluecken. Der Nachtrag kostet keinen
    zusaetzlichen Abruf — die Daten sind waehrend des Backfills ohnehin im
    Speicher.

    **Zur Anpassungsbasis.** yfinance liefert split- und dividendenbereinigte
    Kurse, und die Bereinigung bezieht sich auf den Zeitpunkt des Abrufs: nach
    einem spaeteren Split traegt dieselbe historische Zeile einen anderen Wert.
    Reihen aus verschiedenen Abrufen duerfen deshalb nicht gemischt werden.
    `angepasst` haelt fest, ob bereinigt wurde, `geladen_am` wann — und
    `services/kurshistorie.py` schreibt eine Reihe immer als Ganzes, nie
    zeilenweise ergaenzend. Genau diese Eigenschaft traegt die Split-Sicherheit
    der bestehenden Auswertungen (`auswertung/momentum.py`,
    `services/stetige_indikatoren.py`), die sie bisher aus der gemeinsamen
    Herkunft der Snapshot-Kurse ableiten mussten.

    Groessenordnung: rund 611 Ticker x ~2.400 Handelstage seit 2017.
    """
    __tablename__ = "kurs_historie"
    __table_args__ = (
        UniqueConstraint("ticker", "datum", name="uq_kurshistorie_ticker_datum"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    datum: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    eroeffnung: Mapped[Optional[float]] = mapped_column(Float)
    hoch: Mapped[Optional[float]] = mapped_column(Float)
    tief: Mapped[Optional[float]] = mapped_column(Float)
    schluss: Mapped[float] = mapped_column(Float, nullable=False)
    # Stueckzahl, nicht Umsatz in Waehrung. Nullable, weil einzelne Handelsplaetze
    # und Indizes kein Volumen liefern — das ist ein Normalfall, kein Fehler,
    # und muss von "Volumen war null" unterscheidbar bleiben.
    volumen: Mapped[Optional[float]] = mapped_column(Float)

    # Ob die Reihe split-/dividendenbereinigt geladen wurde. Siehe Docstring:
    # entscheidet, ob zwei Zeilen ueberhaupt vergleichbar sind.
    angepasst: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quelle: Mapped[str] = mapped_column(Text, nullable=False, default="yfinance")
    geladen_am: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "datum": self.datum.isoformat() if self.datum else None,
            "eroeffnung": self.eroeffnung,
            "hoch": self.hoch,
            "tief": self.tief,
            "schluss": self.schluss,
            "volumen": self.volumen,
            "angepasst": self.angepasst,
            "quelle": self.quelle,
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

# Additive Spaltenmigration. `create_all` legt fehlende TABELLEN an, aber keine
# fehlenden SPALTEN — ein neues Feld an einem bestehenden Modell bliebe sonst
# unbemerkt, bis eine Abfrage darauf zur Laufzeit scheitert. Gleiche Bauart wie
# `snapshot_engine.models._schema_migrieren`, nur fuer die Kerntabellen.
#
# Ausschliesslich ADD COLUMN, nie DROP: eine Spalte zu verlieren ist
# unumkehrbar, eine ueberfluessige kostet nichts.
_ZUSATZSPALTEN: dict[str, dict[str, str]] = {
    "journal": {
        # Ohne DEFAULT: NULL heisst "vor der Automatisierung geschrieben" und
        # ist damit von einem automatischen Eintrag unterscheidbar.
        "quelle": "TEXT",
        "position_id": "TEXT",
        "einstiegs_snapshot_id": "INTEGER",
        "einstiegs_confidence": "REAL",
        "einstiegs_signal": "TEXT",
        "einstiegs_analyse_alter_tage": "INTEGER",
        "stop_initial": "REAL",
        "ziel_initial": "REAL",
        "r_multiple": "REAL",
        "haltedauer_tage": "INTEGER",
    },
}


def _spalten_ergaenzen():
    """Ergaenzt fehlende Spalten an bestehenden Tabellen. Idempotent."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    vorhandene = set(inspector.get_table_names())
    for tabelle, spalten in _ZUSATZSPALTEN.items():
        if tabelle not in vorhandene:
            continue
        da = {c["name"] for c in inspector.get_columns(tabelle)}
        with engine.begin() as conn:
            for name, definition in spalten.items():
                if name not in da:
                    conn.execute(text(
                        f"ALTER TABLE {tabelle} ADD COLUMN {name} {definition}"))
                    print(f"[DB] Spalte {name} zu {tabelle} ergänzt.")


def init_db():
    """Erstellt alle Tabellen (falls nicht vorhanden) und migriert JSON-Daten."""
    Base.metadata.create_all(engine)
    _spalten_ergaenzen()
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
