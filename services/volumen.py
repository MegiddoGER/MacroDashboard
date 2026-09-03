"""
services/volumen.py — Der erste Eingang, der wirklich Volumen misst.

**Warum es ihn bisher nicht gab.** Die Kategorie „volume" der Engine misst
kein Volumen: VWMA ist Momentum(20), OBV-Slope ist Momentum(20), POC ist
Momentum(252). Drei Momentum-Messungen mit einem Order-Flow-Etikett (BC-01).
Echter Umsatz, Umsatzspitzen, Volumen bei Ausbrüchen — davon stand in keinem
der 188.347 Snapshots etwas, und deshalb ist dies die einzige Kategorie, über
die es **gar keine** Messung gibt, nicht einmal eine negative.

Möglich wird das erst durch `database.KursHistorie`: 1,47 Mio Handelstage mit
Volumen, ohne einen einzigen neuen Abruf.

**Warum Volumen und Spanne zusammen.** Gefragt ist der Fußabdruck der
Marktteilnehmer. Aus Kursdaten sind Broker nicht sichtbar — sichtbar ist, was
sie hinterlassen: wie viel gehandelt wurde, wie weit der Kurs innerhalb eines
Tages lief, und wie viel über Nacht passierte, während die Börse zu war. Die
letzten beiden sind kein Volumen, gehören aber zur selben Frage und kosten
dieselbe Reihe.

**Median statt Mittelwert, durchgehend.** Tagesvolumen hat schwere Ränder:
ein einzelner Indexumbau oder Verfallstag trägt das Zehnfache eines normalen
Tages. Ein Mittelwert bildete danach wochenlang eine Normalität ab, die es nie
gab.

**Kein Look-ahead.** Jedes Fenster endet am Stichtag EINSCHLIESSLICH. Das
Volumen des Stichtags ist zum Handelsschluss bekannt, genau wie sein
Schlusskurs — dieselbe Festlegung wie in `services/stetige_indikatoren`.

**Bekannte Grenze: Splits.** yfinance liefert bereinigte Reihen, aber ein
Split innerhalb eines Fensters verschiebt das Volumen sprunghaft gegen seinen
eigenen Median. Die Median-Form dämpft das, hebt es aber nicht auf; betroffen
sind die rund zehn Tage nach einem Split. Bei einigen Splits je Titel und
Jahrzehnt ist das ein sehr kleiner Anteil der Beobachtungen — dokumentiert,
nicht korrigiert, weil eine Split-Erkennung hier mehr Annahmen einführte als
sie beseitigt.
"""

from __future__ import annotations

import logging
from bisect import bisect_right
from datetime import datetime
from statistics import median
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


# Fenster in HANDELSTAGEN — anders als in `stetige_indikatoren`, wo wegen der
# Snapshot-Kadenz in Kalendertagen gerechnet werden musste. Hier liegt jede
# Zeile auf einem Handelstag, eine Umrechnung wäre Scheingenauigkeit in die
# andere Richtung.
FENSTER_KURZ = 20
FENSTER_LANG = 60

# Ab hier gilt ein Tag als Bewegung, an der sich Volumen messen lässt. Nicht
# `MIN_BEWEGUNG_PCT` (0,3 %) aus der Outcome-Bewertung: dort geht es um die
# Frage, ob sich überhaupt etwas bewegt hat, hier um einen Tag, den jemand
# bemerkt hätte.
AUSBRUCH_PCT = 2.0

# Ein Median aus weniger Tagen beschreibt die Lücke, nicht den Titel.
MIN_TAGE = 10


def _fenster(reihe: Sequence[tuple], zeitpunkt: datetime, tage: int,
             daten: Optional[Sequence[datetime]] = None) -> list[tuple]:
    """Die letzten `tage` Zeilen bis EINSCHLIESSLICH `zeitpunkt`.

    `reihe` muss nach Datum aufsteigend sortiert sein — so wie
    `services.kurshistorie.reihe_lesen` sie liefert.

    `daten` ist die Datumsspalte derselben Reihe. Sie hier hineinzureichen
    statt sie zu bauen ist kein Feinschliff: der Aufruf erfolgt je Snapshot,
    Kennzahl und Fenster, und die Spalte bei jedem Mal neu aufzubauen macht
    aus einem Sprung einen Durchlauf über die ganze Reihe. Bei 188.347
    Snapshots ist das der Unterschied zwischen Minuten und Stunden.
    """
    if not reihe:
        return []
    if daten is None:
        daten = [z[0] for z in reihe]
    ende = bisect_right(daten, zeitpunkt)
    if ende == 0:
        return []
    return list(reihe[max(0, ende - tage):ende])


def _median(werte: Sequence[Optional[float]]) -> Optional[float]:
    sauber = [w for w in werte if w is not None]
    if len(sauber) < MIN_TAGE:
        return None
    return median(sauber)


def relatives_volumen(fenster: Sequence[tuple]) -> Optional[float]:
    """Volumen des Stichtags gegen den Median der Vortage.

    1,0 heisst „ein ganz normaler Tag", 3,0 heisst „dreimal so viel Umsatz wie
    üblich". Der Stichtag selbst bleibt aus dem Vergleichsmedian heraus — sonst
    vergliche man ihn teilweise mit sich selbst, und ein einzelner Ausreisser
    hübe seine eigene Bezugsgrösse an.
    """
    if len(fenster) < MIN_TAGE + 1:
        return None
    heute = fenster[-1][5]
    if heute is None:
        return None
    basis = _median([z[5] for z in fenster[:-1]])
    if not basis:
        return None
    return heute / basis


