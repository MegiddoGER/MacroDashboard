"""
services/kerzenmuster.py — Erkennung anerkannter Kerzenmuster auf OHLCV.

**Was dieses Modul ist und was es nicht ist.** Es erkennt Muster und benennt
sie. Es sagt **nicht** voraus, wohin der Kurs laeuft, und es speist den Score
nicht — siehe `KERZENMUSTER.md` Paragraph 0 fuer die Abgrenzung zur
Signal-Engine.

Der Grund dafuer steht in der Literatur und ist ungewoehnlich eindeutig:
Marshall/Young/Rose (2006) finden auf DJIA-Titeln keinen Wert,
Marshall/Young/Cahan (2008) finden auf den 100 groessten Titeln der Boerse
Tokio ueber 1975-2004 nichts — nicht ueber 30 Jahre, nicht in Teilperioden,
nicht in Hausse oder Baisse. Kerzen sind japanisch; die Ausrede „im Westen
kennt sie niemand" gibt es nicht.

**Was trotzdem traegt, ist die Ungueltigkeitsmarke.** Bei einem bullischen
Engulfing ist das Tief der Signalkerze der Punkt, an dem die Ablesung falsch
war. Das ist eine Struktureigenschaft des Kursverlaufs und gilt unabhaengig
davon, ob das Muster irgendetwas prognostiziert. Deshalb traegt jedes Muster
hier seine Marke mit — sie ist der eigentliche Ertrag, nicht die Richtung.

Reine Funktionen: kein Datenbankzugriff, kein Netz. Damit ohne Datenbank
testbar.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Sequence

logger = logging.getLogger(__name__)


# Rueckschau fuer den Vortrend, in Handelstagen. Die Musterkerze selbst geht
# NICHT ein (die Reihe endet bei i-1), sonst waere die Bedingung zirkulaer:
# eine grosse gruene Kerze machte den Vortrend selbst aufwaerts.
VORTREND_TAGE = 10

# Fenster fuer den Umsatzvergleich. Der Median ist robuster als der Mittelwert,
# weil einzelne Ausbruchstage ihn sonst selbst anheben.
UMSATZ_FENSTER = 60

# Ab wann ein Docht oder Koerper als „vernachlaessigbar" gilt, als Anteil der
# Tagesspanne. Fuer Doji und Marubozu.
WINZIG = 0.05


@dataclass(frozen=True)
class Kerze:
    """Eine Tageszeile. Bewusst eigene Klasse statt eines DataFrame-Zugriffs:
    die Musterpruefungen lesen sich damit wie ihre Lehrbuchdefinition."""

    datum: datetime
    offen: float
    hoch: float
    tief: float
    schluss: float
    volumen: Optional[float] = None

    # -- Hilfsgroessen, wie in KERZENMUSTER.md Paragraph 6 definiert ---------

    @property
    def koerper(self) -> float:
        return abs(self.schluss - self.offen)

    @property
    def spanne(self) -> float:
        return self.hoch - self.tief

    @property
    def oberer_docht(self) -> float:
        return self.hoch - max(self.offen, self.schluss)

    @property
    def unterer_docht(self) -> float:
        return min(self.offen, self.schluss) - self.tief

    @property
    def koerper_oben(self) -> float:
        return max(self.offen, self.schluss)

    @property
    def koerper_unten(self) -> float:
        return min(self.offen, self.schluss)

    @property
    def koerper_mitte(self) -> float:
        return (self.offen + self.schluss) / 2.0

    @property
    def bullisch(self) -> bool:
        return self.schluss > self.offen

    @property
    def baerisch(self) -> bool:
        return self.schluss < self.offen


@dataclass(frozen=True)
class Muster:
    """Eine Musterdefinition.

    `richtung` steht hier und nicht in der Auswertung — sonst laesst sie sich
    spaeter umdeuten. `ungueltig` liefert die Marke, ab der die Ablesung
    widerlegt ist; sie ist je Muster verschieden (Engulfing: Tief der
    Signalkerze, Harami: Tief der Vorkerze, Morning Star: Tief der mittleren).
    """

    name: str
    richtung: str                     # "long" | "short" | "keine"
    braucht: int                      # benoetigte Vorgaengerkerzen
    vortrend_noetig: int              # -1 abwaerts, +1 aufwaerts, 0 egal
    pruefen: Callable[[Sequence[Kerze], int], bool]
    ungueltig: Callable[[Sequence[Kerze], int], Optional[float]]


@dataclass(frozen=True)
class Treffer:
    """Ein erkanntes Muster an einer bestimmten Zeile."""

    datum: datetime
    muster: str
    richtung: str
    vortrend: int
    kurs: float
    ungueltig_bei: Optional[float]
    umsatz_verhaeltnis: Optional[float]

    @property
    def abstand_prozent(self) -> Optional[float]:
        """Wie weit die Ungueltigkeitsmarke vom Schlusskurs entfernt liegt."""
        if self.ungueltig_bei is None or not self.kurs:
            return None
        return round((self.ungueltig_bei - self.kurs) / self.kurs * 100.0, 2)


# ---------------------------------------------------------------------------
# Eingang
# ---------------------------------------------------------------------------

def kerzen_aus_dataframe(df) -> list[Kerze]:
    """Baut die Kerzenliste aus einem yfinance-DataFrame (Open/High/Low/Close).

    Zeilen mit fehlenden oder unbrauchbaren Werten fallen heraus statt zu
    `NaN` zu werden: eine Kerze ohne Hoch ist keine Kerze mit Hoch 0.
    """
    if df is None or len(df) == 0:
        return []

    spalten = {s.lower(): s for s in df.columns}
    try:
        c_o, c_h = spalten["open"], spalten["high"]
        c_l, c_c = spalten["low"], spalten["close"]
    except KeyError:
        logger.warning("Kursreihe ohne OHLC-Spalten: %s", list(df.columns))
        return []
    c_v = spalten.get("volume")

    kerzen: list[Kerze] = []
    for datum, zeile in df.iterrows():
        try:
            offen = float(zeile[c_o])
            hoch = float(zeile[c_h])
            tief = float(zeile[c_l])
            schluss = float(zeile[c_c])
        except (TypeError, ValueError):
            continue
        # NaN faellt hier durch: NaN != NaN.
        if not (offen == offen and hoch == hoch and tief == tief
                and schluss == schluss):
            continue
        if hoch < tief or hoch <= 0:
            continue

        volumen = None
        if c_v is not None:
            try:
                v = float(zeile[c_v])
                volumen = v if v == v and v >= 0 else None
            except (TypeError, ValueError):
                volumen = None

        kerzen.append(Kerze(datum=datum, offen=offen, hoch=hoch, tief=tief,
                            schluss=schluss, volumen=volumen))
    return kerzen


# ---------------------------------------------------------------------------
# Lagegroessen
# ---------------------------------------------------------------------------

def vortrend(kerzen: Sequence[Kerze], i: int,
             tage: int = VORTREND_TAGE) -> int:
    """Richtung der Bewegung VOR der Kerze i. -1 abwaerts, +1 aufwaerts, 0 unklar.

    Die Rueckschau endet bei `i-1`. Reicht die Historie nicht, ist die Antwort
    0 und nicht etwa „aufwaerts" — Muster mit Trendbedingung fallen dann heraus.
    """
    if i - 1 - tage < 0 or i <= 0:
        return 0
    vorher = kerzen[i - 1 - tage].schluss
    zuletzt = kerzen[i - 1].schluss
    if vorher <= 0:
        return 0
    r = zuletzt / vorher - 1.0
    if r > 0:
        return 1
    if r < 0:
        return -1
    return 0


def umsatz_verhaeltnis(kerzen: Sequence[Kerze], i: int,
                       fenster: int = UMSATZ_FENSTER) -> Optional[float]:
    """Umsatz der Kerze i gegen den Median der vorangehenden `fenster` Tage.

    2,4 heisst „zweieinhalbfacher Umsatz gegenueber einem normalen Tag". Ein
    Muster auf duennem Umsatz ist eine andere Beobachtung als dasselbe Muster
    auf dem Zweieinhalbfachen — deshalb steht die Zahl in der Trefferliste.
    """
    if i <= 0:
        return None
    volumen = kerzen[i].volumen
    if volumen is None:
        return None

    vorher: list[float] = []
    for k in kerzen[max(0, i - fenster):i]:
        if k.volumen is not None and k.volumen > 0:
            vorher.append(k.volumen)
    if len(vorher) < 5:
        return None

    vorher.sort()
    mitte = len(vorher) // 2
    median = (vorher[mitte] if len(vorher) % 2
              else (vorher[mitte - 1] + vorher[mitte]) / 2.0)
    if median <= 0:
        return None
    return round(volumen / median, 2)


# ---------------------------------------------------------------------------
# Die Muster — Definitionen nach Nison und der kanonischen TA-Lib-Fassung.
# Reihenfolge und Bedingungen entsprechen KERZENMUSTER.md Paragraph 6.
# ---------------------------------------------------------------------------

def _hammer_geometrie(k: Kerze) -> bool:
    return (k.koerper > 0 and k.unterer_docht >= 2 * k.koerper
            and k.oberer_docht <= k.koerper)


def _inverser_hammer_geometrie(k: Kerze) -> bool:
    return (k.koerper > 0 and k.oberer_docht >= 2 * k.koerper
            and k.unterer_docht <= k.koerper)


def _marubozu(k: Kerze) -> bool:
    return (k.oberer_docht <= WINZIG * k.spanne
            and k.unterer_docht <= WINZIG * k.spanne)


def _drei_gleichgerichtete(kerzen: Sequence[Kerze], i: int,
                           bullisch: bool) -> bool:
    """Three White Soldiers / Three Black Crows.

    Drei gleichgerichtete Kerzen mit fortschreitendem Schlusskurs, deren
    Eroeffnung jeweils IM Koerper der vorigen liegt (kein Gap) und die
    ueberwiegend Koerper sind (mindestens die halbe Tagesspanne).
    """
    drei = kerzen[i - 2:i + 1]
    for k in drei:
        if k.spanne <= 0 or k.koerper < 0.5 * k.spanne:
            return False
        if bullisch and not k.bullisch:
            return False
        if not bullisch and not k.baerisch:
            return False
    for n in (1, 2):
        vor, jetzt = drei[n - 1], drei[n]
        if bullisch and jetzt.schluss <= vor.schluss:
            return False
        if not bullisch and jetzt.schluss >= vor.schluss:
            return False
        if not (vor.koerper_unten <= jetzt.offen <= vor.koerper_oben):
            return False
    return True


def _stern(kerzen: Sequence[Kerze], i: int, bullisch: bool) -> bool:
    """Morning Star / Evening Star — Umkehr ueber drei Kerzen.

    Grosser Koerper gegen die neue Richtung, dann ein kleiner Koerper
    (hoechstens 30 Prozent des ersten), dann eine Kerze in die neue Richtung,
    die ueber die Mitte des ersten Koerpers zurueckholt.
    """
    erste, mitte, letzte = kerzen[i - 2], kerzen[i - 1], kerzen[i]
    if erste.koerper <= 0:
        return False
    if mitte.koerper > 0.3 * erste.koerper:
        return False
    if bullisch:
        return (erste.baerisch and letzte.bullisch
                and letzte.schluss > erste.koerper_mitte)
    return (erste.bullisch and letzte.baerisch
            and letzte.schluss < erste.koerper_mitte)


MUSTER: dict[str, Muster] = {
    "hammer": Muster(
        name="Hammer", richtung="long", braucht=0, vortrend_noetig=-1,
        pruefen=lambda ks, i: _hammer_geometrie(ks[i]),
        ungueltig=lambda ks, i: ks[i].tief,
    ),
    "hanging_man": Muster(
        name="Hanging Man", richtung="short", braucht=0, vortrend_noetig=1,
        pruefen=lambda ks, i: _hammer_geometrie(ks[i]),
        ungueltig=lambda ks, i: ks[i].hoch,
    ),
    "inverted_hammer": Muster(
        name="Inverted Hammer", richtung="long", braucht=0, vortrend_noetig=-1,
        pruefen=lambda ks, i: _inverser_hammer_geometrie(ks[i]),
        ungueltig=lambda ks, i: ks[i].tief,
    ),
    "shooting_star": Muster(
        name="Shooting Star", richtung="short", braucht=0, vortrend_noetig=1,
        pruefen=lambda ks, i: _inverser_hammer_geometrie(ks[i]),
        ungueltig=lambda ks, i: ks[i].hoch,
    ),
    "marubozu_bullisch": Muster(
        name="Marubozu bullisch", richtung="long", braucht=0, vortrend_noetig=0,
        pruefen=lambda ks, i: ks[i].bullisch and _marubozu(ks[i]),
        ungueltig=lambda ks, i: ks[i].tief,
    ),
    "marubozu_baerisch": Muster(
        name="Marubozu baerisch", richtung="short", braucht=0, vortrend_noetig=0,
        pruefen=lambda ks, i: ks[i].baerisch and _marubozu(ks[i]),
        ungueltig=lambda ks, i: ks[i].hoch,
    ),
    "engulfing_bullisch": Muster(
        name="Bullisches Engulfing", richtung="long", braucht=1, vortrend_noetig=0,
        pruefen=lambda ks, i: (ks[i - 1].baerisch and ks[i].bullisch
                               and ks[i].offen <= ks[i - 1].schluss
                               and ks[i].schluss >= ks[i - 1].offen),
        ungueltig=lambda ks, i: ks[i].tief,
    ),
    "engulfing_baerisch": Muster(
        name="Baerisches Engulfing", richtung="short", braucht=1, vortrend_noetig=0,
        pruefen=lambda ks, i: (ks[i - 1].bullisch and ks[i].baerisch
                               and ks[i].offen >= ks[i - 1].schluss
                               and ks[i].schluss <= ks[i - 1].offen),
        ungueltig=lambda ks, i: ks[i].hoch,
    ),
    "piercing_line": Muster(
        name="Piercing Line", richtung="long", braucht=1, vortrend_noetig=0,
        pruefen=lambda ks, i: (ks[i - 1].baerisch and ks[i].bullisch
                               and ks[i].offen < ks[i - 1].tief
                               and ks[i].schluss > ks[i - 1].koerper_mitte
                               and ks[i].schluss < ks[i - 1].offen),
        ungueltig=lambda ks, i: ks[i].tief,
    ),
    "dark_cloud_cover": Muster(
        name="Dark Cloud Cover", richtung="short", braucht=1, vortrend_noetig=0,
        pruefen=lambda ks, i: (ks[i - 1].bullisch and ks[i].baerisch
                               and ks[i].offen > ks[i - 1].hoch
                               and ks[i].schluss < ks[i - 1].koerper_mitte
                               and ks[i].schluss > ks[i - 1].offen),
        ungueltig=lambda ks, i: ks[i].hoch,
    ),
    "harami_bullisch": Muster(
        name="Bullisches Harami", richtung="long", braucht=1, vortrend_noetig=0,
        pruefen=lambda ks, i: (ks[i - 1].baerisch and ks[i - 1].koerper > 0
                               and ks[i].bullisch
                               and ks[i].koerper_oben <= ks[i - 1].offen
                               and ks[i].koerper_unten >= ks[i - 1].schluss),
        ungueltig=lambda ks, i: ks[i - 1].tief,
    ),
    "harami_baerisch": Muster(
        name="Baerisches Harami", richtung="short", braucht=1, vortrend_noetig=0,
        pruefen=lambda ks, i: (ks[i - 1].bullisch and ks[i - 1].koerper > 0
                               and ks[i].baerisch
                               and ks[i].koerper_oben <= ks[i - 1].schluss
                               and ks[i].koerper_unten >= ks[i - 1].offen),
        ungueltig=lambda ks, i: ks[i - 1].hoch,
    ),
    "morning_star": Muster(
        name="Morning Star", richtung="long", braucht=2, vortrend_noetig=0,
        pruefen=lambda ks, i: _stern(ks, i, bullisch=True),
        ungueltig=lambda ks, i: ks[i - 1].tief,
    ),
    "evening_star": Muster(
        name="Evening Star", richtung="short", braucht=2, vortrend_noetig=0,
        pruefen=lambda ks, i: _stern(ks, i, bullisch=False),
        ungueltig=lambda ks, i: ks[i - 1].hoch,
    ),
    "three_white_soldiers": Muster(
        name="Three White Soldiers", richtung="long", braucht=2, vortrend_noetig=0,
        pruefen=lambda ks, i: _drei_gleichgerichtete(ks, i, bullisch=True),
        ungueltig=lambda ks, i: ks[i - 2].tief,
    ),
    "three_black_crows": Muster(
        name="Three Black Crows", richtung="short", braucht=2, vortrend_noetig=0,
        pruefen=lambda ks, i: _drei_gleichgerichtete(ks, i, bullisch=False),
        ungueltig=lambda ks, i: ks[i - 2].hoch,
    ),
    # Doji traegt KEINE Richtung. Es heisst „Unentschlossenheit" und wird als
    # solche angezeigt — nicht als Treffer mit Ungueltigkeitsmarke.
    "doji": Muster(
        name="Doji", richtung="keine", braucht=0, vortrend_noetig=0,
        pruefen=lambda ks, i: ks[i].koerper <= WINZIG * ks[i].spanne,
        ungueltig=lambda ks, i: None,
    ),
}


# ---------------------------------------------------------------------------
# Erkennung
# ---------------------------------------------------------------------------

def erkennen(kerzen: Sequence[Kerze], i: int) -> list[Treffer]:
    """Alle Muster, die an Zeile `i` ausloesen.

    Ein Tag kann mehrere tragen — ein Engulfing ist oft zugleich ein Marubozu.
    Das wird nicht unterdrueckt: die Anzeige soll zeigen, was dasteht.
    """
    if i < 0 or i >= len(kerzen):
        return []
    k = kerzen[i]
    if k.spanne <= 0:
        # Handelsstopp oder eine Zeile ohne Bewegung — kein Muster.
        return []

    trend = vortrend(kerzen, i)
    umsatz = umsatz_verhaeltnis(kerzen, i)
    treffer: list[Treffer] = []

    for muster in MUSTER.values():
        if i < muster.braucht:
            continue
        if muster.vortrend_noetig and trend != muster.vortrend_noetig:
            continue
        try:
            if not muster.pruefen(kerzen, i):
                continue
            marke = muster.ungueltig(kerzen, i)
        except (IndexError, ZeroDivisionError, TypeError):
            logger.debug("Muster %s an Zeile %d nicht pruefbar", muster.name, i)
            continue

        treffer.append(Treffer(
            datum=k.datum, muster=muster.name, richtung=muster.richtung,
            vortrend=trend, kurs=k.schluss, ungueltig_bei=marke,
            umsatz_verhaeltnis=umsatz,
        ))
    return treffer


def alle_treffer(kerzen: Sequence[Kerze]) -> list[Treffer]:
    """Jeder Treffer der ganzen Reihe, aelteste zuerst."""
    treffer: list[Treffer] = []
    for i in range(len(kerzen)):
        treffer.extend(erkennen(kerzen, i))
    return treffer


def letzte_treffer(kerzen: Sequence[Kerze], anzahl: int = 10,
                   mit_doji: bool = False) -> list[Treffer]:
    """Die juengsten Treffer, neueste zuerst.

    Doji bleibt standardmaessig draussen: es traegt keine Richtung und wuerde
    die Liste fuellen, ohne etwas zu sagen (rund 6 Prozent aller Zeilen).
    """
    treffer = alle_treffer(kerzen)
    if not mit_doji:
        treffer = [t for t in treffer if t.richtung != "keine"]
    treffer.sort(key=lambda t: t.datum, reverse=True)
    return treffer[:anzahl]
