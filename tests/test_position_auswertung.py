"""
tests/test_position_auswertung.py — Auswertung des Positionspfads (P3-05).

Der Positionspfad ist ein anderes Bewertungssystem als der Einstiegspfad, und
die Unterschiede sind still: gleiche Tabelle, gleiche Spaltennamen, andere
Bedeutung. Geprüft wird deshalb genau das, was beim Vermischen kaputtginge —
nicht die Zahlen (es gibt noch keine), sondern die Regeln.
"""

import pytest

from snapshot_engine.auswertung.position import (
    SCORE_BAENDER, TEILSCORE_MITTE, richtung_aus_teilscore,
)


# ---------------------------------------------------------------------------
# Die Mitte eines Teilscores ist 50, nicht 0
# ---------------------------------------------------------------------------

def test_die_neutrale_mitte_ist_fuenfzig():
    """Im Einstiegspfad pendelt ein Beitrag um 0, hier laufen die Teilscores
    von 0 bis 100. Wer die Mitte bei 0 annimmt, liest jeden Teilscore als
    bullisch."""
    assert TEILSCORE_MITTE == 50.0


@pytest.mark.parametrize("wert", [50.1, 65.0, 100.0])
def test_ueber_der_mitte_ist_bullisch(wert):
    assert richtung_aus_teilscore(wert) == "bullisch"


@pytest.mark.parametrize("wert", [49.9, 20.0, 0.0])
def test_unter_der_mitte_ist_bearisch(wert):
    """Ein Teilscore von 20 ist eine bearische Aussage — nicht eine schwach
    bullische, wie es bei einer Mitte von 0 aussähe."""
    assert richtung_aus_teilscore(wert) == "bearisch"


def test_genau_die_mitte_traegt_keine_richtung():
    assert richtung_aus_teilscore(50.0) is None


def test_ohne_wert_keine_richtung():
    assert richtung_aus_teilscore(None) is None


# ---------------------------------------------------------------------------
# Score-Bänder
# ---------------------------------------------------------------------------

def test_baender_decken_die_ganze_skala_ab():
    """Eine Lücke zwischen zwei Bändern würde Beobachtungen still verschlucken."""
    assert SCORE_BAENDER[0]["min"] == 0
    assert SCORE_BAENDER[-1]["max"] == 100
    for vorheriges, naechstes in zip(SCORE_BAENDER, SCORE_BAENDER[1:]):
        assert naechstes["min"] - vorheriges["max"] < 0.05


def test_baender_ueberlappen_nicht():
    for vorheriges, naechstes in zip(SCORE_BAENDER, SCORE_BAENDER[1:]):
        assert vorheriges["max"] < naechstes["min"]


def test_baender_folgen_nicht_den_confidence_grenzen_des_einstiegspfads():
    """Dort markiert 60 die Kaufschwelle. Hier gibt es keine — der Score
    bewertet eine Position, die bereits läuft. Gleiche Grenzen würden eine
    Vergleichbarkeit suggerieren, die nicht besteht."""
    from snapshot_engine.auswertung.kalibrierung import CONFIDENCE_BEREICHE
    grenzen_position = [b["min"] for b in SCORE_BAENDER]
    grenzen_einstieg = [b["min"] for b in CONFIDENCE_BEREICHE]
    assert grenzen_position != grenzen_einstieg
