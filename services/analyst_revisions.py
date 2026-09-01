"""
services/analyst_revisions.py — Analystenhandlungen als Signalquelle (P2-06).

Zweite Signalfamilie nach PEAD (§2e), aus demselben Grund gewählt: die Größe
ist nicht aus Kursen ableitbar. Alles Kursbasierte ist geprüft und still.

**Was messbar ist und was nicht.** Der klassische Revisionsindikator wäre die
Änderung der Konsens-Gewinnschätzung. Sie ist bei dieser Quelle historisch
nicht zu haben — `eps_trend`, `eps_revisions`, `earnings_estimate` und
`recommendations` liefern sämtlich nur ein rollierendes Fenster (aktuell, vor
7/30/60/90 Tagen) ohne Datumsachse. Damit lassen sie sich live lesen, aber nie
rückwirkend auf einen Snapshot von 2019 beziehen. Geprüft, nicht vermutet.

Historisch verwertbar ist genau eine Quelle: `upgrades_downgrades`. Sie ist
ein Ereignisprotokoll mit Datum, Haus, Rating vorher/nachher und Kursziel
vorher/nachher — bei US-Titeln zurück bis 2012, im Schnitt rund 300 Ereignisse
je Ticker seit 2017.

**Zwei Signale, nicht eines.** Beide stecken in denselben Zeilen:

- `netto_rating` — Heraufstufungen minus Herabstufungen im Rückschaufenster.
  Sauberes Ereignis, aber selten: nur rund 16 Prozent der Zeilen tragen einen
  Rating-Wechsel, der Rest bestätigt („main", „reit").
- `ziel_revision` — mittlere prozentuale Änderung des Kursziels. Deutlich
  häufiger (rund 82 Prozent der Zeilen) und mit Betrag statt nur Richtung.
  Das ist die nähere Entsprechung zu einer Schätzungsrevision.

**Die Nullfalle.** `priorPriceTarget` ist `0.0`, nicht `NaN`, wenn es kein
Vorziel gibt. Eine Prüfung auf `notna()` hält diese Zeilen für brauchbar und
rechnet danach gegen einen Nenner von null. Beim Schreiben wird die Null
deshalb zu `None`.

**Der Zeitstempel.** Anders als bei den Quartalszahlen liefert Yahoo hier
zonenlose Zeitstempel. Die Unsicherheit vorbörslich/nachbörslich bleibt
trotzdem, weshalb `MIN_ABSTAND_TAGE` wie in `services/pead.py` Abstand hält —
eine Hochstufung wirkt am Tag ihrer Veröffentlichung am stärksten, und genau
dieser Tag ist der, an dem unklar ist, ob sie schon bekannt war.

Bestandsaufbau (einmalig, rund eine Stunde für 611 Ticker):
    py -c "import services.analyst_revisions as a; a.cli()"
"""

import logging
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database import AnalystenRevision

logger = logging.getLogger(__name__)


# Sicherheitsabstand zwischen Handlung und Snapshot, in Kalendertagen.
# Gleiche Begründung wie in `services/pead.py`.
MIN_ABSTAND_TAGE = 1

# Rückschaufenster, über das Handlungen zu einem Signal verdichtet werden.
# Ein Quartal: kurz genug, dass die Verdichtung nicht über zwei Berichtszyklen
# mittelt, lang genug, dass auch dünn abgedeckte Titel Ereignisse haben.
FENSTER_TAGE = 90

# Yahoos Bezeichner für einen echten Rating-Wechsel.
AKTION_HERAUF = "up"
AKTION_HERAB = "down"


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------

def _positiv(wert) -> Optional[float]:
    """Kursziel als Zahl, oder None — die Null ist hier kein Wert.

    Yahoo schreibt `0.0` statt `NaN`, wenn kein Vorziel existiert (etwa bei
    Erstabdeckung). Als Zahl gelesen erzeugt sie eine Revision von minus
    hundert Prozent oder eine Division durch null.
    """
    try:
        import pandas as pd
        if wert is None or pd.isna(wert):
            return None
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return zahl if zahl > 0 else None


