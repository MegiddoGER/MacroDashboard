"""
tests/test_adx_trendhealth.py — Der ADX bewertet Stärke, nicht Richtung (PC-04).

Der ADX misst, wie stark ein Trend ist, nicht wohin er zeigt. Die
Positions-Engine gab ihm trotzdem einen gerichteten Beitrag zum
TrendHealthScore: `adx > 25` brachte +10 Punkte — auch mitten im Absturz. Bei
einem Titel mit `trend_macro_bearish` (−20) und `cross_bearish` (−15) hob
dieser Bonus zwei Drittel der Cross-Strafe wieder auf.

Diese Tests halten fest, dass die Trendgesundheit nicht mehr davon abhängt,
wie heftig ein Abwärtstrend ist.
"""

import pytest

from services.position_types import PositionMetrics, ValidationResult
from services.scoring_engine_v2 import POSITION_SCORE_VERSION, calc_position_scores


def _trendgesundheit(**signale) -> float:
    scores = calc_position_scores(signale, {}, ValidationResult(), PositionMetrics())
    return scores.trend_health


# ---------------------------------------------------------------------------
# Der Kern: Stärke ändert die Gesundheit nicht
# ---------------------------------------------------------------------------

def test_ein_heftiger_abwaertstrend_ist_nicht_gesuender_als_ein_milder():
    """Der eigentliche Fehler. Vorher lag der starke Trend um 10 Punkte höher,
    weil sein ADX über 25 stand."""
    heftig = _trendgesundheit(trend_macro_bearish=True, cross_bearish=True, adx_val=40.0)
    mild = _trendgesundheit(trend_macro_bearish=True, cross_bearish=True, adx_val=15.0)
    assert heftig == mild


def test_der_adx_aendert_die_trendgesundheit_ueberhaupt_nicht_mehr():
    ohne = _trendgesundheit(trend_macro_bullish=True, cross_bullish=True)
    stark = _trendgesundheit(trend_macro_bullish=True, cross_bullish=True, adx_val=45.0)
    schwach = _trendgesundheit(trend_macro_bullish=True, cross_bullish=True, adx_val=10.0)
    assert ohne == stark == schwach


@pytest.mark.parametrize("adx", [0.0, 10.0, 19.9, 20.0, 25.0, 25.1, 60.0, None])
def test_kein_adx_wert_bewegt_den_score(adx):
    """Auch nicht an den früheren Schwellen 20 und 25 — dort sprang er vorher."""
    basis = _trendgesundheit(trend_macro_bullish=True)
    assert _trendgesundheit(trend_macro_bullish=True, adx_val=adx) == basis


# ---------------------------------------------------------------------------
# Die Richtung entscheidet weiterhin
# ---------------------------------------------------------------------------

def test_aufwaertstrend_bleibt_gesuender_als_abwaertstrend():
    """Die Korrektur darf die Trendaussage nicht mit abgeschafft haben."""
    auf = _trendgesundheit(trend_macro_bullish=True, cross_bullish=True)
    ab = _trendgesundheit(trend_macro_bearish=True, cross_bearish=True)
    assert auf > ab


def test_fehlende_trendsignale_bleiben_neutral():
    """Beide Flags False heißt „SMA 200 nicht berechenbar", nicht
    „Abwärtstrend" — die Unterscheidung aus PC-01 gilt weiter."""
    neutral = _trendgesundheit()
    ab = _trendgesundheit(trend_macro_bearish=True)
    assert neutral > ab


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def test_positions_score_version_ist_erhoeht():
    """Aus denselben Eingaben entsteht ein anderer Teilscore — laut Konvention
    verlangt das eine neue Version, damit Snapshots zweier Bewertungsstände
    nicht gemeinsam gemittelt werden."""
    assert POSITION_SCORE_VERSION == "1.2.0"
