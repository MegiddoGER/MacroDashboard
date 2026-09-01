"""
services/pead.py — Quartalszahlen als Signalquelle (P2-06, PEAD).

Post-Earnings-Announcement Drift ist die Beobachtung, dass ein Kurs nach einer
positiven Ergebnisüberraschung noch Wochen weiterläuft, statt die Nachricht
sofort vollständig einzupreisen. Für diese Engine ist daran das Entscheidende
**nicht** die Hypothese, sondern die Herkunft der Größe: `surprise_pct` ist
aus keiner Kursreihe ableitbar.

Das ist der Grund, aus dem PEAD überhaupt gemessen wird. Alles bisher
Geprüfte — sechzehn Indikator-Richtungen, fünf Kategorien, das
Oszillator-Gate, Querschnitts-Momentum, die Sektortrennung — war kursbasiert
und hat gegen den Markt nichts getragen. Eine weitere Kursformel würde diese
Reihe fortsetzen; eine fundamentale Größe kann sie wenigstens beenden.

**Warum eine eigene Tabelle und nicht `services/earnings.py`.**
`earnings.py` versorgt die Oberfläche: es lädt ein Profil je Ticker im
Request, hält es zehn Minuten im Cache und liest dabei `tk.earnings_dates`
ohne `limit` — Yahoos Vorgabe sind dann rund zwölf Quartale. Genau daher
stammen die 981 Snapshots mit Earnings-Zeile im Bestand (0,4 %): der
Backfill kennt kein Sentiment, und das Live-Feld reicht nicht weit zurück.
Für eine Messung über 2017–2026 braucht es beides anders — `limit=100` reicht
je nach Titel bis 2002, und das Ergebnis muss persistent sein, weil der Lauf
über 600 Ticker Stunden dauert und ein Quartalsergebnis von 2019 sich nicht
mehr ändert.

**Der Zeitstempel ist die eigentliche Falle.** Yahoo liefert Datum und
Uhrzeit, aber keine belastbare Angabe, ob vor Handelsbeginn oder nach
Handelsschluss berichtet wurde. Ein Snapshot vom selben Tag hätte eine
nachbörslich veröffentlichte Zahl noch nicht kennen können — sie trotzdem zu
verwenden wäre Look-ahead, und zwar genau an der Stelle, an der der Effekt
sitzt: die erste Kursreaktion. `MIN_ABSTAND_TAGE` hält deshalb Abstand,
statt der Uhrzeit zu vertrauen.

Bestandsaufbau (einmalig, rund eine Stunde für 611 Ticker):
    py -c "import services.pead as p; p.cli()"
"""

import logging
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database import EarningsEvent

logger = logging.getLogger(__name__)


# Wie viele Quartale je Ticker angefragt werden. Yahoos Vorgabe liegt bei
# rund zwölf; mit 100 reicht die Reihe bei US-Titeln bis 2002 zurück und
# deckt den Snapshot-Bestand (ab 2017) vollständig ab.
ABRUF_LIMIT = 100

# Mindestabstand zwischen Veröffentlichung und Snapshot, in Kalendertagen.
# Ein Tag genügt: die Unsicherheit betrifft nur die Frage vorbörslich/
# nachbörslich innerhalb DESSELBEN Tages. Zwei Tage würden zusätzlich die
# erste Handelssitzung nach der Zahl ausschließen — die gehört aber zum
# Messgegenstand und nicht zur Unsicherheit.
MIN_ABSTAND_TAGE = 1

# Ab hier gilt ein Ereignis als zu alt, um noch nachzuwirken. Die Literatur
# verortet den Drift bei rund 60 Handelstagen; 120 Kalendertage lassen Raum
# darüber hinaus, damit das Abklingen messbar bleibt statt abgeschnitten zu
# werden.
MAX_ALTER_TAGE = 120


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------

