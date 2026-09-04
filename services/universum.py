"""
services/universum.py — Welche Titel gemessen werden, und welche fehlen (Auftrag C).

Zwei Fragen, die bisher vermischt waren und hier getrennt beantwortet werden.

**Frage 1: Welche Titel sollen in den Bestand?** Bis hierher war das
Universum der Screener-Bestand — S&P 500 plus DAX/MDAX, rund 650 grosse,
liquide Werte. Die Literaturrecherche aus `LITERATUR.md` sagt zu diesem
Zuschnitt etwas Unangenehmes: Anomalien konzentrieren sich in kleinen Firmen,
und ab 2006 ohne Microcaps liegt der Median der replizierten Effekte bei
7 Basispunkten im Monat (Chen/Velikov 2023). Ein reines Large-Cap-Universum
ueber 2017-2026 ist damit der Ort und der Zeitraum, an dem am wenigsten zu
finden ist — was den neunfachen Nullbefund erklaeren koennte, ohne dass an
der Messung etwas falsch waere. `handelbares_universum()` baut deshalb den
breiteren Zuschnitt: NASDAQ, NYSE und AMEX ohne Fonds, ETFs, Vorzuege,
Optionsscheine und Bezugsrechte.

**Frage 2: Welche Titel fehlen, und wie sehr faellt das ins Gewicht?** Das
ist die Frage, an der die erste haengt, und sie wurde bisher nur als Warnung
notiert. Sie ist jetzt gemessen — siehe `database.EmittentPunktInZeit`.

**Der Befund, der die naheliegende Abhilfe entwertet.** Ein groesseres
Universum behebt Survivorship nicht. `data/stock_listings.csv` fuehrt die
HEUTE gelisteten Symbole; jeder Ticker darin hat per Konstruktion ueberlebt.
Aus 500 Ueberlebenden werden 5.216 Ueberlebende — der Anteil bleibt bei
100 Prozent. Was sich aendert, ist die Groessenverteilung, nicht die Auswahl
nach Ueberleben. Beides wurde in `CONTEXT.md` unter einem Stichwort gefuehrt;
es sind zwei Probleme, und nur das erste loest Auftrag C.

**Was hier stattdessen moeglich ist: die Luecke beziffern.** Die
vierteljaehrlichen Form-345-Datensaetze der SEC nennen zu jeder Einreichung
das Handelssymbol des Emittenten — auch fuer Firmen, die es heute nicht mehr
gibt. Daraus entsteht eine Emittentenliste, die Ueberlebende nicht bevorzugt:
**11.921 Ticker fuer 2016Q1-2026Q1**, gegen 4.024, die heute noch handelbar
gelistet sind. `abdeckung()` haelt zu jedem Befund fest, wie viele der damals
existierenden Emittenten er gesehen hat.

Die Daten dafuer liegen bereits auf der Platte — es sind dieselben ZIPs, die
`services/insider.py` fuer Auftrag B geladen hat. Kein zusaetzlicher Abruf.

**Grenze der Aussage.** Ein fehlender Ticker ist kein Totalverlust. Gemessen
an den Transaktionskursen der Form-4-Daten selbst verlassen die Verschwundenen
den Bestand zweigeteilt: 20,8 Prozent unter dem halben Vorjahreskurs,
22,5 Prozent ueber dem Anderthalbfachen. Wer Verschwinden pauschal als
Ausfall verbucht, verzerrt in die Gegenrichtung.
"""

import logging
import re
from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database import EmittentPunktInZeit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handelbares Universum aus dem Listing-Verzeichnis
# ---------------------------------------------------------------------------

# NYSE ARCA und BATS sind fast vollstaendig ETF-Plaetze (2.729 bzw. 1.616
# Zeilen), OTC ist mit 3.818 Zeilen der groesste Block und nicht sinnvoll
# handelbar. Bleiben die drei Plaetze, an denen amerikanische Stammaktien
# notieren.
BOERSEN = ("NASDAQ", "NYSE", "AMEX")

