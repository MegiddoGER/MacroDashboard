"""
services/kursverhalten.py — Lage und Setup zum Reiter „Kursverhalten".

Setzt zusammen, was `services/kerzenmuster.py` erkannt hat, und stellt es in
seinen Zusammenhang: Groesse und Liquiditaet des Titels, Lage im Jahresband,
und — der eigentliche Ertrag — die **Ungueltigkeitsmarke** des juengsten
Musters mit ihrem Abstand in Prozent und in ATR.

**Keine Prognose.** Es wird kein Kursziel gerechnet und keine
Wahrscheinlichkeit ausgewiesen. Was hier „Ziel" heisst, ist das naechste
Swing-Hoch bzw. -Tief — ein Ort, an dem der Kurs zuletzt gedreht hat, nicht
eine Erwartung. Begruendung in `KERZENMUSTER.md` Paragraph 2 und 7.

**Zur Waehrung — hier steckt eine Falle.** `get_stock_details()` liefert
`hist_1y` in der ORIGINALWAEHRUNG (direkt aus `tk.history()`), waehrend
`stats` seine Kurse ueber `_to_eur()` umgerechnet hat. Wer den SMA 200 aus
`hist` gegen `stats["current_price"]` haelt, vergleicht bei jedem
nicht-europaeischen Titel zwei Waehrungen. Deshalb stammt hier **jede
Preisgroesse aus `hist`** und aus `stats` nur, was kein Preisvergleich ist:
Marktkapitalisierung (in EUR, steht fuer sich) und KGV (einheitenlos).
"""

import logging
from typing import Optional, Sequence

from services.kerzenmuster import Kerze, Treffer, kerzen_aus_dataframe, letzte_treffer

logger = logging.getLogger(__name__)


# Fenster fuer den Dollar-Umsatz. 60 Handelstage sind rund ein Quartal — kurz
# genug, um eine Liquiditaetsaenderung zu zeigen, lang genug gegen Einzeltage.
UMSATZ_FENSTER = 60

# Schwellen der Groessenklasse, in EUR. Grob an der ueblichen Einteilung.
GROESSENKLASSEN = [
    (200_000_000_000, "Schwergewicht"),
    (10_000_000_000, "Standardwert"),
    (2_000_000_000, "Mittelwert"),
    (0, "Nebenwert"),
]

# Schwellen der Liquiditaet, in EUR Tagesumsatz.
LIQUIDITAET = [
    (50_000_000, "liquide"),
    (5_000_000, "normal"),
    (0, "eng — Slippage beachten"),
]

# Rueckschau je Seite fuer einen Swing-Punkt.
SWING_FENSTER = 5


def _klasse(wert: Optional[float], stufen) -> Optional[str]:
    if wert is None:
        return None
    for schwelle, name in stufen:
        if wert >= schwelle:
            return name
    return None


# ---------------------------------------------------------------------------
# Swing-Punkte
# ---------------------------------------------------------------------------
#
# Bewusst nicht `smc.indicators.find_swing_points`: das liefert Hochs UND Tiefs
# in einer Liste, je nachdem ob die mittlere Kerze Maximum oder Minimum ihres
# Fensters ist. Hier wird getrennt gebraucht — ein Swing-HOCH ueber dem Kurs
# als Referenz fuer eine Long-Ablesung, ein Swing-TIEF darunter fuer eine
# Short-Ablesung.

def _swing_hochs(kerzen: Sequence[Kerze], fenster: int = SWING_FENSTER
                 ) -> list[float]:
    """Lokale Hochs: eine Kerze, deren Hoch das ihres Umfelds uebertrifft."""
    hochs = []
    for i in range(fenster, len(kerzen) - fenster):
        umfeld = kerzen[i - fenster:i + fenster + 1]
        if kerzen[i].hoch >= max(k.hoch for k in umfeld):
            hochs.append(kerzen[i].hoch)
    return hochs


def _swing_tiefs(kerzen: Sequence[Kerze], fenster: int = SWING_FENSTER
                 ) -> list[float]:
    tiefs = []
    for i in range(fenster, len(kerzen) - fenster):
        umfeld = kerzen[i - fenster:i + fenster + 1]
        if kerzen[i].tief <= min(k.tief for k in umfeld):
            tiefs.append(kerzen[i].tief)
    return tiefs


def naechstes_ziel(kerzen: Sequence[Kerze], richtung: str,
                   kurs: float) -> Optional[float]:
    """Das naechste Swing-Hoch ueber (long) bzw. Swing-Tief unter dem Kurs.

    Kein Kursziel — ein Ort, an dem der Kurs zuletzt gedreht hat.
    """
    if not kerzen or not kurs:
        return None
    if richtung == "long":
        darueber = [h for h in _swing_hochs(kerzen) if h > kurs]
        return min(darueber) if darueber else None
    if richtung == "short":
        darunter = [t for t in _swing_tiefs(kerzen) if t < kurs]
        return max(darunter) if darunter else None
    return None


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------

def _atr(kerzen: Sequence[Kerze], periode: int = 14) -> Optional[float]:
    """Average True Range, Wilder-Glaettung — wie `technical.calc_atr`.

    Hier auf den Kerzen statt auf pandas-Reihen, damit das Modul ohne
    DataFrame auskommt und testbar bleibt.
    """
    if len(kerzen) < periode + 1:
        return None
    wert: Optional[float] = None
    for i in range(1, len(kerzen)):
        k, vor = kerzen[i], kerzen[i - 1]
        tr = max(k.hoch - k.tief, abs(k.hoch - vor.schluss),
                 abs(k.tief - vor.schluss))
        wert = tr if wert is None else wert + (tr - wert) / periode
    return wert if wert and wert > 0 else None