def earnings_laden(ticker: str, limit: int = ABRUF_LIMIT) -> list[dict]:
    """Alle berichteten Quartale eines Tickers mit ihrer Abweichung.

    Returns:
        Liste aus {datum, eps_actual, eps_estimate, surprise_pct}, aufsteigend
        nach Datum. Leer, wenn die Quelle nichts liefert — das ist bei
        Auslandsnotierungen der Normalfall und kein Fehler (siehe
        `fehlende_ticker`).
    """
    try:
        import pandas as pd
        import yfinance as yf

        tabelle = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    except Exception as e:
        logger.warning("Earnings für %s nicht ladbar: %s", ticker, e)
        return []

    if tabelle is None or len(tabelle) == 0:
        return []

    spalten = set(tabelle.columns)
    erwartet = {"Reported EPS", "EPS Estimate", "Surprise(%)"}
    if not erwartet.issubset(spalten):
        logger.warning("Earnings-Tabelle für %s ohne erwartete Spalten (%s) — "
                       "yfinance-Struktur geändert?", ticker, sorted(spalten))
        return []

    # Nach Zeitstempel abgelegt statt in einer Liste: Yahoo liefert für
    # manche Titel zwei Zeilen mit identischem Zeitstempel — bei CSCO etwa
    # zweimal den 2002-08-06. Welche davon die richtige ist, lässt sich von
    # außen nicht entscheiden; die spätere gewinnt, weil sie einer Korrektur
    # entspräche. Ohne diese Zusammenführung bricht der Bestandsaufbau am
    # Unique-Index ab und verwirft per Rollback den gesamten Ticker.
    ergebnis: dict[datetime, dict] = {}
    for zeitstempel, zeile in tabelle.iterrows():
        # Ohne berichtetes EPS ist die Zeile ein Termin, kein Ereignis.
        actual = zeile.get("Reported EPS")
        if pd.isna(actual):
            continue
        surprise = zeile.get("Surprise(%)")
        if pd.isna(surprise):
            continue

        datum = pd.Timestamp(zeitstempel)
        # Zeitzone abstreifen: die Snapshot-Zeitpunkte sind naiv, und ein
        # Vergleich zwischen naiv und bewusst wirft. Die Uhrzeit selbst wird
        # ohnehin nicht ausgewertet — dafür gibt es MIN_ABSTAND_TAGE.
        if datum.tzinfo is not None:
            datum = datum.tz_localize(None)

        schaetzung = zeile.get("EPS Estimate")
        schluessel = datum.to_pydatetime()
        ergebnis[schluessel] = {
            "datum": schluessel,
            "eps_actual": float(actual),
            "eps_estimate": None if pd.isna(schaetzung) else float(schaetzung),
            "surprise_pct": float(surprise),
        }

    return [ergebnis[k] for k in sorted(ergebnis)]


# ---------------------------------------------------------------------------
# Bestandsaufbau
# ---------------------------------------------------------------------------

def earnings_backfill(db: Session, tickers: Iterable[str],
                      limit: int = ABRUF_LIMIT,
                      ueberspringen_wenn_vorhanden: bool = True) -> dict:
    """Lädt die Earnings-Historie für viele Ticker in die Tabelle.

    Idempotent über den Unique-Index (ticker, datum): ein zweiter Lauf fügt
    nichts doppelt ein. Das ist Absicht — der Lauf dauert Stunden und muss
    nach einem Abbruch fortsetzbar sein, ohne den Bestand zu verdoppeln.

    Args:
        ueberspringen_wenn_vorhanden: Ticker, für die bereits Zeilen
            existieren, gar nicht erst abrufen. Für den Wiederaufnahmefall.
            Auf False setzen, um einen bestehenden Bestand aufzufrischen.

    Returns:
        {"geprueft", "abgerufen", "neu", "ohne_daten", "fehlende_ticker"}
    """
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t))

    vorhanden: set[str] = set()
    if ueberspringen_wenn_vorhanden:
        vorhanden = {
            t for (t,) in db.query(EarningsEvent.ticker).distinct().all()
        }

    # Annotiert, weil die Werte gemischt sind (Zähler und Ticker-Liste) und
    # mypy sonst auf `object` schließt.
    statistik: dict = {"geprueft": len(tickers), "abgerufen": 0, "neu": 0,
                       "ohne_daten": 0, "fehlende_ticker": []}

    for nummer, ticker in enumerate(tickers, start=1):
        if ticker in vorhanden:
            continue

        ereignisse = earnings_laden(ticker, limit=limit)
        statistik["abgerufen"] += 1

        if not ereignisse:
            statistik["ohne_daten"] += 1
            statistik["fehlende_ticker"].append(ticker)
            continue

        # Bereits gespeicherte Zeitpunkte dieses Tickers, damit der
        # Auffrischungslauf nicht auf Integritätsfehler läuft.
        bekannt = {
            d for (d,) in db.query(EarningsEvent.datum)
            .filter(EarningsEvent.ticker == ticker).all()
        }

        jetzt = datetime.utcnow()
        neu = 0
        for e in ereignisse:
            if e["datum"] in bekannt:
                continue
            db.add(EarningsEvent(
                ticker=ticker,
                datum=e["datum"],
                eps_actual=e["eps_actual"],
                eps_estimate=e["eps_estimate"],
                surprise_pct=e["surprise_pct"],
                quelle="yfinance",
                geladen_am=jetzt,
            ))
            neu += 1

        statistik["neu"] += neu

        # Je Ticker committen: nach einem Abbruch ist alles bis dahin sicher.
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Earnings für %s nicht speicherbar: %s", ticker, e,
                         exc_info=True)
            statistik["fehlende_ticker"].append(ticker)

        if nummer % 25 == 0:
            logger.info("Earnings-Backfill: %d/%d Ticker, %d Ereignisse neu.",
                        nummer, len(tickers), statistik["neu"])

    logger.info("Earnings-Backfill fertig: %d Ticker geprüft, %d abgerufen, "
                "%d Ereignisse neu, %d ohne Daten.",
                statistik["geprueft"], statistik["abgerufen"],
                statistik["neu"], statistik["ohne_daten"])
    return statistik


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------