# Namensbestandteile, die kein Unternehmensanteil sind. Der Filter greift auf
# dem Namen und nicht auf dem Kuerzel, weil das Listing-Verzeichnis die Gattung
# im Klartext fuehrt ("... - Warrants", "... Common Stock"). Gemessen an der
# Datei vom 2026-09-04: 8.838 Zeilen an den drei Plaetzen, davon 3.622
# aussortiert, 5.216 bleiben.
_AUSSCHLUSS = re.compile(
    r"\b(ETFs?|ETNs?|ETVs?|Funds?|Trust|Depositary|Preferred|Warrants?"
    r"|Rights?|Units?|Notes?|Debentures?|Bonds?|Index|Portfolio"
    r"|SPDR|iShares|Invesco|ProShares|Direxion|VanEck|WisdomTree|Vanguard)\b",
    re.IGNORECASE)


def handelbares_universum(nur_mit_sec_historie: bool = False,
                          db: Optional[Session] = None) -> list[str]:
    """Amerikanische Stammaktien an NASDAQ, NYSE und AMEX.

    Args:
        nur_mit_sec_historie: Schraenkt auf Ticker ein, die im
            punkt-in-zeit-Bestand vorkommen, also mindestens eine Form-4-
            Einreichung seit 2016 tragen. Das entfernt Neuemissionen ohne
            Historie und auslaendische Emittenten ohne SEC-Meldepflicht —
            fuer die Insider-Gegenprobe der richtige Zuschnitt, fuer eine
            reine Kursmessung ein unnoetiger Verlust.
        db: Nur noetig, wenn `nur_mit_sec_historie` gesetzt ist.

    Returns:
        Sortierte, doppelfreie Kuerzelliste. Leer, wenn das Verzeichnis
        nicht lesbar ist — der Aufrufer muss das behandeln, ein leeres
        Universum darf nicht stillschweigend als Ergebnis durchgehen.
    """
    from services.cache_core import cached_listings

    verzeichnis = cached_listings()
    if verzeichnis is None or verzeichnis.empty:
        logger.error("Universum: Listing-Verzeichnis nicht lesbar.")
        return []

    spalten = list(verzeichnis.columns)
    kuerzel_spalte, name_spalte, boerse_spalte = spalten[0], spalten[1], spalten[2]

    gefiltert = verzeichnis[verzeichnis[boerse_spalte].isin(BOERSEN)]
    namen = gefiltert[name_spalte].fillna("").astype(str)
    gefiltert = gefiltert[~namen.str.contains(_AUSSCHLUSS, regex=True)]

    tickers = {
        t.strip().upper()
        for t in gefiltert[kuerzel_spalte].dropna().astype(str)
        if t and t.strip()
    }

    if nur_mit_sec_historie:
        if db is None:
            raise ValueError("nur_mit_sec_historie verlangt eine DB-Session.")
        bekannt = {t for (t,) in db.query(EmittentPunktInZeit.ticker)}
        vorher = len(tickers)
        tickers &= bekannt
        logger.info("Universum: %d von %d Tickern mit SEC-Historie.",
                    len(tickers), vorher)

    logger.info("Universum: %d handelbare Stammaktien an %s.",
                len(tickers), "/".join(BOERSEN))
    return sorted(tickers)


# ---------------------------------------------------------------------------
# Punkt-in-Zeit-Emittentenliste aus den Form-345-Datensaetzen
# ---------------------------------------------------------------------------

def _quartal_kennzeichen(jahr: int, quartal: int) -> str:
    """'2024q1' — als Text sortierbar, weil das Quartal einstellig ist."""
    return f"{jahr}q{quartal}"


