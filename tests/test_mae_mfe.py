"""
tests/test_mae_mfe.py — Fenster seit Einstieg, MAE und MFE (P3-01).

Bis hierher lief `high_since_entry` auf den letzten 22 Bars, kommentiert als
„Best approximation with available data". Für eine drei Tage alte Position war
das ungefähr richtig; für eine, die ein halbes Jahr liegt, war es das Hoch des
letzten Monats — eine andere Größe als die, die der Name behauptet. Daran hängt
`profit_giveback_ratio`, und die kostet im Risiko-Teilscore bis zu 20 Punkte.

`low_since_entry` wurde nie übergeben, MAE und MFE gab es nicht.
"""

from datetime import datetime

import pandas as pd
import pytest

from services.position_metrics_engine import calc_position_metrics
from services.position_types import PositionSide
from services.scoring import _fenster_seit_einstieg


def _hist(kurse: list[tuple]) -> pd.DataFrame:
    """(High, Low)-Paare ab 2025-01-01, ein Bar je Tag."""
    index = pd.date_range("2025-01-01", periods=len(kurse), freq="D")
    return pd.DataFrame({"High": [h for h, _ in kurse],
                         "Low": [t for _, t in kurse]}, index=index)


# ---------------------------------------------------------------------------
# Das Fenster
# ---------------------------------------------------------------------------

def test_fenster_beginnt_am_einstieg_nicht_frueher():
    """Die eigentliche Korrektur: was VOR dem Einstieg passierte, gehört nicht
    dazu — sonst zählt ein Hoch, das man nie gehalten hat."""
    hist = _hist([(200.0, 190.0),   # 01.01. — vor dem Einstieg, muss draußen bleiben
                  (110.0, 100.0),   # 02.01.
                  (120.0, 105.0)])  # 03.01.
    hoch, tief = _fenster_seit_einstieg(hist, "2025-01-02")
    assert hoch == 120.0
    assert tief == 100.0


def test_fenster_reicht_bis_zum_letzten_bar():
    hist = _hist([(110.0, 100.0), (130.0, 95.0), (115.0, 105.0)])
    hoch, tief = _fenster_seit_einstieg(hist, "2025-01-01")
    assert hoch == 130.0
    assert tief == 95.0


def test_historie_die_den_einstieg_nicht_abdeckt_liefert_nichts():
    """Beginnt die Historie nach dem Einstieg, fehlt der Anfang des Fensters —
    das wahre Extrem könnte genau darin liegen. None ist die richtige Antwort,
    eine Näherung wäre eine falsche Zahl."""
    hist = _hist([(110.0, 100.0), (120.0, 105.0)])
    assert _fenster_seit_einstieg(hist, "2024-06-01") == (None, None)


def test_einstieg_nach_dem_letzten_bar_liefert_nichts():
    hist = _hist([(110.0, 100.0), (120.0, 105.0)])
    assert _fenster_seit_einstieg(hist, "2026-01-01") == (None, None)


@pytest.mark.parametrize("hist, datum", [
    (None, "2025-01-01"),
    (pd.DataFrame(), "2025-01-01"),
])
def test_ohne_brauchbare_historie_liefert_nichts(hist, datum):
    assert _fenster_seit_einstieg(hist, datum) == (None, None)


def test_ohne_kaufdatum_liefert_nichts():
    assert _fenster_seit_einstieg(_hist([(110.0, 100.0)]), "") == (None, None)
    assert _fenster_seit_einstieg(_hist([(110.0, 100.0)]), None) == (None, None)


# ---------------------------------------------------------------------------
# MAE und MFE
# ---------------------------------------------------------------------------

def _metriken(side, high, low):
    return calc_position_metrics(
        side=side, entry_price=100.0, current_price=105.0, quantity=10,
        high_since_entry=high, low_since_entry=low,
    )


def test_long_mfe_ist_die_beste_bewegung_dafuer():
    m = _metriken(PositionSide.LONG, high=130.0, low=80.0)
    assert m.mfe == pytest.approx(0.30)
    assert m.mae == pytest.approx(-0.20)


def test_short_ist_spiegelbildlich():
    """Bei einer Short-Position ist ein Tief der Gewinn und ein Hoch der
    Rückschlag — genau umgekehrt."""
    m = _metriken(PositionSide.SHORT, high=130.0, low=80.0)
    assert m.mfe == pytest.approx(0.20)
    assert m.mae == pytest.approx(-0.30)


def test_wer_nie_im_minus_lag_hat_kein_mae():
    """Ein Titel, der seit Einstieg nie unter den Einstiegskurs fiel, hatte
    keine Bewegung gegen sich — 0, nicht ein positiver Wert."""
    m = _metriken(PositionSide.LONG, high=130.0, low=102.0)
    assert m.mae == 0.0
    assert m.mfe == pytest.approx(0.30)


def test_wer_nie_im_plus_lag_hat_kein_mfe():
    m = _metriken(PositionSide.LONG, high=98.0, low=80.0)
    assert m.mfe == 0.0
    assert m.mae == pytest.approx(-0.20)


def test_ohne_fenster_bleiben_beide_leer():
    m = _metriken(PositionSide.LONG, high=None, low=None)
    assert m.mae is None
    assert m.mfe is None


def test_ein_halbes_fenster_liefert_nur_die_haelfte():
    """Fehlt eine der beiden Grenzen, entfällt genau die daran hängende
    Kennzahl — und nicht beide."""
    m = _metriken(PositionSide.LONG, high=130.0, low=None)
    assert m.mfe == pytest.approx(0.30)
    assert m.mae is None