def dollar_umsatz(kerzen: Sequence[Kerze],
                  fenster: int = UMSATZ_FENSTER) -> Optional[float]:
    """Mittlerer Tagesumsatz in Waehrungseinheiten (Kurs x Stueck).

    Splitsicher: ein Split multipliziert das Volumen und dividiert den Kurs um
    denselben Faktor, das Produkt bleibt gleich.
    """
    umsaetze: list[float] = []
    for k in kerzen[-fenster:]:
        if k.volumen is not None and k.volumen > 0:
            umsaetze.append(k.schluss * k.volumen)
    if not umsaetze:
        return None
    return sum(umsaetze) / len(umsaetze)


def lage_kontext(kerzen: Sequence[Kerze], stats: dict) -> dict:
    """Block 3 — Groesse, Liquiditaet, Lage im Jahresband, Bewertung."""
    kurs = kerzen[-1].schluss if kerzen else None
    umsatz = dollar_umsatz(kerzen)
    market_cap = stats.get("market_cap") if stats else None

    # Jahresband und SMA 200 aus DERSELBEN Reihe wie der Kurs (siehe Docstring).
    jahr = kerzen[-252:] if len(kerzen) >= 2 else kerzen
    hoch_52w = max((k.hoch for k in jahr), default=None)
    tief_52w = min((k.tief for k in jahr), default=None)

    position_52w = None
    if kurs and hoch_52w is not None and tief_52w is not None and hoch_52w > tief_52w:
        position_52w = round((kurs - tief_52w) / (hoch_52w - tief_52w) * 100.0, 1)

    abstand_sma200 = None
    if len(kerzen) >= 200 and kurs:
        sma200 = sum(k.schluss for k in kerzen[-200:]) / 200.0
        if sma200 > 0:
            abstand_sma200 = round((kurs - sma200) / sma200 * 100.0, 1)

    return {
        "kurs": kurs,
        "waehrung": (stats or {}).get("currency"),
        "market_cap": market_cap,
        "groessenklasse": _klasse(market_cap, GROESSENKLASSEN),
        "dollar_umsatz": umsatz,
        "liquiditaet": _klasse(umsatz, LIQUIDITAET),
        "position_52w": position_52w,
        "hoch_52w": hoch_52w,
        "tief_52w": tief_52w,
        "abstand_sma200": abstand_sma200,
        "kgv": (stats or {}).get("pe_ratio"),
    }


def setup_aus_treffer(treffer: Optional[Treffer],
                      kerzen: Sequence[Kerze]) -> Optional[dict]:
    """Block 4 — Ungueltigkeitsmarke und naechster Swing zum juengsten Muster.

    `verhaeltnis` setzt den Abstand zum Swing ins Verhaeltnis zum Abstand zur
    Marke. Es ist ausdruecklich **kein** Chance-Risiko-Verhaeltnis im Sinne
    einer Erwartung — beide Zahlen sind Abstaende zu Orten im Chart, keine
    Wahrscheinlichkeiten.
    """
    if treffer is None or treffer.richtung == "keine" or not kerzen:
        return None

    kurs = treffer.kurs
    atr = _atr(kerzen)
    marke = treffer.ungueltig_bei
    ziel = naechstes_ziel(kerzen, treffer.richtung, kurs)

    def _abstand(wert):
        if wert is None or not kurs:
            return None, None
        prozent = round((wert - kurs) / kurs * 100.0, 2)
        in_atr = round(abs(wert - kurs) / atr, 1) if atr else None
        return prozent, in_atr

    marke_pct, marke_atr = _abstand(marke)
    ziel_pct, ziel_atr = _abstand(ziel)

    verhaeltnis = None
    if marke_pct and ziel_pct and marke_pct != 0:
        verhaeltnis = round(abs(ziel_pct) / abs(marke_pct), 1)

    return {
        "muster": treffer.muster,
        "datum": treffer.datum,
        "richtung": treffer.richtung,
        "kurs": kurs,
        "umsatz_verhaeltnis": treffer.umsatz_verhaeltnis,
        "ungueltig_bei": marke,
        "ungueltig_prozent": marke_pct,
        "ungueltig_atr": marke_atr,
        "ziel": ziel,
        "ziel_prozent": ziel_pct,
        "ziel_atr": ziel_atr,
        "verhaeltnis": verhaeltnis,
        "atr": atr,
    }


# ---------------------------------------------------------------------------
# Einstiegspunkt fuer den Router
# ---------------------------------------------------------------------------

def kursverhalten(hist, stats: Optional[dict] = None,
                  anzahl: int = 10) -> dict:
    """Alles, was der Reiter braucht — aus einer bereits geladenen Kursreihe.

    `hist` ist der DataFrame aus `cached_stock_details()`; ein eigener Abruf
    findet nicht statt. Die Erkennung kostet auf zehn Jahren Tagesdaten rund
    30 ms, deshalb gibt es dafuer auch keinen eigenen Cache.
    """
    kerzen = kerzen_aus_dataframe(hist)
    if not kerzen:
        return {"verfuegbar": False, "treffer": [], "lage": {}, "setup": None}

    treffer = letzte_treffer(kerzen, anzahl=anzahl)
    return {
        "verfuegbar": True,
        "treffer": treffer,
        "lage": lage_kontext(kerzen, stats or {}),
        "setup": setup_aus_treffer(treffer[0] if treffer else None, kerzen),
        "kerzen_gesamt": len(kerzen),
    }
