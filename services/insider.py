"""
services/insider.py — Offene Insidergeschäfte aus SEC Form 4 (Auftrag B).

Die vierte Signalfamilie mit eigener Quelle, nach PEAD (§2e), den
Analystenrevisionen (§2f) und den Accruals (§2g) — und die einzige, die die
Bewertungsfrage direkt trifft: **jemand mit Informationsvorsprung kauft,
während der Chart fällt.** Kursunabhängig, punkt-in-zeit datierbar, aus
derselben Behörde wie §2g.

**Warum diese Quelle und nicht die beiden naheliegenden.**

- `yfinance.insider_transactions` reicht bei allen fünf in §2g geprüften
  Tickern nur bis September/Oktober 2024 zurück. Der Trainingsteil endet am
  2025-04-20 — es blieben gut sechs Monate Überlappung, und der **Holdout
  hätte mehr Abdeckung als das Training**. Damit ist die Quelle für eine
  Messung unbrauchbar, nicht nur dünn.
- Quiver scheidet ausdrücklich aus (CONTEXT §5 B): kein hinterlegtes Token,
  `/live/...`-Endpunkte ohne Historie, drei `TODO: verify`-Stellen in
  `services/quiver.py`, an denen die Feldnamen nie gegen eine echte Antwort
  geprüft wurden.

**Warum die Quartalsdatensätze und nicht die Einzeleinreichungen.** Der Weg
über `submissions` + Form-4-XML ist der offensichtliche, und er kostet einen
Abruf je Einreichung: bei 611 Tickern über zehn Jahre größenordnungsmäßig
300.000 Abrufe, bei 0,12 s Abstand rund zehn Stunden. Die SEC veröffentlicht
denselben Bestand als **vierteljährliche Form-345-Datensätze** — ein ZIP je
Quartal. Gemessen an 2024Q1: 13,9 MB, 67.671 Einreichungen, 111.404
Geschäfte. Vierzig Quartale sind rund 450 MB und etwa zwanzig Minuten.

Verfügbar ist die Reihe von **2006Q1 bis 2026Q1** (2026Q2 war am 2026-09-04
noch nicht veröffentlicht — geprüft, nicht angenommen). Der Trainingsteil
endet 2025-04-20 und ist damit vollständig abgedeckt.

**`bekannt_ab` ist FILING_DATE, nie TRANS_DATE.** Gemessen an 2024Q1 beträgt
der Meldeverzug im Median zwei Tage und im 90. Perzentil vier — der größte
Einzelwert aber **2.332 Tage**, und sechs Zeilen tragen ein Einreichungsdatum
vor dem Handelstag. Nach `trans_datum` datiert wäre das in Einzelfällen
Look-ahead um Jahre. Der Handelstag bleibt gespeichert, weil die
Routine-Erkennung seinen Kalendermonat braucht.

**Die Routine-Trennung ist keine Verfeinerung, sondern Bedingung.** Cohen,
Malloy und Pomorski (2012) zeigen, dass über die Hälfte aller Insidergeschäfte
kalendergetrieben sind: dieselbe Person, derselbe Monat, Jahr für Jahr. Diese
Geschäfte tragen **null**; die opportunistischen tragen 82 bp/Monat. Wer beide
zusammen misst, misst überwiegend Rauschen. Die Trennung braucht die Historie
je **Person** — deshalb wird `owner_cik` gespeichert und nicht nur der Emittent.

Der 10b5-1-Haken wäre der bequemere Weg, taugt hier aber nicht: er ist erst
seit 2023 verpflichtend anzukreuzen und in vier Schreibweisen kodiert
(`0`/`1`/`false`/`true`, gemessen). Über den halben Messzeitraum wäre die
Spalte leer.

Bestandsaufbau (einmalig, rund zwanzig Minuten):
    py -c "import services.insider as i; i.cli()"
"""

import csv
import io
import logging
import os
import tempfile
import time
import zipfile
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database import InsiderGeschaeft

logger = logging.getLogger(__name__)


QUARTALS_URL = ("https://www.sec.gov/files/structureddata/data/"
                "insider-transactions-data-sets/{jahr}q{quartal}_form345.zip")

# Wie in `services/accruals.py`: die SEC bittet um höchstens zehn Anfragen je
# Sekunde. Hier fällt der Abstand ohnehin kaum ins Gewicht — es sind vierzig
# Abrufe, nicht vierzigtausend.
ABSTAND_SEKUNDEN = 0.2