def emittenten_aus_archiv(daten: bytes) -> dict[str, dict]:
    """Emittenten eines Quartalsstandes, mit Kauf- und Cluster-Kennzeichen.

    Anders als `services.insider.geschaefte_aus_archiv` wird hier **nicht**
    nach einem Universum gefiltert — der Sinn dieser Liste ist ja gerade,
    die Titel zu erfassen, die in keinem heutigen Universum mehr stehen.

    Returns:
        ticker -> {"kauf": bool, "cluster": bool}. `cluster` ist wahr, wenn
        mindestens zwei VERSCHIEDENE Personen in diesem Quartal am Markt
        gekauft haben — das Kriterium aus Paragraph 2n, hier auf Quartals-
        statt auf Halbjahresfenster, weil die Datei quartalsweise vorliegt.
        Es dient der Abdeckungsfrage, nicht der Messung.
    """
    import io
    import zipfile
    from collections import defaultdict

    from services.insider import DOKUMENTTYP, ERWARTET_AD, KAUF, _tsv

    archiv = zipfile.ZipFile(io.BytesIO(daten))

    # Einreichung -> Ticker. Nur Form 4; Form 3 (Ersteintrag) und Form 5
    # (Nachtrag) tragen keine Handelsentscheidung.
    einreichung_ticker: dict[str, str] = {}
    for zeile in _tsv(archiv, "SUBMISSION.tsv"):
        if (zeile.get("DOCUMENT_TYPE") or "").strip() != DOKUMENTTYP:
            continue
        ticker = (zeile.get("ISSUERTRADINGSYMBOL") or "").strip().upper()
        if ticker:
            einreichung_ticker[zeile["ACCESSION_NUMBER"]] = ticker

    # Einreichung -> Person. Bei Gemeinschaftsmeldungen der erste Treffer;
    # fuer das Zaehlen VERSCHIEDENER Kaeufer reicht das, weil eine
    # Gemeinschaftsmeldung ohnehin eine Entscheidung ist.
    einreichung_person: dict[str, str] = {}
    for zeile in _tsv(archiv, "REPORTINGOWNER.tsv"):
        nummer = zeile.get("ACCESSION_NUMBER")
        if nummer in einreichung_ticker and nummer not in einreichung_person:
            einreichung_person[nummer] = (
                (zeile.get("RPTOWNERCIK") or "").strip() or nummer)

    kaeufer: dict[str, set] = defaultdict(set)
    for zeile in _tsv(archiv, "NONDERIV_TRANS.tsv"):
        code = (zeile.get("TRANS_CODE") or "").strip().upper()
        if code != KAUF:
            continue
        # Dieselbe Widerspruchspruefung wie in services/insider.py: 0,19
        # Prozent der Zeilen kennzeichnen einen Kauf als Veraeusserung.
        ad = (zeile.get("TRANS_ACQUIRED_DISP_CD") or "").strip().upper()
        if ad and ad != ERWARTET_AD[code]:
            continue
        nummer = zeile.get("ACCESSION_NUMBER", "")
        ticker = einreichung_ticker.get(nummer)
        if ticker is None:
            continue
        kaeufer[ticker].add(einreichung_person.get(nummer, nummer))

    ergebnis: dict[str, dict] = {
        t: {"kauf": False, "cluster": False} for t in einreichung_ticker.values()
    }
    for ticker, personen in kaeufer.items():
        ergebnis[ticker]["kauf"] = True
        ergebnis[ticker]["cluster"] = len(personen) >= 2
    return ergebnis