def volumen_trend(kurz: Sequence[tuple], lang: Sequence[tuple]) -> Optional[float]:
    """Umsatz der letzten 20 Tage gegen den der letzten 60.

    Über 1 heisst „das Interesse an diesem Titel nimmt zu". Anders als
    `relatives_volumen` eine Aussage über Wochen statt über einen Tag.
    """
    kurz_median = _median([z[5] for z in kurz])
    lang_median = _median([z[5] for z in lang])
    if not kurz_median or not lang_median:
        return None
    return kurz_median / lang_median


def ausbruchs_bestaetigung(fenster: Sequence[tuple]) -> Optional[float]:
    """Kommen die grossen Tage mit Umsatz — oder ohne?

    Mittleres relatives Volumen an den Tagen des Fensters, an denen sich der
    Kurs um mindestens `AUSBRUCH_PCT` bewegt hat. Über 1 heisst: die
    Bewegungen tragen Umsatz. Das ist die klassische Lesart des Lehrbuchs, und
    sie ist in dieser Engine noch nie gemessen worden.

    None, wenn es im Fenster keinen solchen Tag gab — das ist eine Aussage
    über den Titel, aber keine über die Bestätigung, und beide zu vermischen
    wäre der Fehler aus §2h in neuer Form.
    """
    if len(fenster) < MIN_TAGE + 1:
        return None
    basis = _median([z[5] for z in fenster])
    if not basis:
        return None

    verhaeltnisse = []
    for vorher, heute in zip(fenster, fenster[1:]):
        schluss_vorher, schluss_heute = vorher[4], heute[4]
        volumen = heute[5]
        if not schluss_vorher or schluss_heute is None or volumen is None:
            continue
        bewegung = abs((schluss_heute - schluss_vorher) / schluss_vorher) * 100
        if bewegung >= AUSBRUCH_PCT:
            verhaeltnisse.append(volumen / basis)
    if not verhaeltnisse:
        return None
    return median(verhaeltnisse)


def tagesspanne(fenster: Sequence[tuple]) -> Optional[float]:
    """Median von (Hoch − Tief) / Schluss, in Prozent.

    Wie weit der Kurs innerhalb eines Handelstages läuft. Kein Volumen, aber
    derselbe Fussabdruck aus anderer Richtung: ein Titel, der täglich sechs
    Prozent durchmisst, wird anders gehandelt als einer mit einem halben.
    """
    werte = []
    for z in fenster:
        hoch, tief, schluss = z[2], z[3], z[4]
        if hoch is None or tief is None or not schluss:
            continue
        werte.append((hoch - tief) / schluss * 100)
    return _median(werte)


def eroeffnungsluecke(fenster: Sequence[tuple]) -> Optional[float]:
    """Median von |Eröffnung − Vortagesschluss| / Vortagesschluss, in Prozent.

    Was passiert, während die Börse zu ist. Der Anteil der Bewegung, der NICHT
    im Handel entsteht — bei einem Titel, der überwiegend über Nacht springt,
    ist jede Betrachtung des Intraday-Verlaufs eine Aussage über die kleinere
    Hälfte.
    """
    werte = []
    for vorher, heute in zip(fenster, fenster[1:]):
        schluss_vorher, eroeffnung = vorher[4], heute[1]
        if not schluss_vorher or eroeffnung is None:
            continue
        werte.append(abs((eroeffnung - schluss_vorher) / schluss_vorher) * 100)
    return _median(werte)


# Die Kennzahlen dieses Moduls, mit dem Fenster, das jede braucht. Der
# Auswerter iteriert darüber; eine neue Kennzahl hier einzutragen genügt.
KENNZAHLEN: dict[str, str] = {
    "Relatives Volumen": "kurz",
    "Volumen-Trend (20/60)": "beide",
    "Ausbruchs-Bestätigung": "kurz",
    "Tagesspanne": "kurz",
    "Eröffnungslücke": "kurz",
}


def kennzahlen_am(reihe: Sequence[tuple], zeitpunkt: datetime,
                  daten: Optional[Sequence[datetime]] = None
                  ) -> dict[str, Optional[float]]:
    """Alle Kennzahlen eines Titels zu einem Stichtag.

    Args:
        reihe: aufsteigende (datum, open, hoch, tief, schluss, volumen)-Tupel.
        daten: die Datumsspalte derselben Reihe, einmal je Titel gebaut.

    Returns:
        Name → Wert, mit None für „nicht berechenbar". Die Trennung zwischen
        None und 0 ist hier dieselbe wie in BC-04 und genauso wichtig: ein
        Handelsplatz ohne Volumenmeldung ist kein Tag ohne Umsatz.
    """
    kurz = _fenster(reihe, zeitpunkt, FENSTER_KURZ + 1, daten)
    lang = _fenster(reihe, zeitpunkt, FENSTER_LANG, daten)
    return {
        "Relatives Volumen": relatives_volumen(kurz),
        "Volumen-Trend (20/60)": volumen_trend(kurz, lang),
        "Ausbruchs-Bestätigung": ausbruchs_bestaetigung(kurz),
        "Tagesspanne": tagesspanne(kurz),
        "Eröffnungslücke": eroeffnungsluecke(kurz),
    }
