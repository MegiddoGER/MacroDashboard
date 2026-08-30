"""
tests/test_position_snapshot.py — Erfassung des Positionspfads (P3-03).

Geprüft wird das, was später eine Gewichtungsentscheidung tragen soll:
die Übersetzung einer Empfehlung in ein messbares Richtungssignal, und die
Gewichtstabelle, aus der der Overall-Score entsteht.
"""

import pytest

from services.position_types import (
    PositionSide, RecommendationType, ScoreBreakdown,
)
from services.scoring_engine_v2 import (
    POSITION_GEWICHTE, POSITION_SCORE_VERSION, calc_position_scores,
)
from services.target_stop_validator import validate_target_stop
from services.position_metrics_engine import calc_position_metrics
from snapshot_engine.models import AnalyseModus
from snapshot_engine.position_snapshot import (
    richtung_aus_empfehlung, teilscores_schreiben,
)


# ---------------------------------------------------------------------------
# Richtungssignal
# ---------------------------------------------------------------------------

# Erwartung je Empfehlung bei einer LONG-Position. Maßstab ist die
# Exposition, die die Empfehlung hinterlässt — nicht ihre Stimmung.
LONG_ERWARTUNG = {
    RecommendationType.NEW_ENTRY_ALLOWED: "KAUF",
    RecommendationType.HOLD: "KAUF",
    RecommendationType.NORMAL_HOLD: "KAUF",
    RecommendationType.HOLD_WITH_TRAILING_STOP: "KAUF",
    RecommendationType.HOLD_BUT_REDUCE_RISK: "KAUF",
    RecommendationType.PROFIT_PROTECTION_MODE: "KAUF",
    RecommendationType.STOP_THREATENED: "KAUF",
    RecommendationType.ADD_ALLOWED: "KAUF",
    RecommendationType.EXIT: "VERKAUF",
    RecommendationType.PARTIAL_TAKE_PROFIT: "VERKAUF",
    RecommendationType.NEW_ENTRY_NOT_ALLOWED: "NEUTRAL",
    RecommendationType.ADD_NOT_ALLOWED: "NEUTRAL",
    RecommendationType.TARGET_REACHED_REVIEW: "NEUTRAL",
    RecommendationType.THESIS_REVIEW: "NEUTRAL",
    RecommendationType.LOSS_POSITION_REVIEW: "NEUTRAL",
    RecommendationType.EXIT_REVIEW: "NEUTRAL",
    RecommendationType.NO_ACTION_DATA_INSUFFICIENT: "NEUTRAL",
}


def test_jeder_empfehlungstyp_ist_zugeordnet():
    """Kein Empfehlungstyp darf unbemerkt ohne Zuordnung bleiben.

    Ein neuer Typ fiele sonst still auf NEUTRAL und verschwände aus der
    Messung, ohne dass es jemandem auffiele.
    """
    fehlend = set(RecommendationType) - set(LONG_ERWARTUNG)
    assert not fehlend, f"Ohne Zuordnung: {sorted(t.value for t in fehlend)}"


@pytest.mark.parametrize("typ,erwartet", sorted(
    LONG_ERWARTUNG.items(), key=lambda kv: kv[0].value))
def test_richtung_long(typ, erwartet):
    assert richtung_aus_empfehlung(typ, PositionSide.LONG) == erwartet


@pytest.mark.parametrize("typ,erwartet", sorted(
    LONG_ERWARTUNG.items(), key=lambda kv: kv[0].value))
def test_richtung_short_spiegelt_long(typ, erwartet):
    """SHORT dreht jede gerichtete Aussage um, NEUTRAL bleibt NEUTRAL."""
    gespiegelt = {"KAUF": "VERKAUF", "VERKAUF": "KAUF", "NEUTRAL": "NEUTRAL"}
    assert richtung_aus_empfehlung(typ, PositionSide.SHORT) == gespiegelt[erwartet]


def test_richtung_ohne_empfehlung_ist_neutral():
    assert richtung_aus_empfehlung(None) == "NEUTRAL"


def test_richtung_bei_unbekanntem_typ_ist_neutral():
    """Ein unbekannter Wert darf keine Richtungsaussage erfinden."""
    assert richtung_aus_empfehlung("GIBT_ES_NICHT") == "NEUTRAL"


def test_richtung_akzeptiert_string_wert():
    """Aus JSON gelesene Empfehlungen kommen als String zurück."""
    assert richtung_aus_empfehlung("EXIT", PositionSide.LONG) == "VERKAUF"