# Erstes Quartal, für das die SEC den Datensatz führt.
ERSTES_QUARTAL = (2006, 1)

# Nur die eigentliche Meldung, keine Berichtigungen (`4/A`) und keine
# Form 5. Berichtigungen stellen eine frühere Meldung richtig und würden ohne
# Abgleich doppelt zählen; Form 5 meldet nachträglich befreite Geschäfte,
# also gerade die, die keine Marktentscheidung waren.
DOKUMENTTYP = "4"

# P = Kauf am Markt, S = Verkauf am Markt. Zuteilungen (A),
# Optionsausübungen (M), Steuereinbehalte (F) und Schenkungen (G) sind keine
# Entscheidung, zu diesem Kurs zu handeln — genau die Trennung, die
# Lakonishok/Lee (2001) ziehen.
KAUF, VERKAUF = "P", "S"
CODES = (KAUF, VERKAUF)

# Das erwartete Gegenstück in TRANS_ACQUIRED_DISP_CD. Gemessen an 2024Q1
# widersprechen sich 61 von 32.354 Zeilen (0,19 %) — ein Kauf, der als
# Veräußerung ausgezeichnet ist. Solche Zeilen werden verworfen: welche der
# beiden Angaben stimmt, ist von außen nicht entscheidbar.
ERWARTET_AD = {KAUF: "A", VERKAUF: "D"}

# Sicherheitsabstand zwischen Bekanntwerden und Snapshot, in Kalendertagen —
# wie in `services/accruals.py` und `services/pead.py`, aus demselben Grund:
# das Einreichungsdatum trägt keine Uhrzeit.
MIN_ABSTAND_TAGE = 1

# Rückblickfenster der Firmenkennzahl. Sechs Monate ist das Fenster, über das
# Lakonishok/Lee (2001) den Netto-Insiderhandel je Firma bilden.
FENSTER_TAGE = 180

# Cohen/Malloy/Pomorski nennen eine Person routinemäßig, wenn sie im selben
# Kalendermonat in mindestens drei aufeinanderfolgenden Vorjahren gehandelt hat.
ROUTINE_JAHRE = 3


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------

def _kopfzeilen() -> dict:
    import config
    return {"User-Agent": config.SEC_USER_AGENT,
            "Accept-Encoding": "gzip, deflate"}


def _cache_verzeichnis() -> str:
    """Ablage der Quartals-ZIPs — **außerhalb des Repos**.

    Bewusst nicht unter `data/`: `.gitignore` deckt dort weder `*.zip` noch
    ein Unterverzeichnis ab, und ein versehentlich eingecheckter Quartalsstand
    wäre derselbe Vorfall wie die 37,3 MB WAL-Datei aus Commit `6f2f3db`.
    """
    pfad = os.path.join(tempfile.gettempdir(), "macrodashboard_sec_form345")
    os.makedirs(pfad, exist_ok=True)
    return pfad


