"""
snapshot_engine/auswertung/groesse.py — Groessenklassen fuer die Gegenprobe zu §2p.

**Wozu.** §2p misst die Nettoemission gegen die *gepoolte* Marktbasis. Emittenten
sind aber systematisch kleinere Titel, und §2d hat fuer die Sektoren gezeigt, was
das anrichtet: die unbedingte Marktquote schwankt zwischen den Gruppen um 6,6 pp,
weit ausserhalb der Fehlerspanne. Wer nach einem Merkmal trennt, das mit der
Groesse laeuft, und dann gegen den Pool rechnet, misst den Groessenunterschied
statt des Signals. Dieses Modul liefert die Schichtung, mit der sich das trennen
laesst.

**Das Groessenmass ist der mittlere Dollar-Umsatz (`schluss * volumen`), nicht die
Marktkapitalisierung.** Das ist eine Messentscheidung, keine Bequemlichkeit:

Eine Kapitalisierung entstuende hier aus der rohen SEC-Aktienzahl
(`NettoemissionKennzahl.aktien`) mal einem Kurs aus `KursHistorie` — und diese
Kursreihe ist **rueckwirkend split-bereinigt**, die Aktienzahl dagegen steht auf
der Split-Basis ihrer Einreichung. Gemessen an NVDA ergaebe das:

    Einreichung 2021-02-26:    620,0 Mio Aktien x  13,66 =     8,5 Mrd
    Einreichung 2024-02-21:  2.464,0 Mio Aktien x  67,35 =   166,0 Mrd
    Einreichung 2025-02-26: 24.477,0 Mio Aktien x 131,08 = 3.208,5 Mrd

Der Fehler ist der **kumulierte Splitfaktor seit der Einreichung** — 2021 rund
Faktor 40. NVDA laege damit fuer den groessten Teil seiner Geschichte in der
kleinsten Groessenklasse. Der Fehler trifft bevorzugt die starken Kurssteiger,
also genau die Titel, deren Einordnung ueber das Ergebnis entscheidet. §2p hat
die Split-Falle bei der Kennzahl selbst ueber die gemeinsame `accession` geloest
und dafuer ausdruecklich **keinen** Splitbestand als eigene Quelle aufgenommen;
eine Kapitalisierung wuerde ihn hier durch die Hintertuer noetig machen.

Der Dollar-Umsatz hat die Falle nicht. yfinance bereinigt Kurs **und** Volumen
mit demselben Faktor, das Produkt ist daher split-invariant. Gemessen an NVDA um
den 10:1-Split vom 2024-06-10:

    2024-06-07   120,68 x 412.386.000 = 49,8 Mrd
    2024-06-10   121,58 x 313.434.100 = 38,1 Mrd

Kein Sprung. Der Dollar-Umsatz ist zudem zu 100 % im Bestand gedeckt (9,25 Mio
Zeilen), punkt-in-zeit aus der Kursreihe konstruierbar und in der Literatur das
uebliche Mass fuer Groesse und Handelbarkeit zugleich. Dass er Liquiditaet mit
misst, ist fuer diese Frage ein Vorteil und kein Mangel: der Einwand gegen §2p
lautet "kleine, illiquide, volatile Titel", und genau das faengt er ein.

**Look-ahead.** Das Fenster endet am Tag VOR dem Stichtag. `bisect_left` liefert
den ersten Handelstag >= Stichtag, das Fenster ist `[ende - n, ende)` und damit
strikt davor. Das ist die Eigenschaft, die `tests/test_groesse.py` festhaelt.
"""

import logging
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from database import KursHistorie
from services.cross_sectional_momentum import raenge_je_woche

logger = logging.getLogger(__name__)


# Handelstage im Rueckblickfenster. 60 statt 20: ein Quartal glaettet einzelne
# Umsatzspitzen (Index-Aufnahme, Quartalszahlen), ohne dass die Klasse traege
# gegenueber einem echten Groessenwechsel wird.
FENSTER_TAGE = 60

# Weniger Handelstage als das sind kein Mittelwert, sondern ein Zufall. Trifft
# vor allem Neuemissionen am linken Rand ihrer Reihe — die fallen heraus.
MIN_TAGE = 20

# Klassen der Schichtung. Fuenf wie die Quintile der Kennzahl selbst, damit die
# Tabelle in beiden Richtungen dieselbe Aufloesung hat.
KLASSEN = 5

MIN_QUERSCHNITT = 20


def _reihe_laden(db: Session, ticker: str
                 ) -> tuple[list[datetime], list[float]]:
    """Datum und Dollar-Umsatz eines Tickers als zwei parallele Listen.

    Dieselbe Bauform wie `kurspanel._reihe_laden` und aus demselben Grund: je
    Ticker folgen einige hundert bis tausend Nachschlaege, und `bisect` auf
    einer Liste ist dafuer um Groessenordnungen billiger als ein Index-Zugriff.

    Tage ohne Umsatz bleiben mit 0,0 stehen statt herauszufallen. Sie sind eine
    echte Eigenschaft des Titels (Handelsaussetzung, sehr duenner Handel), und
    wer sie entfernt, macht illiquide Titel kuenstlich liquider — also genau
    den Fehler, den diese Schichtung aufdecken soll.
    """
    zeilen = (
        db.query(KursHistorie.datum, KursHistorie.schluss, KursHistorie.volumen)
        .filter(KursHistorie.ticker == ticker)
        .filter(KursHistorie.schluss.isnot(None))
        .filter(KursHistorie.volumen.isnot(None))
        .order_by(KursHistorie.datum)
        .all()
    )
    return ([z[0] for z in zeilen],
            [float(z[1]) * float(z[2]) for z in zeilen])


