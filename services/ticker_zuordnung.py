"""
services/ticker_zuordnung.py — Von der Notierung zum SEC-Emittenten.

**Wozu.** Alle Fundamentalbestaende des Projekts (Accruals, Nettoemission,
PEAD, Analystenrevisionen, Insidergeschaefte) haengen an der CIK, und die SEC
kennt nur US-Ticker. Eine reale Watchlist mit neun Titeln war deshalb bei
acht davon blind — darunter beide offenen Positionen, obwohl hinter ABEA.DE
Alphabet und hinter ORC.DE Oracle steht und beide vollstaendig einreichen.

**Der Weg, der NICHT genommen wird.** Endung abschneiden und nachschlagen:

    ALV.DE  ist Allianz SE.       `ALV`  bei der SEC ist Autoliv.
    DTE.DE  ist Deutsche Telekom. `DTE`  bei der SEC ist DTE Energy.

Beide Ticker existieren im SEC-Verzeichnis, beide Zuordnungen waeren falsch,
und der Fehler waere still: die Kennzahlen kaemen an und saehen plausibel aus.
Der Tickerstamm ist an dieser Zuordnung deshalb **nicht beteiligt**.

**Auch nicht ueber die ISIN.** yfinance fuehrt ein Feld `isin`, aber es ist
hier unbrauchbar und zwar auf die gefaehrliche Art: fuer GOOGL liefert es
`CA02080M1005` — eine kanadische ISIN, schlicht falsch fuer Alphabet. Fuer die
meisten Frankfurter Notierungen liefert es gar nichts (`-`). Ein Feld, das
teils schweigt und teils falsch antwortet, ist schlechter als keines.

**Der Weg, der genommen wird: Firmenidentitaet.** `longName` der Notierung
gegen `title` im SEC-Verzeichnis, beide normalisiert. Verlangt wird ein
**eindeutiger Treffer auf CIK-Ebene** — nicht auf Tickerebene, denn
GOOGL/GOOG/GOOGM sind drei Ticker desselben Emittenten und sollen
zusammenfallen. Gemessen am Verzeichnis (10.422 Eintraege, 8.011
normalisierte Namen) fuehren nur **11 Namen auf mehr als eine CIK**; alles
andere ist eindeutig oder findet nichts.

**Was bewusst NICHT passiert:** kein unscharfer Abgleich, keine Teilstrings,
keine Editierdistanz. Entweder der normalisierte Name stimmt ueberein oder es
gibt keine Zuordnung. Eine fehlende Zuordnung kostet eine leere Anzeige; eine
falsche kostet eine Fehlentscheidung auf fremden Zahlen.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database import TickerZuordnung

logger = logging.getLogger(__name__)


# Rechtsformen und Fuellwoerter, die zwischen "NVIDIA Corporation" (yfinance)
# und "NVIDIA CORP" (SEC) stehen. Bewusst konservativ: je mehr hier entfernt
# wird, desto eher kollidieren zwei verschiedene Firmen zu einem Namen.
_RECHTSFORM = (
    r"\b(CORPORATION|CORP|INCORPORATED|INC|COMPANY|CO|PLC|LTD|LIMITED|LLC|"
    r"LP|NV|SA|SE|AG|HOLDINGS|HOLDING|GROUP|THE|COM|NEW|CLASS [A-C])\b"
)


def normalisieren(name: Optional[str]) -> str:
    """Firmenname auf seinen vergleichbaren Kern.

    Grossschreibung, Satzzeichen zu Leerzeichen, Rechtsformen entfernt,
    Leerraum verdichtet. `"Amazon.com, Inc."` und `"AMAZON COM INC"` ergeben
    beide `"AMAZON"`.

    Ein leerer Rest ist ein Ergebnis und kein Fehler — er fuehrt zu keiner
    Zuordnung, was richtig ist: ein Name, der nur aus einer Rechtsform
    besteht, identifiziert niemanden.
    """
    text = (name or "").upper()
    text = re.sub(r"[^A-Z0-9 ]", " ", text)
    text = re.sub(_RECHTSFORM, " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sec_namensindex() -> dict[str, list[tuple[str, str]]]:
    """Normalisierter Firmenname → [(us_ticker, cik), ...] aus dem SEC-Verzeichnis.

    Nutzt denselben Abruf wie `services/accruals.cik_zuordnung()` — die SEC
    liefert Ticker, CIK und Firmennamen in einer Datei, und ein zweiter Abruf
    waere Verschwendung.

    Returns:
        Leeres Dict, wenn das Verzeichnis nicht ladbar war. Der Aufrufer
        unterscheidet das von "Name nicht enthalten": Ersteres ist ein
        Ausfall, Letzteres ein Ergebnis.
    """
    import requests

    from services.accruals import TICKER_KARTE_URL, _kopfzeilen

    try:
        antwort = requests.get(TICKER_KARTE_URL, headers=_kopfzeilen(),
                               timeout=60)
        antwort.raise_for_status()
        eintraege = antwort.json()
    except Exception as e:
        logger.error("SEC-Tickerverzeichnis nicht ladbar: %s", e, exc_info=True)
        return {}

    index: dict[str, list[tuple[str, str]]] = {}
    for eintrag in eintraege.values():
        name = normalisieren(eintrag.get("title"))
        ticker = str(eintrag.get("ticker", "")).strip().upper()
        cik = eintrag.get("cik_str")
        if not name or not ticker or cik is None:
            continue
        index.setdefault(name, []).append((ticker, str(cik).zfill(10)))

    logger.info("SEC-Namensindex: %d Eintraege zu %d normalisierten Namen.",
                len(eintraege), len(index))
    return index


def _firmendaten(notierung: str) -> tuple[Optional[str], Optional[str]]:
    """(longName, country) einer Notierung aus yfinance.

    Getrennt gehalten, damit die Zuordnungslogik ohne Netz testbar bleibt.
    """
    import yfinance as yf

    try:
        info = yf.Ticker(notierung).info or {}
    except Exception as e:
        logger.warning("yfinance-Info fuer %s fehlgeschlagen: %s", notierung, e)
        return None, None
    return info.get("longName") or info.get("shortName"), info.get("country")


def zuordnung_bestimmen(notierung: str, firmenname: Optional[str],
                        land: Optional[str],
                        namensindex: dict[str, list[tuple[str, str]]]
                        ) -> dict:
    """Die reine Entscheidung — ohne Netz, ohne Datenbank.

    Returns:
        {"notierung", "cik", "us_ticker", "firmenname", "land", "gefunden",
         "begruendung"}

    `gefunden=False` traegt immer eine `begruendung`. Das ist kein Luxus: die
    drei Gruende (kein Name, kein Treffer, mehrdeutig) verlangen
    unterschiedliche Reaktionen — beim ersten stimmt der Ticker nicht, beim
    zweiten gibt es schlicht keinen SEC-Emittenten, beim dritten muss ein
    Mensch entscheiden.
    """
    ergebnis = {"notierung": notierung, "cik": None, "us_ticker": None,
                "firmenname": firmenname, "land": land, "gefunden": False,
                "begruendung": None}

    kern = normalisieren(firmenname)
    if not kern:
        ergebnis["begruendung"] = "kein Firmenname zur Notierung ermittelbar"
        return ergebnis

    treffer = namensindex.get(kern, [])
    if not treffer:
        ergebnis["begruendung"] = (
            f"kein SEC-Emittent mit dem Namen {kern!r} — "
            f"vermutlich kein SEC-Filer")
        return ergebnis

    ciks = {cik for _, cik in treffer}
    if len(ciks) > 1:
        # Der einzige Fall, in dem ein Mensch entscheiden muss. Lieber keine
        # Zuordnung als die falsche von zweien.
        ergebnis["begruendung"] = (
            f"mehrdeutig: {kern!r} fuehrt auf {len(ciks)} verschiedene CIKs "
            f"({', '.join(sorted(ciks))}) — manuelle Zuordnung noetig")
        return ergebnis

    # Eindeutig. Unter mehreren Tickern derselben CIK (Aktienklassen) gewinnt
    # der kuerzeste: GOOGL/GOOG/GOOGM -> GOOG, AMZN -> AMZN. Der kuerzeste ist
    # in aller Regel die Stammnotierung und der Schluessel, unter dem die
    # bestehenden Bestaende liegen.
    us_ticker = sorted((t for t, _ in treffer), key=lambda t: (len(t), t))[0]
    ergebnis.update({"cik": ciks.pop(), "us_ticker": us_ticker,
                     "gefunden": True,
                     "begruendung": f"eindeutiger Namenstreffer {kern!r}"})
    return ergebnis


def zuordnung_ermitteln(notierung: str,
                        namensindex: Optional[dict] = None) -> dict:
    """Wie `zuordnung_bestimmen`, holt Firmendaten und Index aber selbst."""
    if namensindex is None:
        namensindex = sec_namensindex()
    firmenname, land = _firmendaten(notierung)
    return zuordnung_bestimmen(notierung, firmenname, land, namensindex)


# ---------------------------------------------------------------------------
# Bestand
# ---------------------------------------------------------------------------

def zuordnung_lesen(db: Session, notierung: str) -> Optional[TickerZuordnung]:
    return db.get(TickerZuordnung, notierung)


def zuordnung_speichern(db: Session, ergebnis: dict,
                        quelle: str = "auto-name") -> TickerZuordnung:
    """Legt die Zuordnung an oder aktualisiert sie.

    Eine **manuelle** Zeile wird von einem automatischen Lauf nicht
    ueberschrieben: wer von Hand zugeordnet hat, wusste mehr als der
    Namensabgleich — typischerweise gerade in den mehrdeutigen Faellen, um
    derentwillen die Handeingabe existiert.
    """
    zeile = db.get(TickerZuordnung, ergebnis["notierung"])
    if zeile is None:
        zeile = TickerZuordnung(notierung=ergebnis["notierung"])
        db.add(zeile)
    elif zeile.quelle == "manuell" and quelle != "manuell":
        logger.debug("Zuordnung %s ist manuell — automatischer Lauf "
                     "uebersprungen.", ergebnis["notierung"])
        return zeile

    zeile.cik = ergebnis.get("cik")
    zeile.us_ticker = ergebnis.get("us_ticker")
    zeile.firmenname = ergebnis.get("firmenname")
    zeile.land = ergebnis.get("land")
    zeile.gefunden = bool(ergebnis.get("gefunden"))
    zeile.begruendung = ergebnis.get("begruendung")
    zeile.quelle = quelle
    zeile.geprueft_am = datetime.now()
    db.commit()
    return zeile


def manuell_setzen(db: Session, notierung: str, us_ticker: str,
                   cik: Optional[str] = None,
                   namensindex: Optional[dict] = None) -> TickerZuordnung:
    """Zuordnung von Hand — fuer die mehrdeutigen und die exotischen Faelle.

    Ohne `cik` wird sie aus dem SEC-Verzeichnis zum angegebenen US-Ticker
    nachgeschlagen. Das ist der uebliche Fall: ein Mensch weiss den Ticker,
    nicht die zehnstellige Nummer.
    """
    us_ticker = (us_ticker or "").strip().upper()
    if cik is None:
        from services.accruals import cik_zuordnung
        cik = cik_zuordnung().get(us_ticker)

    return zuordnung_speichern(db, {
        "notierung": notierung,
        "cik": cik,
        "us_ticker": us_ticker,
        "firmenname": None,
        "land": None,
        "gefunden": bool(cik),
        "begruendung": ("von Hand gesetzt"
                        if cik else
                        f"von Hand gesetzt, aber {us_ticker!r} steht nicht "
                        f"im SEC-Verzeichnis"),
    }, quelle="manuell")


def us_ticker_fuer(db: Session, notierung: str) -> Optional[str]:
    """Der US-Ticker zu einer Notierung — oder sie selbst, wenn sie einer ist.

    **Das ist die eine Funktion, die der Rest des Dashboards braucht.** Sie
    beantwortet: unter welchem Schluessel liegen die Fundamentaldaten zu
    diesem Titel? Fuer AMZN ist die Antwort AMZN, fuer ABEA.DE ist sie GOOG,
    fuer ALV.DE ist sie None.

    Kein Netzabruf: es wird nur gelesen, was der Zuordnungslauf hinterlegt
    hat. Ein Seitenaufruf darf nicht an der SEC haengen.
    """
    if "." not in notierung:
        # Ein US-Ticker traegt kein Boersenkuerzel. Er ist sein eigener
        # Schluessel, ohne dass dafuer eine Zeile noetig waere.
        return notierung.upper()

    zeile = db.get(TickerZuordnung, notierung)
    if zeile is None or not zeile.gefunden:
        return None
    return zeile.us_ticker


def zuordnungen_auffrischen(db: Session, notierungen: list[str]) -> dict:
    """Ermittelt fehlende Zuordnungen fuer eine Liste von Notierungen.

    Bereits geprueft heisst nicht erneut pruefen — auch ein `gefunden=False`
    ist ein Ergebnis und wird nicht bei jedem Lauf neu erfragt. Wer eine
    Zeile erneuern will, loescht sie.

    Returns:
        {"geprueft", "neu", "gefunden", "ohne_treffer", "mehrdeutig",
         "uebersprungen"}
    """
    statistik = {"geprueft": 0, "neu": 0, "gefunden": 0, "ohne_treffer": 0,
                 "mehrdeutig": 0, "uebersprungen": 0}

    offen = [n for n in dict.fromkeys(notierungen)
             if "." in n and db.get(TickerZuordnung, n) is None]
    statistik["uebersprungen"] = len(set(notierungen)) - len(offen)
    if not offen:
        return statistik

    namensindex = sec_namensindex()
    if not namensindex:
        logger.error("Kein SEC-Namensindex — Zuordnungslauf abgebrochen, "
                     "es wird nichts geschrieben.")
        return statistik

    for notierung in offen:
        statistik["geprueft"] += 1
        ergebnis = zuordnung_ermitteln(notierung, namensindex)
        zuordnung_speichern(db, ergebnis)
        statistik["neu"] += 1
        if ergebnis["gefunden"]:
            statistik["gefunden"] += 1
        elif "mehrdeutig" in (ergebnis.get("begruendung") or ""):
            statistik["mehrdeutig"] += 1
        else:
            statistik["ohne_treffer"] += 1

    logger.info("Zuordnungslauf: %d geprueft, %d gefunden, %d ohne Treffer, "
                "%d mehrdeutig.", statistik["geprueft"], statistik["gefunden"],
                statistik["ohne_treffer"], statistik["mehrdeutig"])
    return statistik
