"""Nettoemission aus den XBRL-Daten der SEC — punkt-in-zeit datiert (P2-06).

**Was gemessen wird.** Pontiff/Woodgate (2008) und Daniel/Titman (2006):
Unternehmen, die Aktien ausgeben, liefern schlechtere Folgerenditen als
Unternehmen, die zurueckkaufen. Die Kennzahl ist

    nettoemission = ln(Aktienzahl / Aktienzahl im Vorjahr)

**Unten ist gut** — wie bei den Accruals (§2g) und anders als bei PEAD (§2e).
Ein Rueckkauf ergibt einen negativen Wert.

**Warum gerade diese Familie.** `LITERATUR.md` §6.3 fuehrt sie als staerksten
Einzelkandidaten: kursunabhaengig, punkt-in-zeit datierbar, ueber den in
`services/accruals.py` bereits geloesten Weg fuer wenige Minuten Rechenzeit
erhebbar — und die einzige gepruefte Familie, fuer die die Literatur
ausdruecklich Robustheit ueber **kleine und grosse** Firmen berichtet. Genau
an dieser Eigenschaft ist der Insider-Clusterkauf gescheitert: auf Large Cap
+3,1 pp, auf 4.161 Titeln −0,0 pp (CONTEXT.md §2o).

Sie beantwortet ausserdem die Vorabfrage aus §5 („warum scheitert es nicht an
der Jahresstabilitaet?"): das Vorzeichen stammt nicht aus einem Marktregime,
sondern aus einer Unternehmensentscheidung.

---

**Der Kern: beide Aktienzahlen stammen aus DERSELBEN Einreichung.**

Aktienzahlen der SEC sind roh und nicht split-bereinigt, und eine Einreichung
stellt ihre Vergleichsperioden auf die *aktuelle* Split-Basis um. Gemessen an
NVDA (10:1 im Juni 2024), Konzept `WeightedAverageNumberOfSharesOutstanding
Basic`, dieselbe Periode 2023-01-29:

    Einreichung 2024-02-21:   2.487,0 Mio Aktien
    Einreichung 2025-02-26:  24.870,0 Mio Aktien      <- Faktor 10, reiner Split

Wer die Zahlen zweier Einreichungen vergleicht, misst fuer NVDA im Jahr 2024
eine Nettoemission von rund +887 Prozent, wo tatsaechlich ein Rueckkauf von
einem halben Prozent stattfand. Das waere kein kleiner Fehler, sondern ein
frei erfundener Extremwert in genau dem Quintil, um das es geht.

Innerhalb einer Einreichung ist das Verhaeltnis dagegen sauber — NVDA ueber
vier Jahre: 0,996 / 0,993 / 0,995 / 0,992. Deshalb wird ausschliesslich
innerhalb einer Accession verglichen. Ein Splitbestand als eigene Quelle wird
dadurch nicht gebraucht, und es gibt keine Bereinigung, die selbst falsch
sein koennte.

**Punkt-in-Zeit.** Je Periode wird die **frueheste** Accession genommen, die
das Paar (Periode, Vorjahr) enthaelt — das ist der Moment, in dem der
Vergleich oeffentlich wurde. Spaetere Einreichungen wiederholen dieselbe
Periode auf neuerer Split-Basis; sie zu verwenden hiesse, mit dem Wissen von
morgen zu rechnen. Dieselbe Regel und derselbe Grund wie in `accruals.py`.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime
from math import log
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database import NettoemissionKennzahl
from services.accruals import cik_zuordnung  # dieselbe Zuordnung, ein Abruf

logger = logging.getLogger(__name__)


KONZEPT_URL = ("https://data.sec.gov/api/xbrl/companyconcept/"
               "CIK{cik}/us-gaap/{konzept}.json")

# Wie in accruals.py: die SEC bittet um hoechstens zehn Anfragen je Sekunde.
ABSTAND_SEKUNDEN = 0.12

# Reihenfolge = Vorzug bei gleicher Abdeckung. `CommonStockSharesOutstanding`
# steht vorn, weil Pontiff/Woodgate die *ausstehende* Aktienzahl verwenden;
# die gewichteten Durchschnitte sind deren geglaettete Fassung und stehen als
# Rueckfall dahinter. Stichtags- und Zeitraumwerte werden gleich behandelt,
# weil die Paarbildung nur die Periodenenden vergleicht.
#
# **Nicht der erste Treffer gewinnt, sondern der bestabgedeckte.** Gemessen:
# GOOGL liefert aus `WeightedAverageNumberOfSharesOutstandingBasic` nur drei
# Paare (ab 2023), aus `CommonStockSharesOutstanding` aber elf (ab 2015);
# MSFT 18 gegen 19. Wer den ersten nicht leeren Treffer nimmt, verliert bei
# solchen Filern zwei Drittel der Historie, ohne dass es auffiele.
KONZEPTE_AKTIEN = (
    "CommonStockSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "CommonStockSharesIssued",
    "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
)

# Ab so vielen Paaren wird nicht weitergesucht. Der Messzeitraum umfasst rund
# zehn Jahre; wer zwoelf Jahrespaare liefert, deckt ihn vollstaendig ab, und
# ein weiterer Abruf koennte daran nichts mehr verbessern. Das spart bei
# 4.161 Tickern rund vier Fuenftel der Abrufe.
VOLLE_HISTORIE = 12

# Als Jahresgroesse gilt eine Dauer in diesem Bereich — wie in accruals.py,
# damit 52/53-Wochen-Geschaeftsjahre und Schaltjahre hereinfallen,
# Halbjahres- und Neunmonatswerte aber nicht.
JAHRESDAUER = (350, 385)

# Abstand zwischen den beiden Periodenenden eines Paares. Weiter gefasst als
# JAHRESDAUER, weil ein Geschaeftsjahreswechsel die Enden verschiebt.
PAARABSTAND = (330, 400)

# Groessere Spruenge sind keine Emission, sondern ein Ereignis anderer Art:
# ein Split, den ein Filer NICHT rueckwirkend angewandt hat, eine Fusion, ein
# Reverse Split. exp(1.0) ist Faktor 2,7 und exp(-1.0) Faktor 0,37 — jenseits
# davon wird verworfen statt gestutzt, weil ein gestutzter Extremwert immer
# noch im aeussersten Quintil landet und dort das Ergebnis traegt.
MAX_BETRAG = 1.0


def _kopfzeilen() -> dict:
    import config
    return {"User-Agent": config.SEC_USER_AGENT,
            "Accept-Encoding": "gzip, deflate"}


def _konzept_laden(cik: str, konzept: str) -> list[dict]:
    """Alle Aktienzahl-Fakten eines Unternehmens zu einer Auszeichnung.

    Anders als in `accruals.py` wird die Einheit **shares** gelesen, nicht
    USD — ein Abruf auf `units["USD"]` liefert hier durchgaengig nichts.
    """
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
        # Diese Auszeichnung verwendet der Filer nicht — Regelfall beim
        # Durchprobieren, kein Vorfall.
        return []
    if antwort.status_code != 200:
        logger.warning("SEC-Abruf %s/%s: HTTP %s", cik, konzept,
                       antwort.status_code)
        return []

    try:
        return antwort.json().get("units", {}).get("shares", [])
    except ValueError:
        logger.warning("SEC-Antwort %s/%s ist kein JSON.", cik, konzept)
        return []


def _jahreseintraege(eintraege: list[dict]) -> list[dict]:
    """Auf Jahresperioden eingegrenzt, Stichtagswerte unveraendert durchgelassen."""
    behalten = []
    for e in eintraege:
        ende, eingereicht, accn = e.get("end"), e.get("filed"), e.get("accn")
        if not ende or not eingereicht or not accn or e.get("val") is None:
            continue
        beginn = e.get("start")
        if beginn:
            try:
                spanne = (date.fromisoformat(ende) - date.fromisoformat(beginn)).days
            except ValueError:
                continue
            if not JAHRESDAUER[0] <= spanne <= JAHRESDAUER[1]:
                continue
        behalten.append(e)
    return behalten


def paare_aus_einreichungen(eintraege: list[dict]) -> dict[str, dict]:
    """Je Periodenende das frueheste split-konsistente Vorjahrespaar.

    Beide Werte eines Paares stammen aus derselben Accession — das ist der
    ganze Punkt dieses Moduls, siehe Modul-Docstring.

    Returns:
        {periode_ende: {aktien, aktien_vorjahr, bekannt_ab, accession}}
    """
    nach_accn: dict[str, list[dict]] = defaultdict(list)
    for e in _jahreseintraege(eintraege):
        nach_accn[e["accn"]].append(e)

    ergebnis: dict[str, dict] = {}
    for accn, gruppe in nach_accn.items():
        # Je (accn, end) genau ein Wert: `companyconcept` liefert nur die
        # konsolidierten Fakten ohne Dimensionen. An GOOGL, BRK und AAPL
        # geprueft — null mehrdeutige Paare.
        je_ende: dict[str, dict] = {}
        for e in gruppe:
            je_ende.setdefault(e["end"], e)

        enden = sorted(je_ende)
        for spaeter, frueher in zip(enden[1:], enden[:-1]):
            try:
                abstand = (date.fromisoformat(spaeter)
                           - date.fromisoformat(frueher)).days
            except ValueError:
                continue
            if not PAARABSTAND[0] <= abstand <= PAARABSTAND[1]:
                continue

            jetzt, vorher = je_ende[spaeter], je_ende[frueher]
            if not vorher["val"] or not jetzt["val"]:
                continue
            if vorher["val"] <= 0 or jetzt["val"] <= 0:
                continue

            try:
                eingereicht = date.fromisoformat(jetzt["filed"])
            except ValueError:
                continue

            vorhanden = ergebnis.get(spaeter)
            if vorhanden is not None and vorhanden["bekannt_ab"] <= eingereicht:
                continue
            ergebnis[spaeter] = {
                "aktien": float(jetzt["val"]),
                "aktien_vorjahr": float(vorher["val"]),
                "bekannt_ab": eingereicht,
                "accession": accn,
            }
    return ergebnis


def nettoemission_laden(ticker: str, cik: str) -> list[dict]:
    """Jahres-Nettoemissionen eines Unternehmens, punkt-in-zeit datiert.

    Returns:
        Liste aus {periode_ende, bekannt_ab, accession, konzept, aktien,
        aktien_vorjahr, nettoemission}, aufsteigend nach Periode.
    """
    bestes_konzept, beste_paare = None, {}
    for konzept in KONZEPTE_AKTIEN:
        paare = paare_aus_einreichungen(_konzept_laden(cik, konzept))
        if len(paare) > len(beste_paare):
            bestes_konzept, beste_paare = konzept, paare
        if len(beste_paare) >= VOLLE_HISTORIE:
            break

    if not beste_paare:
        return []

    ergebnis = []
    for ende in sorted(beste_paare):
        p = beste_paare[ende]
        wert = log(p["aktien"] / p["aktien_vorjahr"])
        if abs(wert) > MAX_BETRAG:
            # Nicht rueckwirkend angewandter Split, Fusion, Reverse Split.
            continue
        ergebnis.append({
            "periode_ende": datetime.fromisoformat(ende),
            "bekannt_ab": datetime.combine(p["bekannt_ab"],
                                           datetime.min.time()),
            "accession": p["accession"],
            "konzept": bestes_konzept,
            "aktien": p["aktien"],
            "aktien_vorjahr": p["aktien_vorjahr"],
            "nettoemission": wert,
        })
    return ergebnis


# ---------------------------------------------------------------------------
# Bestandsaufbau
# ---------------------------------------------------------------------------

def nettoemission_backfill(db: Session, tickers: Iterable[str],
                           karte: Optional[dict[str, str]] = None,
                           ueberspringen_wenn_vorhanden: bool = True) -> dict:
    """Laedt Jahres-Nettoemissionen fuer viele Ticker in die Tabelle.

    Returns:
        {"geprueft", "ohne_cik", "abgerufen", "neu", "ohne_daten",
         "fehlende_ticker"}
    """
    tickers = list(dict.fromkeys(t.strip().upper() for t in tickers if t))
    if karte is None:
        karte = cik_zuordnung()
    if not karte:
        logger.error("Ohne CIK-Zuordnung ist kein Bestandsaufbau moeglich.")
        return {"geprueft": len(tickers), "ohne_cik": len(tickers),
                "abgerufen": 0, "neu": 0, "ohne_daten": 0,
                "fehlende_ticker": list(tickers)}

    vorhanden: set[str] = set()
    if ueberspringen_wenn_vorhanden:
        vorhanden = {t for (t,) in
                     db.query(NettoemissionKennzahl.ticker).distinct().all()}

    statistik: dict = {"geprueft": len(tickers), "ohne_cik": 0, "abgerufen": 0,
                       "neu": 0, "ohne_daten": 0, "fehlende_ticker": []}

    for nummer, ticker in enumerate(tickers, start=1):
        if ticker in vorhanden:
            continue
        cik = karte.get(ticker)
        if cik is None:
            # Jede Auslandsnotierung. Kein Fehler, aber der Grund, aus dem
            # diese Messung wie §2f, §2g und §2n US-only bleibt.
            statistik["ohne_cik"] += 1
            statistik["fehlende_ticker"].append(ticker)
            continue

        kennzahlen = nettoemission_laden(ticker, cik)
        statistik["abgerufen"] += 1

        if not kennzahlen:
            statistik["ohne_daten"] += 1
            statistik["fehlende_ticker"].append(ticker)
            continue

        bekannt = {
            p for (p,) in db.query(NettoemissionKennzahl.periode_ende)
            .filter(NettoemissionKennzahl.ticker == ticker).all()
        }
        jetzt = datetime.utcnow()
        neu = 0
        for k in kennzahlen:
            if k["periode_ende"] in bekannt:
                continue
            db.add(NettoemissionKennzahl(ticker=ticker, cik=cik,
                                         quelle="sec-xbrl", geladen_am=jetzt, **k))
            neu += 1
        statistik["neu"] += neu

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Nettoemission fuer %s nicht speicherbar: %s", ticker, e,
                         exc_info=True)
            statistik["fehlende_ticker"].append(ticker)

        if nummer % 100 == 0:
            logger.info("Nettoemission-Backfill: %d/%d Ticker, %d Kennzahlen neu.",
                        nummer, len(tickers), statistik["neu"])

    logger.info("Nettoemission-Backfill fertig: %d geprueft, %d ohne CIK, "
                "%d abgerufen, %d Kennzahlen neu, %d ohne Daten.",
                statistik["geprueft"], statistik["ohne_cik"],
                statistik["abgerufen"], statistik["neu"],
                statistik["ohne_daten"])
    return statistik


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------

def nettoemission_je_ticker(db: Session,
                            tickers: Optional[Iterable[str]] = None
                            ) -> dict[str, list[tuple[datetime, float]]]:
    """Je Ticker die nach `bekannt_ab` sortierten (Zeitpunkt, Nettoemission).

    Dieselbe Form wie `accruals.accruals_je_ticker`, damit
    `letzter_accrual_vor` auch hier verwendbar ist.
    """
    abfrage = db.query(NettoemissionKennzahl.ticker,
                       NettoemissionKennzahl.bekannt_ab,
                       NettoemissionKennzahl.nettoemission)
    if tickers is not None:
        liste = [t.strip().upper() for t in tickers if t]
        if not liste:
            return {}
        abfrage = abfrage.filter(NettoemissionKennzahl.ticker.in_(liste))

    reihen: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for ticker, bekannt_ab, wert in abfrage.all():
        if bekannt_ab is None or wert is None:
            continue
        reihen[ticker].append((bekannt_ab, float(wert)))
    for reihe in reihen.values():
        reihe.sort(key=lambda p: p[0])
    return dict(reihen)


def cli() -> None:
    """Bestandsaufbau ueber das erweiterte Universum (Auftrag C).

    Bewusst NICHT ueber das Snapshot-Universum wie `accruals.cli()`: die
    Groessenwarnung aus `LITERATUR.md` §3 und der Verlauf von §2n sagen, dass
    ein Befund auf 592 Large Caps nichts darueber aussagt, ob er auf kleineren
    Titeln haelt. Die Auswertung laeuft ueber `auswertung/kurspanel.py` und
    braucht dafuer keine Snapshots.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import config
    if "example.com" in (config.SEC_USER_AGENT or ""):
        print("WARNUNG: SEC_USER_AGENT ist noch der Platzhalter aus "
              ".env.example. Die SEC verlangt eine echte Kontaktadresse und "
              "sperrt Abrufer ohne eine solche.")

    import database
    from services.universum import erweitertes_universum

    database.init_db()
    db = database.get_session()
    try:
        tickers = erweitertes_universum(db, nur_mit_sec_historie=True)
        print(f"Universum: {len(tickers)} Ticker.")
        ergebnis = nettoemission_backfill(db, tickers)
        print(f"Ohne CIK: {ergebnis['ohne_cik']} | abgerufen: "
              f"{ergebnis['abgerufen']} | neue Kennzahlen: {ergebnis['neu']} | "
              f"ohne Daten: {ergebnis['ohne_daten']}")
    finally:
        db.close()


if __name__ == "__main__":
    cli()