def ereignisse_je_ticker(db: Session,
                         tickers: Optional[Iterable[str]] = None
                         ) -> dict[str, list[tuple[datetime, float]]]:
    """Je Ticker die nach Datum sortierten (Zeitpunkt, Abweichung).

    Wird einmal am Anfang einer Auswertung geladen und dann im Speicher
    durchsucht — dieselbe Bauweise wie `auswertung/momentum._kursreihen`.
    Ein Datenbankzugriff je Snapshot wäre bei 180.000 Snapshots der
    Flaschenhals der gesamten Messung.
    """
    query = db.query(EarningsEvent.ticker, EarningsEvent.datum,
                     EarningsEvent.surprise_pct)
    if tickers is not None:
        liste = [t.strip().upper() for t in tickers if t]
        if not liste:
            return {}
        query = query.filter(EarningsEvent.ticker.in_(liste))

    reihen: dict[str, list[tuple[datetime, float]]] = {}
    for ticker, datum, surprise in query.order_by(EarningsEvent.ticker,
                                                  EarningsEvent.datum).all():
        if datum is None or surprise is None:
            continue
        reihen.setdefault(ticker, []).append((datum, surprise))
    return reihen


def letztes_ereignis_vor(reihe: Optional[list[tuple[datetime, float]]],
                         zeitpunkt: datetime,
                         min_abstand_tage: int = MIN_ABSTAND_TAGE,
                         max_alter_tage: int = MAX_ALTER_TAGE
                         ) -> Optional[tuple[datetime, float, int]]:
    """Die jüngste Veröffentlichung, die zum Zeitpunkt sicher bekannt war.

    Returns:
        (Datum, Abweichung in Prozent, Alter in Kalendertagen) — oder None,
        wenn keine Zahl im Fenster liegt.

    Zwei Grenzen, beide notwendig:

    - `min_abstand_tage` schneidet nach vorn ab. Ohne ihn geriete eine
      nachbörslich veröffentlichte Zahl in einen Snapshot desselben Tages,
      der sie nicht kennen konnte — Look-ahead an genau der Stelle, an der
      die Kursreaktion am größten ist.
    - `max_alter_tage` schneidet nach hinten ab. Ohne ihn trüge jeder
      Snapshot irgendein Ereignis, notfalls eines von vor fünf Monaten, und
      die Messung vergliche nicht mehr Drift gegen Nicht-Drift, sondern nur
      noch alte Überraschungen gegen sehr alte.
    """
    if not reihe or zeitpunkt is None:
        return None

    obergrenze = zeitpunkt - timedelta(days=min_abstand_tage)
    untergrenze = zeitpunkt - timedelta(days=max_alter_tage)

    # Rückwärts, weil das gesuchte Ereignis am Ende der sortierten Reihe liegt.
    for datum, surprise in reversed(reihe):
        if datum > obergrenze:
            continue
        if datum < untergrenze:
            return None
        return (datum, surprise, (zeitpunkt - datum).days)
    return None


# ---------------------------------------------------------------------------
# Kommandozeile
# ---------------------------------------------------------------------------

def cli() -> None:
    """Bestandsaufbau über das Snapshot-Universum, mit Protokoll auf der Konsole.

    Steht hier und nicht in `backfill_cli.py`: jener Lauf erzeugt Snapshots und
    hat eine eigene Fortschrittsverwaltung in der Datenbank. Dieser lädt
    Stammdaten und ist über den Unique-Index von sich aus wiederaufnehmbar —
    zwei verschiedene Aufgaben, die sich ein Skript nicht teilen sollten.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # yfinance meldet fehlende Symbole selbst als ERROR; das ist hier der
    # erwartete Normalfall (Auslandsnotierungen) und kein Vorfall.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    from database import get_session
    from snapshot_engine.models import AnalyseModus, AnalyseSnapshot

    db = get_session()
    try:
        tickers = [
            t for (t,) in db.query(AnalyseSnapshot.ticker)
            .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
            .distinct().all()
        ]
        print(f"Universum: {len(tickers)} Ticker.")
        ergebnis = earnings_backfill(db, tickers)
        print(f"Abgerufen: {ergebnis['abgerufen']} | "
              f"neue Ereignisse: {ergebnis['neu']} | "
              f"ohne Daten: {ergebnis['ohne_daten']}")
        if ergebnis["fehlende_ticker"]:
            print("Ohne Earnings-Historie: "
                  + ", ".join(sorted(ergebnis["fehlende_ticker"])))
    finally:
        db.close()