def quartale(von: date, bis: date) -> list[tuple[int, int]]:
    """Alle Quartale zwischen zwei Daten, aufsteigend.

    Das Quartal eines Geschäfts richtet sich nach seinem EINREICHUNGSdatum,
    nicht nach dem Handelstag — eine Meldung vom Januar kann ein Geschäft vom
    November des Vorjahres enthalten. Wer nach Handelstagen abgrenzt, verliert
    genau die verspäteten Meldungen.
    """
    ergebnis = []
    jahr, quartal = max((von.year, (von.month - 1) // 3 + 1), ERSTES_QUARTAL)
    letztes = (bis.year, (bis.month - 1) // 3 + 1)
    while (jahr, quartal) <= letztes:
        ergebnis.append((jahr, quartal))
        jahr, quartal = (jahr + 1, 1) if quartal == 4 else (jahr, quartal + 1)
    return ergebnis


def quartal_laden(jahr: int, quartal: int,
                  cache: bool = True) -> Optional[bytes]:
    """Das Form-345-ZIP eines Quartals, aus dem Zwischenspeicher oder vom Netz.

    Returns:
        None, wenn das Quartal (noch) nicht veröffentlicht ist — der Regelfall
        am aktuellen Rand, kein Vorfall.
    """
    import requests

    datei = os.path.join(_cache_verzeichnis(), f"{jahr}q{quartal}_form345.zip")
    if cache and os.path.exists(datei) and os.path.getsize(datei) > 0:
        with open(datei, "rb") as f:
            return f.read()

    url = QUARTALS_URL.format(jahr=jahr, quartal=quartal)
    try:
        antwort = requests.get(url, headers=_kopfzeilen(), timeout=180)
    except Exception as e:
        logger.warning("SEC-Abruf %dQ%d fehlgeschlagen: %s", jahr, quartal, e)
        return None
    finally:
        time.sleep(ABSTAND_SEKUNDEN)

    if antwort.status_code == 404:
        logger.info("SEC-Datensatz %dQ%d noch nicht veröffentlicht.",
                    jahr, quartal)
        return None
    if antwort.status_code != 200:
        logger.warning("SEC-Abruf %dQ%d: HTTP %s", jahr, quartal,
                       antwort.status_code)
        return None

    if cache:
        try:
            with open(datei, "wb") as f:
                f.write(antwort.content)
        except OSError as e:
            logger.warning("Zwischenspeicher %dQ%d nicht schreibbar: %s",
                           jahr, quartal, e)
    return antwort.content


# ---------------------------------------------------------------------------
# Auswertung eines Quartalsstandes
# ---------------------------------------------------------------------------

def _datum(text: str) -> Optional[datetime]:
    """`31-JAN-2024` → datetime. Die Datensätze der SEC verwenden dieses Format."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d-%b-%Y")
    except ValueError:
        return None


def _zahl(text: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _wahrheit(text: str) -> Optional[bool]:
    """Der 10b5-1-Haken, in allen vier gemessenen Schreibweisen.

    Gemessen an 2024Q1 stehen `0` (47.277), `false` (11.213), `1` (4.013),
    `true` (1.139) und leer (4.029) nebeneinander — die SEC hat die Kodierung
    zwischen den Jahrgängen gewechselt. Ein `bool(text)` läse `"false"` als
    True; das ist die Sorte Fehler, die keinen Test bricht und ein Ergebnis
    still umdreht.
    """
    text = (text or "").strip().lower()
    if text in ("1", "true", "y", "yes"):
        return True
    if text in ("0", "false", "n", "no"):
        return False
    return None


def _tsv(archiv: zipfile.ZipFile, name: str):
    """Zeilen einer TSV im Archiv, als Dicts. Fehlt sie, ist die Reihe leer."""
    if name not in archiv.namelist():
        logger.warning("Form-345-Archiv ohne %s.", name)
        return
    with archiv.open(name) as roh:
        for zeile in csv.DictReader(
                io.TextIOWrapper(roh, "utf-8", errors="replace"),
                delimiter="\t"):
            yield zeile


def geschaefte_aus_archiv(daten: bytes,
                          universum: Optional[set[str]] = None) -> list[dict]:
    """Alle offenen Käufe und Verkäufe eines Quartalsstandes.

    Args:
        universum: Wenn gesetzt, bleiben nur diese Ticker. Der Filter greift
            VOR dem Aufbau der Zeilen — 2024Q1 trägt 111.404 Geschäfte, von
            denen bei 611 Tickern rund 8.800 übrig bleiben.

    Returns:
        Liste aus {ticker, issuer_cik, accession, sec_sk, owner_cik,
        owner_name, beziehung, mehrere_meldende, trans_datum, bekannt_ab,
        code, stueck, kurs, wert, plan_10b5_1}.
    """
    archiv = zipfile.ZipFile(io.BytesIO(daten))

    einreichungen: dict[str, dict] = {}
    for zeile in _tsv(archiv, "SUBMISSION.tsv"):
        if (zeile.get("DOCUMENT_TYPE") or "").strip() != DOKUMENTTYP:
            continue
        ticker = (zeile.get("ISSUERTRADINGSYMBOL") or "").strip().upper()
        if not ticker or (universum is not None and ticker not in universum):
            continue
        eingereicht = _datum(zeile.get("FILING_DATE", ""))
        if eingereicht is None:
            continue
        einreichungen[zeile["ACCESSION_NUMBER"]] = {
            "ticker": ticker,
            "issuer_cik": (zeile.get("ISSUERCIK") or "").strip() or None,
            "bekannt_ab": eingereicht,
            "plan_10b5_1": _wahrheit(zeile.get("AFF10B5ONE", "")),
        }

    # Je Einreichung der alphabetisch erste Meldende. 97,8 % der Einreichungen
    # tragen genau einen (gemessen: 66.198 von 67.671); die übrigen sind
    # Gemeinschaftsmeldungen verbundener Rechtsträger. Das Geschäft je
    # Meldendem zu vervielfachen würde Stückzahlen doppelt zählen, deshalb
    # bleibt es eine Zeile — mit einem Vermerk, dass die Person nicht eindeutig ist.
    meldende: dict[str, dict] = {}
    for zeile in _tsv(archiv, "REPORTINGOWNER.tsv"):
        nummer = zeile.get("ACCESSION_NUMBER")
        if nummer not in einreichungen:
            continue
        cik = (zeile.get("RPTOWNERCIK") or "").strip() or None
        vorhanden = meldende.get(nummer)
        if vorhanden is None:
            meldende[nummer] = {
                "owner_cik": cik,
                "owner_name": (zeile.get("RPTOWNERNAME") or "").strip() or None,
                "beziehung": (zeile.get("RPTOWNER_RELATIONSHIP") or "").strip() or None,
                "mehrere_meldende": False,
            }
            continue
        vorhanden["mehrere_meldende"] = True
        if cik is not None and (vorhanden["owner_cik"] is None
                                or cik < vorhanden["owner_cik"]):
            vorhanden["owner_cik"] = cik
            vorhanden["owner_name"] = (zeile.get("RPTOWNERNAME") or "").strip() or None
            vorhanden["beziehung"] = (zeile.get("RPTOWNER_RELATIONSHIP") or "").strip() or None

    ergebnis: list[dict] = []
    widersprueche = 0
    for zeile in _tsv(archiv, "NONDERIV_TRANS.tsv"):
        code = (zeile.get("TRANS_CODE") or "").strip().upper()
        if code not in CODES:
            continue
        kopf = einreichungen.get(zeile.get("ACCESSION_NUMBER", ""))
        if kopf is None:
            continue

        # Kauf und Veräußerung dürfen sich nicht widersprechen.
        ad = (zeile.get("TRANS_ACQUIRED_DISP_CD") or "").strip().upper()
        if ad and ad != ERWARTET_AD[code]:
            widersprueche += 1
            continue

        gehandelt = _datum(zeile.get("TRANS_DATE", ""))
        if gehandelt is None:
            continue
        stueck = _zahl(zeile.get("TRANS_SHARES", ""))
        kurs = _zahl(zeile.get("TRANS_PRICEPERSHARE", ""))
        person = meldende.get(zeile["ACCESSION_NUMBER"], {})

        ergebnis.append({
            "ticker": kopf["ticker"],
            "issuer_cik": kopf["issuer_cik"],
            "accession": zeile["ACCESSION_NUMBER"],
            "sec_sk": (zeile.get("NONDERIV_TRANS_SK") or "").strip(),
            "owner_cik": person.get("owner_cik"),
            "owner_name": person.get("owner_name"),
            "beziehung": person.get("beziehung"),
            "mehrere_meldende": bool(person.get("mehrere_meldende")),
            "trans_datum": gehandelt,
            "bekannt_ab": kopf["bekannt_ab"],
            "code": code,
            "stueck": stueck,
            "kurs": kurs,
            "wert": (None if stueck is None or kurs is None else stueck * kurs),
            "plan_10b5_1": kopf["plan_10b5_1"],
        })

    if widersprueche:
        logger.info("Form 345: %d Zeilen mit widersprüchlicher "
                    "Erwerbskennung verworfen.", widersprueche)
    return ergebnis


# ---------------------------------------------------------------------------
# Bestandsaufbau
# ---------------------------------------------------------------------------

def insider_backfill(db: Session, tickers: Iterable[str],
                     von: date, bis: Optional[date] = None,
                     cache: bool = True) -> dict:
    """Lädt offene Insidergeschäfte quartalsweise in die Tabelle.

    Returns:
        {"quartale", "quartale_geladen", "gelesen", "neu", "ohne_quartal"}
    """
    universum = {t.strip().upper() for t in tickers if t}
    if bis is None:
        bis = date.today()

    liste = quartale(von, bis)
    statistik: dict = {"quartale": len(liste), "quartale_geladen": 0,
                       "gelesen": 0, "neu": 0, "ohne_quartal": []}

    for jahr, quartal in liste:
        daten = quartal_laden(jahr, quartal, cache=cache)
        if daten is None:
            statistik["ohne_quartal"].append(f"{jahr}Q{quartal}")
            continue
        statistik["quartale_geladen"] += 1

        try:
            zeilen = geschaefte_aus_archiv(daten, universum)
        except (zipfile.BadZipFile, KeyError) as e:
            logger.error("Form-345-Archiv %dQ%d nicht lesbar: %s",
                         jahr, quartal, e, exc_info=True)
            statistik["ohne_quartal"].append(f"{jahr}Q{quartal}")
            continue
        statistik["gelesen"] += len(zeilen)

        # Der Doppelabgleich läuft je Quartal und nicht je Zeile: ein
        # `SELECT` gegen 350.000 Bestandszeilen wäre pro Geschäft eine Abfrage.
        bekannt = {
            (a, s) for a, s in db.query(InsiderGeschaeft.accession,
                                        InsiderGeschaeft.sec_sk).all()
        }
        jetzt = datetime.utcnow()
        neu = 0
        for zeile in zeilen:
            if (zeile["accession"], zeile["sec_sk"]) in bekannt:
                continue
            bekannt.add((zeile["accession"], zeile["sec_sk"]))
            db.add(InsiderGeschaeft(quelle="sec-form345", geladen_am=jetzt,
                                    **zeile))
            neu += 1

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Insidergeschäfte %dQ%d nicht speicherbar: %s",
                         jahr, quartal, e, exc_info=True)
            statistik["ohne_quartal"].append(f"{jahr}Q{quartal}")
            continue

        statistik["neu"] += neu
        logger.info("Form 345 %dQ%d: %d Geschäfte im Universum, %d neu.",
                    jahr, quartal, len(zeilen), neu)

    logger.info("Insider-Backfill fertig: %d/%d Quartale, %d gelesen, %d neu.",
                statistik["quartale_geladen"], statistik["quartale"],
                statistik["gelesen"], statistik["neu"])
    return statistik


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------

def geschaefte_je_ticker(db: Session,
                         tickers: Optional[Iterable[str]] = None
                         ) -> dict[str, list[tuple]]:
    """Je Ticker die nach `bekannt_ab` sortierten Geschäfte.

    Returns:
        {ticker: [(bekannt_ab, trans_datum, owner_cik, code, wert)]} —
        aufsteigend nach dem Bekanntwerden, weil jede Auswertung danach
        abschneidet.
    """
    query = db.query(InsiderGeschaeft.ticker, InsiderGeschaeft.bekannt_ab,
                     InsiderGeschaeft.trans_datum, InsiderGeschaeft.owner_cik,
                     InsiderGeschaeft.code, InsiderGeschaeft.wert)
    if tickers is not None:
        liste = [t.strip().upper() for t in tickers if t]
        if not liste:
            return {}
        query = query.filter(InsiderGeschaeft.ticker.in_(liste))

    reihen: dict[str, list[tuple]] = {}
    for ticker, bekannt_ab, gehandelt, owner, code, wert in query.all():
        if bekannt_ab is None or gehandelt is None or not code:
            continue
        reihen.setdefault(ticker, []).append(
            (bekannt_ab, gehandelt, owner, code, wert))
    for reihe in reihen.values():
        reihe.sort(key=lambda e: e[0])
    return reihen


def routine_kalender(reihen: dict[str, list[tuple]]) -> dict[tuple, datetime]:
    """Je (Person, Jahr, Monat) der früheste Zeitpunkt, zu dem das bekannt war.

    Die Grundlage der Routine-Erkennung nach Cohen/Malloy/Pomorski. Der
    Schlüssel trägt den **Handelsmonat** — das ist die Größe, deren
    Wiederkehr die Routine ausmacht —, der Wert das **Einreichungsdatum**,
    damit die spätere Prüfung punkt-in-zeit bleibt.
    """
    kalender: dict[tuple, datetime] = {}
    for reihe in reihen.values():
        for bekannt_ab, gehandelt, owner, _code, _wert in reihe:
            if owner is None:
                continue
            schluessel = (owner, gehandelt.year, gehandelt.month)
            vorhanden = kalender.get(schluessel)
            if vorhanden is None or bekannt_ab < vorhanden:
                kalender[schluessel] = bekannt_ab
    return kalender


def ist_routine(kalender: dict[tuple, datetime], owner: Optional[str],
                gehandelt: datetime, grenze: datetime,
                jahre: int = ROUTINE_JAHRE) -> bool:
    """Handelt diese Person seit Jahren im selben Kalendermonat?

    Args:
        grenze: Zeitpunkt der Auswertung. Vorjahresgeschäfte zählen nur, wenn
            sie **bis dahin bereits eingereicht** waren. Ohne diese Bedingung
            würde eine verspätete Meldung aus der Zukunft eine Person
            rückwirkend zur Routine erklären — Look-ahead durch die Hintertür.

    Unbekannte Personen (`owner is None`) gelten als nicht-routinemäßig: die
    Nichtklassifizierbarkeit ist kein Beleg für Kalendertreue. Das ist die
    vorsichtige Richtung — sie lässt Rauschen im opportunistischen Topf, statt
    ein Geschäft aus ihm zu entfernen.
    """
    if owner is None:
        return False
    for zurueck in range(1, jahre + 1):
        gesehen = kalender.get((owner, gehandelt.year - zurueck, gehandelt.month))
        if gesehen is None or gesehen > grenze:
            return False
    return True


def kennzahl_vor(reihe: Optional[list[tuple]], zeitpunkt: datetime,
                 kalender: Optional[dict[tuple, datetime]] = None,
                 fenster_tage: int = FENSTER_TAGE,
                 min_abstand_tage: int = MIN_ABSTAND_TAGE) -> Optional[dict]:
    """Der Netto-Insiderhandel einer Firma zu einem Zeitpunkt.

    Gezählt werden **Personen, nicht Geschäfte**: wer in einem Fenster
    dreimal nachkauft, ist ein Käufer. Das ist die Konstruktion von
    Lakonishok/Lee (2001) und der Grund, aus dem sie es so machen — sonst
    entschiede die Stückelung einer einzelnen Order über die Kennzahl.

    Returns:
        {"kaeufer", "verkaeufer", "npr", "opportunistische_kaeufer",
         "npr_opportunistisch", "kauf_wert", "verkauf_wert", "n_geschaefte"}
        — oder None, wenn im Fenster überhaupt nichts gemeldet wurde.

    `npr` läuft von −1 (nur Verkäufer) bis +1 (nur Käufer). Positiv ist gut:
    die Hypothese lautet, dass Insiderkäufe Überrenditen vorhersagen.
    """
    if not reihe or zeitpunkt is None:
        return None

    obergrenze = zeitpunkt - timedelta(days=min_abstand_tage)
    untergrenze = zeitpunkt - timedelta(days=fenster_tage)

    kaeufer: set = set()
    verkaeufer: set = set()
    opportunistisch: set = set()
    kauf_wert = verkauf_wert = 0.0
    n = 0

    for bekannt_ab, gehandelt, owner, code, wert in reihe:
        if bekannt_ab > obergrenze:
            # Nach `bekannt_ab` sortiert — ab hier liegt alles in der Zukunft.
            break
        if bekannt_ab <= untergrenze:
            continue
        n += 1
        # Gezählt wird über die CIK der Person. Sie fehlt in den Daten der SEC
        # nicht (gemessen an 2024Q1: 0 von 71.738 Meldenden ohne CIK); sollte
        # sie es doch einmal, fallen alle namenlosen Meldungen eines Fensters
        # zu EINER Person zusammen — die vorsichtige Richtung, weil sie die
        # Käuferzahl unterschätzt statt sie aufzublähen.
        person = owner
        if code == KAUF:
            kaeufer.add(person)
            if wert:
                kauf_wert += wert
            if kalender is not None and not ist_routine(
                    kalender, owner, gehandelt, obergrenze):
                opportunistisch.add(person)
        else:
            verkaeufer.add(person)
            if wert:
                verkauf_wert += wert

    if not n:
        return None

    gesamt = len(kaeufer) + len(verkaeufer)
    npr = None if not gesamt else (len(kaeufer) - len(verkaeufer)) / gesamt
    gesamt_opp = len(opportunistisch) + len(verkaeufer)
    npr_opp = (None if not gesamt_opp
               else (len(opportunistisch) - len(verkaeufer)) / gesamt_opp)

    return {
        "kaeufer": len(kaeufer),
        "verkaeufer": len(verkaeufer),
        "npr": npr,
        "opportunistische_kaeufer": len(opportunistisch),
        "npr_opportunistisch": npr_opp,
        "kauf_wert": kauf_wert,
        "verkauf_wert": verkauf_wert,
        "n_geschaefte": n,
    }


# ---------------------------------------------------------------------------
# Kommandozeile
# ---------------------------------------------------------------------------

def cli(von_jahr: int = 2016) -> None:
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
        ergebnis = insider_backfill(db, tickers, date(von_jahr, 1, 1))
        print(f"Quartale: {ergebnis['quartale_geladen']}/"
              f"{ergebnis['quartale']} | gelesen: {ergebnis['gelesen']} | "
              f"neu: {ergebnis['neu']}")
        if ergebnis["ohne_quartal"]:
            print(f"Ohne Datensatz: {', '.join(ergebnis['ohne_quartal'])}")
    finally:
        db.close()