# ---------------------------------------------------------------------------
# Gewichtstabelle
# ---------------------------------------------------------------------------

def test_gewichte_decken_alle_teilscores_ab():
    """Jeder Teilscore ist entweder gewichtet oder bewusst ausgenommen.

    Fängt den Fall ab, dass ein dreizehnter Teilscore hinzukommt und ohne
    Gewicht still aus dem Overall-Score fällt.
    """
    ausgenommen = {"data_quality", "overall",
                   "has_critical_warning", "has_data_warning"}
    teilscores = set(ScoreBreakdown().to_dict()) - ausgenommen
    assert teilscores == set(POSITION_GEWICHTE)


def test_gewichte_sind_positiv():
    assert all(g > 0 for g in POSITION_GEWICHTE.values())


def test_score_version_gesetzt():
    assert POSITION_SCORE_VERSION


def test_overall_entspricht_gespeicherten_gewichten():
    """Der Overall-Score muss sich aus Teilscores und Gewichten exakt
    nachrechnen lassen — sonst wäre eine spätere Neugewichtung aus den
    gespeicherten Werten nicht möglich (Konvention aus CONTEXT.md §7)."""
    val = validate_target_stop(
        side=PositionSide.LONG, current_price=110.0, entry_price=100.0,
        take_profit=130.0, active_stop=105.0,
    )
    metrics = calc_position_metrics(
        side=PositionSide.LONG, entry_price=100.0, current_price=110.0,
        quantity=10, active_stop=105.0, active_take_profit=130.0,
    )
    scores = calc_position_scores({"trend_macro_bullish": True}, {}, val, metrics)
    gespeichert = scores.to_dict()

    summe = 0.0
    gewicht = 0.0
    for name, g in POSITION_GEWICHTE.items():
        if gespeichert[name] is not None:
            summe += g * gespeichert[name]
            gewicht += g

    assert gewicht > 0
    assert scores.overall == pytest.approx(summe / gewicht)


# ---------------------------------------------------------------------------
# Teilscores als Indikator-Zeilen
# ---------------------------------------------------------------------------

class _SessionAttrappe:
    """Sammelt add()-Aufrufe, statt eine Datenbank zu benötigen."""

    def __init__(self):
        self.zeilen = []

    def add(self, obj):
        self.zeilen.append(obj)


def test_teilscores_ohne_wert_werden_nicht_geschrieben():
    """Ein nicht berechenbarer Teilscore ist eine Lücke, kein Wert 0.

    Er steht in cat_max_json; eine Indikator-Zeile mit 0 würde ihn dagegen
    als gemessenen Extremwert in jede Auswertung tragen.
    """
    db = _SessionAttrappe()
    geschrieben = teilscores_schreiben(
        db, None, {"trend_health": 70.0, "valuation": None, "overall": 65.0})

    assert geschrieben == 1
    assert [z.indikator_name for z in db.zeilen] == ["trend_health"]
    assert db.zeilen[0].beitrag_numeric == 70.0


def test_data_quality_wird_als_info_gefuehrt():
    """data_quality trägt kein Gewicht im Overall-Score und darf deshalb
    keine Gewichtungsentscheidung stützen — gleiche Regel wie MACD im
    Einstiegspfad."""
    from snapshot_engine.models import Granularitaet

    db = _SessionAttrappe()
    teilscores_schreiben(
        db, None, {"trend_health": 70.0, "data_quality": 85.0})

    nach_name = {z.indikator_name: z for z in db.zeilen}
    assert nach_name["trend_health"].granularitaet == Granularitaet.INDIKATOR
    assert nach_name["data_quality"].granularitaet == Granularitaet.INFO


def test_neutrale_mitte_ist_fuenfzig():
    """Teilscores laufen von 0 bis 100 — die Mitte ist 50, nicht 0."""
    db = _SessionAttrappe()
    teilscores_schreiben(
        db, None, {"trend_health": 70.0, "momentum": 50.0, "sentiment": 30.0})

    nach_name = {z.indikator_name: z.signal_text for z in db.zeilen}
    assert nach_name == {
        "trend_health": "bullisch",
        "momentum": "neutral",
        "sentiment": "bearisch",
    }


def test_modus_ist_eigener_namensraum():
    """Der Positionspfad schreibt in denselben Tabellen, aber unter eigenem
    Modus — sonst mischten sich zwei Bewertungssysteme in einer Trefferquote."""
    assert AnalyseModus.BESTEHENDE_POSITION != AnalyseModus.NEUE_POSITION
