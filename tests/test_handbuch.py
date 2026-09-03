"""
tests/test_handbuch.py — Die Lesart je Instrument (Schritt 6).

Geprüft werden die Stellen, an denen eine falsche Zahl als Fund durchginge.

Der Spread ist die verführerischste Kennzahl des Moduls: er lässt sich aus
zwei Ausreissern an den Enden bilden und sieht dann aus wie ein Verlauf.
`_monoton` ist das Gegenmittel und muss deshalb streng sein — bei fünf Zellen
ist eine einzelne signifikante ein Zufallskandidat, eine durchgehende Treppe
nicht.

Dazu die Korrekturbreite: sie muss über ALLE Zellen eines Durchlaufs spannen.
Wer zehn Instrumente durchsucht und danach das beste zitiert, hat zehnmal
getestet — genau die Inflation, an der in dieser Messreihe schon mehrere
scheinbare Funde gestorben sind.
"""

import pytest

from snapshot_engine.auswertung.basis import z_korrigiert
from snapshot_engine.auswertung.handbuch import (
    GEGENLAEUFIG, QUANTILE, _monoton, _spread, quintil,
)


def _zeilen(quoten) -> list[dict]:
    return [{"quintil": i + 1, "markt_trefferquote": q}
            for i, q in enumerate(quoten)]


# ---------------------------------------------------------------------------
# Quintile
# ---------------------------------------------------------------------------

def test_quintil_grenzen():
    assert quintil(0) == 1
    assert quintil(19.9) == 1
    assert quintil(20) == 2
    assert quintil(99.9) == 5
    assert quintil(None) is None


def test_rang_hundert_faellt_nicht_aus_der_skala():
    """Ohne die Deckelung ergäbe Rang 100 ein sechstes Quintil.

    Eine einzelne Zeile in einer Gruppe, die es nicht geben darf — und sie
    fiele erst auf, wenn eine Auswertung ein Q6 ausweist.
    """
    assert quintil(100) == QUANTILE


# ---------------------------------------------------------------------------
# Monotonie — der Schutz gegen den Spread aus zwei Ausreissern
# ---------------------------------------------------------------------------

def test_durchgehende_treppe_gilt_als_monoton():
    assert _monoton(_zeilen([48.7, 49.0, 49.2, 50.2, 51.1])) is True


def test_fallende_treppe_gilt_ebenfalls():
    """Ein umgekehrter Verlauf ist genauso eine Aussage — nur andersherum.

    Der MACD zeigt genau das: von Q1 nach Q5 fallend. Wer nur auf steigend
    prüft, verwirft eine gegenläufige Lesart als Rauschen.
    """
    assert _monoton(_zeilen([50.9, 50.0, 49.3, 49.2, 48.6])) is True


def test_zwei_ausreisser_an_den_enden_sind_nicht_monoton():
    """Der Fall, der ohne diese Prüfung als Fund durchginge.

    Spread 2,4 pp, aber die Mitte trägt nichts — das ist kein Verlauf,
    sondern zwei Zellen.
    """
    zeilen = _zeilen([48.7, 50.4, 49.1, 50.3, 51.1])
    assert _spread(zeilen, "quintil", 5, 1) == pytest.approx(2.4)
    assert _monoton(zeilen) is False


def test_fehlende_quote_macht_keine_aussage():
    """None ist nicht "nicht monoton" — es ist "nicht beurteilbar"."""
    assert _monoton(_zeilen([48.7, None, 49.2, 50.2, 51.1])) is None


# ---------------------------------------------------------------------------
# Spread
# ---------------------------------------------------------------------------

def test_spread_ist_oben_minus_unten():
    assert _spread(_zeilen([48.7, 49.0, 49.2, 50.2, 51.1]),
                   "quintil", 5, 1) == pytest.approx(2.4)


def test_spread_ohne_beide_enden_ist_none():
    """Ein halber Spread wäre schlimmer als keiner — er sähe aus wie eine Zahl."""
    assert _spread(_zeilen([48.7, 49.0, 49.2, 50.2, None]),
                   "quintil", 5, 1) is None
    assert _spread([], "quintil", 5, 1) is None


# ---------------------------------------------------------------------------
# Mehrfachtests
# ---------------------------------------------------------------------------

def test_korrektur_waechst_mit_der_zahl_der_instrumente():
    """Der Kern der Disziplin: mehr Instrumente heisst strengere Schwelle.

    Zehn Instrumente x drei Horizonte x sieben Zellen sind 210 Tests, nicht
    sieben. Eine Korrektur je Instrument wäre zehnmal zum Preis von einem.
    """
    ein_instrument = z_korrigiert(1 * 3 * (QUANTILE + 2))
    alle = z_korrigiert(10 * 3 * (QUANTILE + 2))
    assert alle > ein_instrument
    assert alle == pytest.approx(3.67, abs=0.02)


# ---------------------------------------------------------------------------
# Leserichtung
# ---------------------------------------------------------------------------

def test_mean_reversion_instrumente_sind_als_gegenlaeufig_markiert():
    """Ohne diesen Hinweis liest man Q5 als "stark".

    Bei RSI, Stochastic und Bollinger ist der hohe Rohwert das
    VERKAUFS-Signal — die Engine stimmt dort bearisch. Ein Q5 mit Vorsprung
    hiesse dort, dass die Engine falsch herum liest, nicht dass das Signal
    trägt.
    """
    assert GEGENLAEUFIG == {"RSI (14)", "Stochastic (14)", "Bollinger Bänder"}