def dollar_umsatz_je_beobachtung(db: Session, zuordnung: dict[int, tuple],
                                 fenster: int = FENSTER_TAGE,
                                 mindest_tage: int = MIN_TAGE
                                 ) -> dict[int, float]:
    """Mittlerer taeglicher Dollar-Umsatz VOR dem Stichtag, je Beobachtung.

    Args:
        zuordnung: {beobachtung_id: (ticker, zeitpunkt)} — dieselbe Form, die
            `kurspanel.als_auswertungsform` liefert.
        fenster: Handelstage Rueckblick.
        mindest_tage: Weniger belegte Tage im Fenster heisst kein Wert.

    Returns:
        {beobachtung_id: mittlerer Dollar-Umsatz}. Beobachtungen ohne Reihe,
        mit zu kurzem Fenster oder mit Umsatz 0 fehlen — sie bekommen keine
        Klasse und fallen aus der Schichtung, statt eine falsche zu erben.
    """
    je_ticker: dict[str, list[tuple[int, datetime]]] = defaultdict(list)
    for beobachtung_id, (ticker, zeitpunkt) in zuordnung.items():
        je_ticker[ticker].append((beobachtung_id, zeitpunkt))

    ergebnis: dict[int, float] = {}
    ohne_reihe = zu_kurz = ohne_umsatz = 0

    for ticker, eintraege in je_ticker.items():
        daten, umsaetze = _reihe_laden(db, ticker)
        if not daten:
            ohne_reihe += len(eintraege)
            continue

        # Praefixsummen: damit kostet jedes Fenster zwei Nachschlaege statt
        # einer Schleife ueber 60 Tage. Bei 1,2 Mio Beobachtungen ist das der
        # Unterschied zwischen Minuten und Stunden.
        kumuliert = [0.0] * (len(umsaetze) + 1)
        for i, wert in enumerate(umsaetze):
            kumuliert[i + 1] = kumuliert[i] + wert

        for beobachtung_id, zeitpunkt in eintraege:
            # Erster Handelstag >= Stichtag. Das Fenster endet davor, also ist
            # der Stichtag selbst nicht enthalten — kein Look-ahead.
            ende = bisect_left(daten, zeitpunkt)
            start = max(0, ende - fenster)
            tage = ende - start
            if tage < mindest_tage:
                zu_kurz += 1
                continue
            mittel = (kumuliert[ende] - kumuliert[start]) / tage
            if mittel <= 0:
                ohne_umsatz += 1
                continue
            ergebnis[beobachtung_id] = mittel

    logger.info(
        "Dollar-Umsatz: %d von %d Beobachtungen belegt "
        "(%d ohne Reihe, %d Fenster zu kurz, %d ohne Umsatz).",
        len(ergebnis), len(zuordnung), ohne_reihe, zu_kurz, ohne_umsatz)
    return ergebnis


def groessen_klasse(rang: Optional[float], klassen: int = KLASSEN
                    ) -> Optional[int]:
    """Klasse 1..n zu einem Perzentilrang; **1 ist die kleinste**.

    Die Richtung ist bewusst so herum und entgegengesetzt zu `quintil` in
    `nettoemission.py`: dort traegt Q1 die Hypothese, hier ist Klasse 1 schlicht
    der duennste Handel. Wer beide Skalen gleich liest, vertauscht die Enden.
    """
    if rang is None:
        return None
    return min(klassen, int(rang // (100 / klassen)) + 1)


def groessen_klassen(db: Session, zuordnung: dict[int, tuple],
                     gruppe_fuer: Callable[[str], Optional[str]],
                     klassen: int = KLASSEN,
                     fenster: int = FENSTER_TAGE,
                     minimum_querschnitt: int = MIN_QUERSCHNITT
                     ) -> tuple[dict[int, int], dict[int, float]]:
    """Ordnet jeder Beobachtung ihre Groessenklasse zu.

    Gerangt wird je Kalenderwoche und Handelsplatz — dieselben Eimer wie
    `nettoemission_raenge`, und aus demselben Grund: eine Rangliste ueber Xetra
    und US gemeinsam wiese den Waehrungsunterschied als Groesse aus, und eine
    ueber alle Jahre gemeinsam wiese das Wachstum der Boersenumsaetze als
    Groessenwechsel aus. Ein Titel, dessen Umsatz mit dem Markt mitwaechst, soll
    seine Klasse behalten.

    Returns:
        ({beobachtung_id: klasse 1..n}, {beobachtung_id: Dollar-Umsatz})
    """
    werte = dollar_umsatz_je_beobachtung(db, zuordnung, fenster=fenster)
    raenge = raenge_je_woche(werte, zuordnung, gruppe_fuer,
                             minimum_querschnitt)

    zugeordnet: dict[int, int] = {}
    for beobachtung_id, rang in raenge.items():
        k = groessen_klasse(rang, klassen)
        if k is not None:
            zugeordnet[beobachtung_id] = k

    verteilung: dict[int, int] = defaultdict(int)
    for k in zugeordnet.values():
        verteilung[k] += 1
    logger.info("Groessenklassen: %d Beobachtungen eingeordnet, Verteilung %s.",
                len(zugeordnet), dict(sorted(verteilung.items())))
    return zugeordnet, werte