def pit_aufbauen(db: Session, von: Optional[date] = None,
                 bis: Optional[date] = None) -> dict:
    """Baut oder aktualisiert `EmittentPunktInZeit` aus den Quartals-ZIPs.

    Idempotent: ein erneuter Lauf zaehlt nicht doppelt, sondern rechnet die
    Quartalsmengen je Ticker neu aus. Die ZIPs kommen aus dem Zwischenspeicher
    von `services/insider.py`, ein zweiter Download findet nicht statt.

    Returns:
        {"emittenten": int, "quartale": int, "heute_gelistet": int}
    """
    from services.insider import quartal_laden, quartale

    von = von or date(2016, 1, 1)
    bis = bis or date.today()

    # ticker -> {"quartale": set, "kauf": set, "cluster": set}
    sammlung: dict[str, dict[str, set]] = {}
    gelesen = 0

    for jahr, quartal in quartale(von, bis):
        daten = quartal_laden(jahr, quartal)
        if daten is None:
            continue
        kennung = _quartal_kennzeichen(jahr, quartal)
        try:
            emittenten = emittenten_aus_archiv(daten)
        except Exception as e:
            logger.error("Form-345-Archiv %s nicht lesbar: %s", kennung, e,
                         exc_info=True)
            continue
        gelesen += 1
        for ticker, kennzeichen in emittenten.items():
            eintrag = sammlung.setdefault(
                ticker, {"quartale": set(), "kauf": set(), "cluster": set()})
            eintrag["quartale"].add(kennung)
            if kennzeichen["kauf"]:
                eintrag["kauf"].add(kennung)
            if kennzeichen["cluster"]:
                eintrag["cluster"].add(kennung)
        logger.info("Punkt-in-Zeit %s: %d Emittenten.", kennung, len(emittenten))

    if not sammlung:
        logger.warning("Punkt-in-Zeit: kein einziges Quartal lesbar.")
        return {"emittenten": 0, "quartale": 0, "heute_gelistet": 0}

    # Heutiger Listing-Stand, einmal gelesen. Fehlt das Verzeichnis, bleibt
    # `heute_gelistet` unangetastet statt faelschlich auf False zu fallen.
    heute: dict[str, str] = {}
    from services.cache_core import cached_listings
    verzeichnis = cached_listings()
    if verzeichnis is not None and not verzeichnis.empty:
        spalten = list(verzeichnis.columns)
        for kuerzel, boerse in zip(verzeichnis[spalten[0]], verzeichnis[spalten[2]]):
            if kuerzel and str(kuerzel).strip():
                heute[str(kuerzel).strip().upper()] = str(boerse).strip()
    else:
        logger.warning("Punkt-in-Zeit: Listing-Verzeichnis fehlt, "
                       "heute_gelistet bleibt unbestimmt.")

    vorhanden = {e.ticker: e for e in db.query(EmittentPunktInZeit)}
    jetzt = datetime.now()
    gelistet = 0

    for ticker, eintrag in sammlung.items():
        satz = vorhanden.get(ticker)
        if satz is None:
            satz = EmittentPunktInZeit(ticker=ticker)
            db.add(satz)
        satz.erstes_quartal = min(eintrag["quartale"])
        satz.letztes_quartal = max(eintrag["quartale"])
        satz.quartale_aktiv = len(eintrag["quartale"])
        satz.quartale_mit_kauf = len(eintrag["kauf"])
        satz.quartale_mit_cluster = len(eintrag["cluster"])
        if heute:
            satz.heute_gelistet = ticker in heute
            satz.heute_boerse = heute.get(ticker)
            if satz.heute_gelistet:
                gelistet += 1
        satz.geprueft_am = jetzt

    db.commit()
    logger.info("Punkt-in-Zeit: %d Emittenten aus %d Quartalen, "
                "%d heute gelistet.", len(sammlung), gelesen, gelistet)
    return {"emittenten": len(sammlung), "quartale": gelesen,
            "heute_gelistet": gelistet}


# ---------------------------------------------------------------------------
# Abdeckung: was hat eine Messung gesehen, und was fehlt ihr
# ---------------------------------------------------------------------------