def revisionen_laden(ticker: str) -> list[dict]:
    """Alle protokollierten Analystenhandlungen eines Tickers.

    Returns:
        Liste aus {datum, firma, aktion, ziel_aktion, note_neu, note_alt,
        ziel_neu, ziel_alt}, aufsteigend nach Datum. Leer, wenn die Quelle
        nichts liefert — bei deutschen Titeln der Normalfall.
    """
    try:
        import pandas as pd
        import yfinance as yf

        tabelle = yf.Ticker(ticker).upgrades_downgrades
    except Exception as e:
        logger.warning("Revisionen für %s nicht ladbar: %s", ticker, e)
        return []

    if tabelle is None or len(tabelle) == 0:
        return []

    erwartet = {"Firm", "ToGrade", "FromGrade", "Action"}
    if not erwartet.issubset(set(tabelle.columns)):
        logger.warning("Revisionstabelle für %s ohne erwartete Spalten (%s) — "
                       "yfinance-Struktur geändert?", ticker,
                       sorted(tabelle.columns))
        return []

    def _text(wert) -> Optional[str]:
        if wert is None or pd.isna(wert):
            return None
        text = str(wert).strip()
        return text or None

    # Wie bei den Quartalszahlen nach Schlüssel abgelegt: zwei Zeilen mit
    # gleichem Zeitstempel UND gleichem Haus wären am Unique-Index ein Abbruch,
    # der per Rollback den ganzen Ticker verwirft.
    ergebnis: dict[tuple, dict] = {}
    for zeitstempel, zeile in tabelle.iterrows():
        zeitpunkt = pd.Timestamp(zeitstempel)
        if zeitpunkt.tzinfo is not None:
            zeitpunkt = zeitpunkt.tz_localize(None)
        datum = zeitpunkt.to_pydatetime()

        firma = _text(zeile.get("Firm"))
        if firma is None:
            # Ohne Haus fehlt der dritte Teil des Schlüssels; die Zeile ließe
            # sich später nicht von einer anderen desselben Tages trennen.
            continue

        ergebnis[(datum, firma)] = {
            "datum": datum,
            "firma": firma,
            "aktion": _text(zeile.get("Action")),
            "ziel_aktion": _text(zeile.get("priceTargetAction")),
            "note_neu": _text(zeile.get("ToGrade")),
            "note_alt": _text(zeile.get("FromGrade")),
            "ziel_neu": _positiv(zeile.get("currentPriceTarget")),
            "ziel_alt": _positiv(zeile.get("priorPriceTarget")),
        }

    return [ergebnis[k] for k in sorted(ergebnis)]


# ---------------------------------------------------------------------------
# Bestandsaufbau
# ---------------------------------------------------------------------------

def revisionen_backfill(db: Session, tickers: Iterable[str],
                        ueberspringen_wenn_vorhanden: bool = True) -> dict:
    """Lädt das Handlungsprotokoll für viele Ticker in die Tabelle.

    Idempotent über den Unique-Index (ticker, datum, firma) und je Ticker
    committet — ein Abbruch kostet höchstens den laufenden Titel.

    Returns:
        {"geprueft", "abgerufen", "neu", "ohne_daten", "fehlende_ticker"}
    """
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t))

    vorhanden: set[str] = set()
    if ueberspringen_wenn_vorhanden:
        vorhanden = {
            t for (t,) in db.query(AnalystenRevision.ticker).distinct().all()
        }

    statistik: dict = {"geprueft": len(tickers), "abgerufen": 0, "neu": 0,
                       "ohne_daten": 0, "fehlende_ticker": []}

    for nummer, ticker in enumerate(tickers, start=1):
        if ticker in vorhanden:
            continue

        handlungen = revisionen_laden(ticker)
        statistik["abgerufen"] += 1

        if not handlungen:
            statistik["ohne_daten"] += 1
            statistik["fehlende_ticker"].append(ticker)
            continue

        bekannt = {
            (d, f) for d, f in db.query(AnalystenRevision.datum,
                                        AnalystenRevision.firma)
            .filter(AnalystenRevision.ticker == ticker).all()
        }

        jetzt = datetime.utcnow()
        neu = 0
        for h in handlungen:
            if (h["datum"], h["firma"]) in bekannt:
                continue
            db.add(AnalystenRevision(
                ticker=ticker, quelle="yfinance", geladen_am=jetzt, **h))
            neu += 1

        statistik["neu"] += neu

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Revisionen für %s nicht speicherbar: %s", ticker, e,
                         exc_info=True)
            statistik["fehlende_ticker"].append(ticker)

        if nummer % 25 == 0:
            logger.info("Revisions-Backfill: %d/%d Ticker, %d Handlungen neu.",
                        nummer, len(tickers), statistik["neu"])

    logger.info("Revisions-Backfill fertig: %d geprüft, %d abgerufen, "
                "%d Handlungen neu, %d ohne Daten.",
                statistik["geprueft"], statistik["abgerufen"],
                statistik["neu"], statistik["ohne_daten"])
    return statistik


# ---------------------------------------------------------------------------
# Lesen und verdichten
# ---------------------------------------------------------------------------

