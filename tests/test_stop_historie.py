"""
tests/test_stop_historie.py — Stop-Historie (P3-01).

Ohne diese Historie ist der ursprünglich eingegangene Betrag nicht mehr
feststellbar, sobald der Stop einmal nachgezogen wurde — die Positionstabelle
kennt nur den aktuellen. Damit sind R-Multiple, MAE und MFE unberechenbar.

Geprüft wird hier die Regel, nicht die Speicherung: **welcher Eintrag darf als
Einstiegsrisiko gelten.** Das ist die Stelle, an der ein geschöntes R-Multiple
entstünde — ein bereits nachgezogener Stop als Einstiegsrisiko gelesen lässt
jede Position besser aussehen, als sie war.
"""

from services.watchlist import (
    QUELLE_AENDERUNG, QUELLE_ALTBESTAND, QUELLE_EROEFFNUNG,
    initialer_aus_historie, vorheriger_aus_historie,
)


def _eintrag(stop: float, quelle: str) -> dict:
    return {"stop": stop, "quelle": quelle}


# ---------------------------------------------------------------------------
# Einstiegs-Stop
# ---------------------------------------------------------------------------

def test_eroeffnungsstop_ist_das_einstiegsrisiko():
    historie = [_eintrag(90.0, QUELLE_EROEFFNUNG), _eintrag(95.0, QUELLE_AENDERUNG)]
    assert initialer_aus_historie(historie) == 90.0


def test_nachziehen_aendert_das_einstiegsrisiko_nicht():
    """Der Sinn der Historie: der ursprüngliche Wert bleibt erhalten, egal wie
    oft der Stop danach bewegt wurde."""
    historie = [
        _eintrag(90.0, QUELLE_EROEFFNUNG),
        _eintrag(95.0, QUELLE_AENDERUNG),
        _eintrag(102.0, QUELLE_AENDERUNG),
    ]
    assert initialer_aus_historie(historie) == 90.0


def test_altbestand_gilt_nicht_als_einstiegsrisiko():
    """Der wichtigste Fall. Ein ALTBESTAND-Eintrag ist der zuletzt bekannte
    Stop, nicht der ursprüngliche — er könnte längst nachgezogen sein. Ihn zu
    verwenden würde das R-Multiple systematisch zu gut ausweisen."""
    historie = [_eintrag(95.0, QUELLE_ALTBESTAND), _eintrag(102.0, QUELLE_AENDERUNG)]
    assert initialer_aus_historie(historie) is None


def test_ohne_historie_kein_einstiegsrisiko():
    assert initialer_aus_historie([]) is None


def test_nur_der_erste_eintrag_entscheidet():
    """Ein später eingetragener EROEFFNUNG-Eintrag wäre ein Datenfehler und
    darf nicht rückwirkend zur Bezugsgröße werden."""
    historie = [_eintrag(95.0, QUELLE_ALTBESTAND), _eintrag(90.0, QUELLE_EROEFFNUNG)]
    assert initialer_aus_historie(historie) is None


# ---------------------------------------------------------------------------
# Vorheriger Stop (Ratchet)
# ---------------------------------------------------------------------------

def test_vorheriger_stop_ist_der_vorletzte_eintrag():
    historie = [
        _eintrag(90.0, QUELLE_EROEFFNUNG),
        _eintrag(95.0, QUELLE_AENDERUNG),
        _eintrag(102.0, QUELLE_AENDERUNG),
    ]
    assert vorheriger_aus_historie(historie) == 95.0


def test_ein_einziger_eintrag_hat_keinen_vorgaenger():
    assert vorheriger_aus_historie([_eintrag(90.0, QUELLE_EROEFFNUNG)]) is None
    assert vorheriger_aus_historie([]) is None


def test_fuer_die_ratchet_pruefung_zaehlt_jede_herkunft():
    """Anders als beim Einstiegsrisiko genügt hier der zuletzt bekannte Wert —
    gefragt ist nur, ob der Stop gelockert statt nachgezogen wurde."""
    historie = [_eintrag(95.0, QUELLE_ALTBESTAND), _eintrag(88.0, QUELLE_AENDERUNG)]
    assert vorheriger_aus_historie(historie) == 95.0


# ---------------------------------------------------------------------------
# Durchleitung: der Einstiegs-Stop erreicht die Metriken
# ---------------------------------------------------------------------------

def _position(initial_stop=None):
    daten = {
        "buy_price": 100.0,
        "current_price": 110.0,
        "quantity": 10,
        "holding_days": 30,
        "stop_loss": 95.0,
    }
    if initial_stop is not None:
        daten["initial_stop"] = initial_stop
    return daten


def test_ohne_historie_bleibt_das_r_multiple_leer():
    """Der Zustand vor P3-01 — und weiterhin der korrekte, wenn die Position
    manuell eingegeben wurde und keine gespeicherte Historie hat."""
    from services.scoring import ScoreResult, calc_position_analysis_v2
    analyse = calc_position_analysis_v2(ScoreResult(), _position())
    assert analyse["position_analysis"].metrics.r_multiple is None


def test_mit_einstiegsstop_wird_das_r_multiple_berechnet():
    """Einstieg 100, Stop bei Eröffnung 90 — also 10 Risiko. Kurs 110 heißt
    10 Gewinn, das ist genau 1 R."""
    from services.scoring import ScoreResult, calc_position_analysis_v2
    analyse = calc_position_analysis_v2(ScoreResult(), _position(initial_stop=90.0))
    assert analyse["position_analysis"].metrics.r_multiple == 1.0


def test_ein_enger_einstiegsstop_ergibt_ein_hoeheres_r():
    """Dieselbe Kursbewegung, halbes Einstiegsrisiko — doppeltes R. Genau
    deshalb darf ein nachgezogener Stop nicht als Einstiegsrisiko gelten."""
    from services.scoring import ScoreResult, calc_position_analysis_v2
    analyse = calc_position_analysis_v2(ScoreResult(), _position(initial_stop=95.0))
    assert analyse["position_analysis"].metrics.r_multiple == 2.0