def abdeckung(db: Session, tickers: Iterable[str],
              von_jahr: int = 2016, bis_jahr: int = 2019) -> dict:
    """Wie viel des damaligen Emittentenbestandes deckt eine Tickermenge ab?

    Der Vergleichszeitraum endet bewusst frueh (Vorgabe 2016-2019): nur
    Emittenten, die lange genug zurueckliegen, hatten ueberhaupt Gelegenheit
    zu verschwinden. Wer gegen 2025 vergleicht, misst vor allem, dass
    Delisting Zeit braucht — 2025 sind noch 53,6 Prozent gelistet, bei den
    2016ern 12,4 Prozent.

    Returns:
        {"universum": int, "gesehen": int, "anteil": float,
         "fehlend": int, "fehlend_mit_cluster": int,
         "ueberlebensquote_gesehen": float, "ueberlebensquote_fehlend": float}

        `ueberlebensquote_*` ist die Kennzahl, auf die es ankommt. Liegt sie
        bei den gesehenen Tickern deutlich hoeher als bei den fehlenden, hat
        die Messung Ueberlebende bevorzugt — und zwar in dem Mass.
    """
    gesucht = {t.strip().upper() for t in tickers if t and t.strip()}

    bestand = [
        e for e in db.query(EmittentPunktInZeit)
        if von_jahr <= int(e.erstes_quartal[:4]) <= bis_jahr
        or int(e.erstes_quartal[:4]) <= von_jahr <= int(e.letztes_quartal[:4])
    ]
    if not bestand:
        logger.warning("Abdeckung: kein Punkt-in-Zeit-Bestand fuer %d-%d. "
                       "Wurde pit_aufbauen() ausgefuehrt?", von_jahr, bis_jahr)
        return {"universum": 0, "gesehen": 0, "anteil": 0.0, "fehlend": 0,
                "fehlend_mit_cluster": 0, "ueberlebensquote_gesehen": 0.0,
                "ueberlebensquote_fehlend": 0.0}

    gesehen = [e for e in bestand if e.ticker in gesucht]
    fehlend = [e for e in bestand if e.ticker not in gesucht]

    def quote(menge: list) -> float:
        if not menge:
            return 0.0
        return sum(1 for e in menge if e.heute_gelistet) / len(menge)

    ergebnis = {
        "universum": len(bestand),
        "gesehen": len(gesehen),
        "anteil": len(gesehen) / len(bestand),
        "fehlend": len(fehlend),
        "fehlend_mit_cluster": sum(1 for e in fehlend if e.quartale_mit_cluster),
        "ueberlebensquote_gesehen": quote(gesehen),
        "ueberlebensquote_fehlend": quote(fehlend),
    }
    logger.info("Abdeckung %d-%d: %d von %d Emittenten (%.1f %%); "
                "Ueberlebensquote gesehen %.1f %% gegen fehlend %.1f %%.",
                von_jahr, bis_jahr, ergebnis["gesehen"], ergebnis["universum"],
                100 * ergebnis["anteil"],
                100 * ergebnis["ueberlebensquote_gesehen"],
                100 * ergebnis["ueberlebensquote_fehlend"])
    return ergebnis


def abdeckung_text(werte: dict) -> str:
    """Einzeiler fuer die Oberflaeche und die Protokolle.

    Bewusst ohne Wertung: die Zahl gehoert neben jeden Befund, die Deutung
    macht der Leser. Ein Satz, der "unbedenklich" sagen wuerde, waere genau
    die Art von erfundener Empfehlung, die Paragraph 2m entfernt hat.
    """
    if not werte.get("universum"):
        return "Abdeckung unbekannt — kein Punkt-in-Zeit-Bestand."
    return (
        f"Gesehen: {werte['gesehen']} von {werte['universum']} damaligen "
        f"Emittenten ({100 * werte['anteil']:.1f} %). "
        f"Von den {werte['fehlend']} fehlenden sind heute noch "
        f"{100 * werte['ueberlebensquote_fehlend']:.1f} % gelistet, "
        f"von den gesehenen {100 * werte['ueberlebensquote_gesehen']:.1f} %."
    )