def zielrevision(ziel_neu: Optional[float],
                 ziel_alt: Optional[float]) -> Optional[float]:
    """Kursziel-Änderung in Prozent, oder None ohne brauchbares Paar."""
    if not ziel_neu or not ziel_alt or ziel_alt <= 0:
        return None
    return (ziel_neu / ziel_alt - 1.0) * 100.0


def handlungen_je_ticker(db: Session,
                         tickers: Optional[Iterable[str]] = None
                         ) -> dict[str, list[tuple]]:
    """Je Ticker die nach Datum sortierten Handlungen.

    Returns:
        {ticker: [(datum, aktion, zielrevision_pct), ...]}

    Einmal geladen und danach im Speicher durchsucht — dieselbe Bauweise wie
    `pead.ereignisse_je_ticker`. Ein Datenbankzugriff je Snapshot wäre bei
    180.000 Snapshots der Flaschenhals.
    """
    query = db.query(AnalystenRevision.ticker, AnalystenRevision.datum,
                     AnalystenRevision.aktion, AnalystenRevision.ziel_neu,
                     AnalystenRevision.ziel_alt)
    if tickers is not None:
        liste = [t.strip().upper() for t in tickers if t]
        if not liste:
            return {}
        query = query.filter(AnalystenRevision.ticker.in_(liste))

    reihen: dict[str, list[tuple]] = {}
    for ticker, datum, aktion, neu, alt in query.order_by(
            AnalystenRevision.ticker, AnalystenRevision.datum).all():
        if datum is None:
            continue
        reihen.setdefault(ticker, []).append(
            (datum, aktion, zielrevision(neu, alt)))
    return reihen


def fenster_verdichten(reihe: Optional[list[tuple]], zeitpunkt: datetime,
                       fenster_tage: int = FENSTER_TAGE,
                       min_abstand_tage: int = MIN_ABSTAND_TAGE
                       ) -> Optional[dict]:
    """Verdichtet die Handlungen vor einem Zeitpunkt zu zwei Kennzahlen.

    Returns:
        {"netto_rating", "anzahl_rating", "ziel_revision", "anzahl_ziel",
         "anzahl"} — oder None, wenn im Fenster keine Handlung liegt.

    `netto_rating` ist nicht normiert. Ein Titel mit zwanzig Häusern erzeugt
    mehr Handlungen als einer mit dreien, und die Normierung auf die Zahl der
    Handlungen würde genau das wegrechnen, was die Aussage trägt: dass sich
    viele Häuser gleichzeitig bewegen. Der Querschnittsrang stellt die
    Vergleichbarkeit her, nicht eine Division.

    `ziel_revision` ist der **Mittelwert** der Einzelrevisionen im Fenster, und
    zwar bewusst über die Handlungen, nicht über die Häuser: ein Haus, das
    zweimal anhebt, hat sich zweimal bewegt.
    """
    if not reihe or zeitpunkt is None:
        return None

    obergrenze = zeitpunkt - timedelta(days=min_abstand_tage)
    untergrenze = zeitpunkt - timedelta(days=fenster_tage)

    herauf = herab = 0
    revisionen: list[float] = []
    anzahl = 0

    for datum, aktion, revision in reversed(reihe):
        if datum > obergrenze:
            continue
        if datum < untergrenze:
            break
        anzahl += 1
        if aktion == AKTION_HERAUF:
            herauf += 1
        elif aktion == AKTION_HERAB:
            herab += 1
        if revision is not None:
            revisionen.append(revision)

    if anzahl == 0:
        return None

    return {
        "netto_rating": herauf - herab,
        "anzahl_rating": herauf + herab,
        "ziel_revision": (sum(revisionen) / len(revisionen)
                          if revisionen else None),
        "anzahl_ziel": len(revisionen),
        "anzahl": anzahl,
    }


# ---------------------------------------------------------------------------
# Kommandozeile
# ---------------------------------------------------------------------------

def cli() -> None:
    """Bestandsaufbau über das Snapshot-Universum, Protokoll auf der Konsole."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Fehlende Symbole meldet yfinance selbst als ERROR; bei deutschen Titeln
    # ist das der erwartete Normalfall und kein Vorfall.
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
        ergebnis = revisionen_backfill(db, tickers)
        print(f"Abgerufen: {ergebnis['abgerufen']} | "
              f"neue Handlungen: {ergebnis['neu']} | "
              f"ohne Daten: {ergebnis['ohne_daten']}")
        if ergebnis["fehlende_ticker"]:
            print("Ohne Revisionsprotokoll: "
                  + ", ".join(sorted(ergebnis["fehlende_ticker"])))
    finally:
        db.close()
