"""
tests/test_position_side.py — Die Positionsseite ist erreichbar (P3-02).

`calc_position_analysis_v2` hatte `side = PositionSide.LONG` fest verdrahtet,
obwohl jede Engine darunter beide Seiten vollständig behandelt und
`tests/test_position_management.py` den SHORT-Zweig einzeln prüft. Der Pfad war
also nicht falsch, sondern unerreichbar — getesteter toter Code.

Geprüft wird hier deshalb nicht die Rechnung (die steht dort), sondern die
Durchleitung: kommt eine angegebene Seite unten an, und was passiert bei
unsinniger Eingabe.
"""

import pytest

from services.position_types import PositionSide
from services.scoring import (
    ScoreResult, _seite_aus_positionsdaten, calc_position_analysis_v2,
)


# ---------------------------------------------------------------------------
# Lesen der Seite aus den Eingabedaten
# ---------------------------------------------------------------------------

def test_ohne_angabe_bleibt_es_long():
    assert _seite_aus_positionsdaten({}) == PositionSide.LONG
    assert _seite_aus_positionsdaten({"side": None}) == PositionSide.LONG


def test_enum_wird_durchgereicht():
    assert _seite_aus_positionsdaten({"side": PositionSide.SHORT}) == PositionSide.SHORT
    assert _seite_aus_positionsdaten({"side": PositionSide.LONG}) == PositionSide.LONG


@pytest.mark.parametrize("roh", ["SHORT", "short", " Short ", "sHoRt"])
def test_text_in_jeder_schreibweise(roh):
    """Formulardaten kommen als Text herein, in unbekannter Schreibweise."""
    assert _seite_aus_positionsdaten({"side": roh}) == PositionSide.SHORT


@pytest.mark.parametrize("roh", ["LONG", "long", "", "quatsch", 0, 1, []])
def test_alles_unverstaendliche_wird_long(roh):
    """Aus einem Tippfehler darf keine umgekehrte Empfehlung werden."""
    assert _seite_aus_positionsdaten({"side": roh}) == PositionSide.LONG


# ---------------------------------------------------------------------------
# Durchleitung bis in die Analyse
# ---------------------------------------------------------------------------

def _positionsdaten(side=None) -> dict:
    daten = {
        "buy_price": 100.0,
        "current_price": 90.0,
        "quantity": 10,
        "holding_days": 30,
    }
    if side is not None:
        daten["side"] = side
    return daten


def test_short_kommt_in_der_analyse_an():
    """Der Kern von P3-02: vorher war das Ergebnis immer LONG."""
    analyse = calc_position_analysis_v2(ScoreResult(), _positionsdaten("SHORT"))
    assert analyse["position_analysis"].side == PositionSide.SHORT


def test_ohne_angabe_bleibt_die_analyse_long():
    """Die Oberfläche liefert keine Seite — ihr Verhalten darf sich nicht
    geändert haben."""
    analyse = calc_position_analysis_v2(ScoreResult(), _positionsdaten())
    assert analyse["position_analysis"].side == PositionSide.LONG


def test_dieselbe_lage_wird_je_seite_verschieden_bewertet():
    """Ein Kurs unter dem Einstieg ist für LONG ein Verlust und für SHORT ein
    Gewinn. Kämen beide Seiten zum selben Ergebnis, wäre die Durchleitung
    zwar da, aber wirkungslos.
    """
    lang = calc_position_analysis_v2(ScoreResult(), _positionsdaten("LONG"))
    kurz = calc_position_analysis_v2(ScoreResult(), _positionsdaten("SHORT"))

    metriken_lang = lang["position_analysis"].metrics
    metriken_kurz = kurz["position_analysis"].metrics
    assert metriken_lang is not None and metriken_kurz is not None

    # Bei 100 → 90 verliert die Long-Seite und gewinnt die Short-Seite.
    assert metriken_lang.unrealized_pnl_pct < 0
    assert metriken_kurz.unrealized_pnl_pct > 0
