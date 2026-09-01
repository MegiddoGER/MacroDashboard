"""
services/accruals.py — Periodenabgrenzungen als Signalquelle (P2-06).

Dritte Signalfamilie nach PEAD (§2e) und den Analystenrevisionen (§2f), und
die erste, die den Kurs gar nicht berühren kann: Accruals entstehen aus
Jahresabschluss und Kapitalflussrechnung.

    accrual = (Jahresüberschuss − operativer Cashflow) / Bilanzsumme

Ein Gewinn, der nicht als Zahlung ankommt, ist Buchhaltung. Die Erwartung der
Literatur (Sloan 1996) ist, dass hohe Abgrenzungen **schlechtere** Folgerenditen
haben. **Das Vorzeichen ist damit umgekehrt** zu PEAD und den Revisionen — beim
Lesen der Quintile ist unten gut. Wer das verwechselt, liest einen bestätigten
Befund als Widerlegung.

**Warum die SEC und nicht yfinance.** yfinance liefert fünf Jahres- und sieben
Quartalsperioden — Historie bis 2022. Für eine Messung ab 2017 zu wenig. Die
XBRL-Schnittstellen der SEC reichen weit zurück, brauchen keinen Schlüssel und
verlangen nur einen aussagekräftigen `User-Agent` (`config.SEC_USER_AGENT`).

**Warum `companyconcept` und nicht `frames`.** `frames` wäre um Größenordnungen
billiger: ein Abruf liefert eine Kennzahl für alle rund 5.700 Unternehmen einer
Periode. Gemessen ist die Schnittstelle für diesen Zweck aber unbrauchbar — sie
liefert die zuletzt berichtete Fassung. Für `CY2020Q1` stammen nur **7,1 %** der
Werte aus einer Einreichung von 2020 und **84 %** aus 2021, also aus der
Vergleichsspalte des Folgejahres. Ein pauschaler Aufschlag von drei Monaten
würde damit bei vier Fünfteln der Daten Wissen verwenden, das seinerzeit ein
Jahr in der Zukunft lag. `companyconcept` kostet einen Abruf je Unternehmen und
Kennzahl, trägt dafür `filed` an jeder einzelnen Zahl.

**Jahres- statt Quartalswerte.** Gemessen: der operative Cashflow wird
überwiegend kumuliert übers Geschäftsjahr berichtet, weshalb nur das erste
Quartal eine Dreimonatsdauer trägt — je Ticker blieben rund acht statt
achtunddreißig verwertbare Quartale. Die Jahresform braucht keine
Differenzbildung, ist die Form der Literatur und liefert rund zehn saubere
Beobachtungen je Titel seit 2016.

**Kein pauschaler Sicherheitsabstand.** `bekannt_ab` ist das **späteste** der
drei Einreichungsdaten: vorher war die Kennzahl nicht berechenbar. Median rund
54 Tage nach Geschäftsjahresende; einzelne Werte liegen deutlich darüber, wenn
ein Bestandteil erst später ausgezeichnet wurde. Diese Fälle werden dadurch
korrekt spät verfügbar, statt durch einen festen Aufschlag zu früh.

Bestandsaufbau (einmalig, rund zehn Minuten):
    py -c "import services.accruals as a; a.cli()"
"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database import AccrualKennzahl

logger = logging.getLogger(__name__)


TICKER_KARTE_URL = "https://www.sec.gov/files/company_tickers.json"
KONZEPT_URL = ("https://data.sec.gov/api/xbrl/companyconcept/"
               "CIK{cik}/us-gaap/{konzept}.json")

# Die SEC bittet um höchstens zehn Anfragen je Sekunde. Der Abstand ist
# großzügiger gewählt — ein Sperrfall kostet mehr als die gesparte Minute.
ABSTAND_SEKUNDEN = 0.12

# Je Bestandteil mehrere Auszeichnungen, in der Reihenfolge ihrer Verbreitung.
# Nicht jeder Filer verwendet dieselbe: Banken und Versicherer weichen
# regelmäßig ab, weshalb ein Teil des Universums ohne Kennzahl bleibt.
KONZEPTE_GEWINN = ("NetIncomeLoss", "ProfitLoss")
KONZEPTE_CASHFLOW = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
)
KONZEPTE_BILANZSUMME = ("Assets",)

# Als Jahresgröße gilt eine Dauer in diesem Bereich. 350–385 Tage fängt sowohl
# das 52/53-Wochen-Geschäftsjahr des Einzelhandels als auch Schaltjahre ein,
# ohne Halbjahres- oder Neunmonatswerte hereinzulassen.
JAHRESDAUER = (350, 385)

# Sicherheitsabstand zwischen Bekanntwerden und Snapshot, in Kalendertagen —
# wie in `services/pead.py`, aus demselben Grund: das Einreichungsdatum trägt
# keine Uhrzeit.
MIN_ABSTAND_TAGE = 1

# Ab diesem Alter gilt ein Abschluss als überholt. Zwei Jahre lassen Raum für
# verspätete Einreichungen, ohne dass ein Titel dauerhaft an einer Zahl von
# 2019 gemessen wird, weil er seither nichts Auswertbares veröffentlicht hat.
MAX_ALTER_TAGE = 730


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------

def _kopfzeilen() -> dict:
    import config
    return {"User-Agent": config.SEC_USER_AGENT,
            "Accept-Encoding": "gzip, deflate"}


def cik_zuordnung() -> dict[str, str]:
    """Ticker → zehnstellige CIK, aus dem Verzeichnis der SEC.

    Returns:
        Leeres Dict, wenn das Verzeichnis nicht ladbar war. Der Aufrufer
        unterscheidet das von „Ticker nicht enthalten" — Letzteres ist der
        Normalfall für jede Auslandsnotierung.
    """
    import requests

    try:
        antwort = requests.get(TICKER_KARTE_URL, headers=_kopfzeilen(), timeout=60)
        antwort.raise_for_status()
        eintraege = antwort.json()
    except Exception as e:
        logger.error("SEC-Tickerverzeichnis nicht ladbar: %s", e, exc_info=True)
        return {}

    karte = {}
    for eintrag in eintraege.values():
        symbol = str(eintrag.get("ticker", "")).strip().upper()
        cik = eintrag.get("cik_str")
        if symbol and cik is not None:
            karte[symbol] = str(cik).zfill(10)
    logger.info("SEC-Tickerverzeichnis: %d Symbole.", len(karte))
    return karte


def _konzept_laden(cik: str, konzept: str) -> list[dict]:
    """Alle US-Dollar-Fakten eines Unternehmens zu einer Auszeichnung."""
    import requests

    try:
        antwort = requests.get(KONZEPT_URL.format(cik=cik, konzept=konzept),
                               headers=_kopfzeilen(), timeout=60)
    except Exception as e:
        logger.warning("SEC-Abruf %s/%s fehlgeschlagen: %s", cik, konzept, e)
        return []
    finally:
        time.sleep(ABSTAND_SEKUNDEN)

    if antwort.status_code == 404:
        # Diese Auszeichnung verwendet der Filer nicht — der Regelfall beim
        # Durchprobieren der Alternativen, kein Vorfall.
        return []
    if antwort.status_code != 200:
        logger.warning("SEC-Abruf %s/%s: HTTP %s", cik, konzept,
                       antwort.status_code)
        return []

    try:
        return antwort.json().get("units", {}).get("USD", [])
    except ValueError:
        logger.warning("SEC-Antwort %s/%s ist kein JSON.", cik, konzept)
        return []


def _erste_einreichung(eintraege: list[dict], zeitraum: bool,
                       dauer: tuple[int, int] = JAHRESDAUER
                       ) -> dict[str, tuple[date, float]]:
    """Je Periodenende die FRÜHESTE Einreichung, die die Zahl enthielt.

    Args:
        zeitraum: True für Stromgrößen (Gewinn, Cashflow — mit `start`),
            False für Bestandsgrößen (Bilanzsumme — ohne `start`).

    Die früheste Einreichung ist der Punkt, an dem die Zahl öffentlich wurde.
    Spätere Nennungen derselben Periode sind Vergleichsspalten der Folgejahre;
    sie zu verwenden hieße, mit dem Wissen von morgen zu rechnen — genau der
    Fehler, an dem die `frames`-Schnittstelle scheitert.
    """
    ergebnis: dict[str, tuple[date, float]] = {}
    for eintrag in eintraege:
        ende, eingereicht = eintrag.get("end"), eintrag.get("filed")
        if not ende or not eingereicht:
            continue
        beginn = eintrag.get("start")
        if zeitraum:
            if not beginn:
                continue
            try:
                spanne = (date.fromisoformat(ende) - date.fromisoformat(beginn)).days
            except ValueError:
                continue
            if not dauer[0] <= spanne <= dauer[1]:
                continue
        elif beginn:
            continue

        wert = eintrag.get("val")
        if wert is None:
            continue
        try:
            datum = date.fromisoformat(eingereicht)
        except ValueError:
            continue

        vorhanden = ergebnis.get(ende)
        if vorhanden is None or datum < vorhanden[0]:
            ergebnis[ende] = (datum, float(wert))
    return ergebnis


def _erster_treffer(cik: str, konzepte: Iterable[str], zeitraum: bool) -> dict:
    """Erste Auszeichnung der Liste, die überhaupt Perioden liefert."""
    for konzept in konzepte:
        gefunden = _erste_einreichung(_konzept_laden(cik, konzept), zeitraum)
        if gefunden:
            return gefunden
    return {}


def accruals_laden(ticker: str, cik: str) -> list[dict]:
    """Jahres-Accruals eines Unternehmens, punkt-in-zeit datiert.

    Returns:
        Liste aus {periode_ende, bekannt_ab, netto_gewinn,
        operativer_cashflow, bilanzsumme, accrual}, aufsteigend nach Periode.
    """
    gewinn = _erster_treffer(cik, KONZEPTE_GEWINN, zeitraum=True)
    if not gewinn:
        return []
    cashflow = _erster_treffer(cik, KONZEPTE_CASHFLOW, zeitraum=True)
    if not cashflow:
        return []
    bilanz = _erster_treffer(cik, KONZEPTE_BILANZSUMME, zeitraum=False)
    if not bilanz:
        return []

    ergebnis = []
    for ende in sorted(set(gewinn) & set(cashflow) & set(bilanz)):
        (f_gewinn, v_gewinn) = gewinn[ende]
        (f_cashflow, v_cashflow) = cashflow[ende]
        (f_bilanz, v_bilanz) = bilanz[ende]
        if not v_bilanz:
            # Eine Bilanzsumme von null ist kein Nenner. Kommt bei
            # Zweckgesellschaften und Fehlauszeichnungen vor.
            continue

        ergebnis.append({
            "periode_ende": datetime.fromisoformat(ende),
            # Berechenbar erst, wenn ALLE drei Bestandteile öffentlich sind.
            "bekannt_ab": datetime.combine(
                max(f_gewinn, f_cashflow, f_bilanz), datetime.min.time()),
            "netto_gewinn": v_gewinn,
            "operativer_cashflow": v_cashflow,
            "bilanzsumme": v_bilanz,
            "accrual": (v_gewinn - v_cashflow) / v_bilanz,
        })
    return ergebnis


# ---------------------------------------------------------------------------
# Bestandsaufbau
# ---------------------------------------------------------------------------

def accruals_backfill(db: Session, tickers: Iterable[str],
                      karte: Optional[dict[str, str]] = None,
                      ueberspringen_wenn_vorhanden: bool = True) -> dict:
    """Lädt Jahres-Accruals für viele Ticker in die Tabelle.

    Returns:
        {"geprueft", "ohne_cik", "abgerufen", "neu", "ohne_daten",
         "fehlende_ticker"}
    """
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t))
    if karte is None:
        karte = cik_zuordnung()
    if not karte:
        logger.error("Ohne CIK-Zuordnung ist kein Bestandsaufbau möglich.")
        return {"geprueft": len(tickers), "ohne_cik": len(tickers),
                "abgerufen": 0, "neu": 0, "ohne_daten": 0,
                "fehlende_ticker": list(tickers)}

    vorhanden: set[str] = set()
    if ueberspringen_wenn_vorhanden:
        vorhanden = {t for (t,) in db.query(AccrualKennzahl.ticker).distinct().all()}

    statistik: dict = {"geprueft": len(tickers), "ohne_cik": 0, "abgerufen": 0,
                       "neu": 0, "ohne_daten": 0, "fehlende_ticker": []}

    for nummer, ticker in enumerate(tickers, start=1):
        if ticker in vorhanden:
            continue
        cik = karte.get(ticker)
        if cik is None:
            # Jede Auslandsnotierung. Kein Fehler, aber der Grund, aus dem
            # diese Messung US-only bleibt.
            statistik["ohne_cik"] += 1
            statistik["fehlende_ticker"].append(ticker)
            continue

        kennzahlen = accruals_laden(ticker, cik)
        statistik["abgerufen"] += 1

        if not kennzahlen:
            statistik["ohne_daten"] += 1
            statistik["fehlende_ticker"].append(ticker)
            continue

        bekannt = {
            p for (p,) in db.query(AccrualKennzahl.periode_ende)
            .filter(AccrualKennzahl.ticker == ticker).all()
        }
        jetzt = datetime.utcnow()
        neu = 0
        for k in kennzahlen:
            if k["periode_ende"] in bekannt:
                continue
            db.add(AccrualKennzahl(ticker=ticker, cik=cik, quelle="sec-xbrl",
                                   geladen_am=jetzt, **k))
            neu += 1
        statistik["neu"] += neu

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Accruals für %s nicht speicherbar: %s", ticker, e,
                         exc_info=True)
            statistik["fehlende_ticker"].append(ticker)

        if nummer % 25 == 0:
            logger.info("Accrual-Backfill: %d/%d Ticker, %d Kennzahlen neu.",
                        nummer, len(tickers), statistik["neu"])

    logger.info("Accrual-Backfill fertig: %d geprüft, %d ohne CIK, "
                "%d abgerufen, %d Kennzahlen neu, %d ohne Daten.",
                statistik["geprueft"], statistik["ohne_cik"],
                statistik["abgerufen"], statistik["neu"],
                statistik["ohne_daten"])
    return statistik


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------

def accruals_je_ticker(db: Session,
                       tickers: Optional[Iterable[str]] = None
                       ) -> dict[str, list[tuple[datetime, float]]]:
    """Je Ticker die nach `bekannt_ab` sortierten (Zeitpunkt, Accrual).

    Sortiert wird nach dem Bekanntwerden, nicht nach der Periode: Abschlüsse
    erscheinen nicht immer in der Reihenfolge ihrer Geschäftsjahre, wenn eine
    Nachmeldung dazwischenkommt.
    """
    query = db.query(AccrualKennzahl.ticker, AccrualKennzahl.bekannt_ab,
                     AccrualKennzahl.accrual)
    if tickers is not None:
        liste = [t.strip().upper() for t in tickers if t]
        if not liste:
            return {}
        query = query.filter(AccrualKennzahl.ticker.in_(liste))

    reihen: dict[str, list[tuple[datetime, float]]] = {}
    for ticker, bekannt_ab, accrual in query.all():
        if bekannt_ab is None or accrual is None:
            continue
        reihen.setdefault(ticker, []).append((bekannt_ab, float(accrual)))
    for reihe in reihen.values():
        reihe.sort(key=lambda e: e[0])
    return reihen


def letzter_accrual_vor(reihe: Optional[list[tuple[datetime, float]]],
                        zeitpunkt: datetime,
                        min_abstand_tage: int = MIN_ABSTAND_TAGE,
                        max_alter_tage: int = MAX_ALTER_TAGE
                        ) -> Optional[tuple[datetime, float, int]]:
    """Die jüngste Kennzahl, die zum Zeitpunkt bereits öffentlich war.

    Returns:
        (bekannt_ab, accrual, Alter in Tagen) — oder None.
    """
    if not reihe or zeitpunkt is None:
        return None

    obergrenze = zeitpunkt - timedelta(days=min_abstand_tage)
    untergrenze = zeitpunkt - timedelta(days=max_alter_tage)

    for bekannt_ab, accrual in reversed(reihe):
        if bekannt_ab > obergrenze:
            continue
        if bekannt_ab < untergrenze:
            return None
        return (bekannt_ab, accrual, (zeitpunkt - bekannt_ab).days)
    return None


# ---------------------------------------------------------------------------
# Kommandozeile
# ---------------------------------------------------------------------------

def cli() -> None:
    """Bestandsaufbau über das Snapshot-Universum."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import config
    if "example.com" in (config.SEC_USER_AGENT or ""):
        print("WARNUNG: SEC_USER_AGENT ist noch der Platzhalter aus "
              ".env.example. Die SEC verlangt eine echte Kontaktadresse und "
              "sperrt Abrufer ohne eine solche.")

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
        ergebnis = accruals_backfill(db, tickers)
        print(f"Ohne CIK: {ergebnis['ohne_cik']} | abgerufen: "
              f"{ergebnis['abgerufen']} | neue Kennzahlen: {ergebnis['neu']} | "
              f"ohne Daten: {ergebnis['ohne_daten']}")
    finally:
        db.close()
