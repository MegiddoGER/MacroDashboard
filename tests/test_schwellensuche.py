"""
tests/test_schwellensuche.py — Schwellensuche auf dem Trainingsteil (P1-07).

Geprüft werden die beiden Vorkehrungen gegen Überanpassung: die Korrektur für
Mehrfachtests und die Plateau-Wahl. Beide entscheiden darüber, ob eine Zahl
später auf neuen Daten Bestand hat — Fehler darin fallen sonst erst auf, wenn
der Holdout schon verbraucht ist.
"""

import inspect

import pytest

from snapshot_engine.auswertung.schwellensuche import (
    ALPHA, KANDIDATEN, _laengstes_plateau, _z_korrigiert, _zeilen_laden,
)


# ---------------------------------------------------------------------------
# Korrektur für Mehrfachtests
# ---------------------------------------------------------------------------

def test_ein_einzelner_test_entspricht_dem_ueblichen_z():
    assert _z_korrigiert(1) == pytest.approx(1.96, abs=0.01)


def test_mehr_tests_verlangen_mehr_vorsprung():
    """Die Schwelle für einen Fund muss mit der Zahl der Versuche steigen."""
    werte = [_z_korrigiert(k) for k in (1, 3, 13, 50)]
    assert werte == sorted(werte)
    assert len(set(werte)) == 4


def test_null_tests_faellt_nicht_um():
    assert _z_korrigiert(0) == pytest.approx(_z_korrigiert(1))


def test_alpha_ist_das_uebliche_niveau():
    assert ALPHA == 0.05


# ---------------------------------------------------------------------------
# Plateau statt Spitze
# ---------------------------------------------------------------------------

def _kandidaten(*muster: bool) -> list[dict]:
    """Baut Ergebniszeilen mit vorgegebenem Signifikanzmuster."""
    return [{"schwelle": 0.10 * (i + 1), "signifikant": s}
            for i, s in enumerate(muster)]


def test_ohne_signifikante_kandidaten_kein_plateau():
    assert _laengstes_plateau(_kandidaten(False, False, False)) == []


def test_eine_einzelne_spitze_ist_ein_plateau_der_laenge_eins():
    plateau = _laengstes_plateau(_kandidaten(False, True, False))
    assert len(plateau) == 1


def test_der_laengste_zusammenhaengende_bereich_gewinnt():
    """Eine isolierte Spitze darf einen breiteren Bereich nicht schlagen —
    genau darin liegt der Unterschied zwischen Rauschen und Effekt."""
    plateau = _laengstes_plateau(
        _kandidaten(True, False, True, True, True, False))
    assert len(plateau) == 3
    assert plateau == pytest.approx([0.30, 0.40, 0.50])


def test_bei_gleichstand_gewinnen_die_niedrigeren_schwellen():
    """Niedrigere Schwellen lassen mehr Signale durch und stützen sich auf
    mehr Beobachtungen — bei gleicher Belegbarkeit die robustere Wahl."""
    plateau = _laengstes_plateau(
        _kandidaten(True, True, False, True, True))
    assert plateau == pytest.approx([0.10, 0.20])


def test_luecke_unterbricht_das_plateau():
    plateau = _laengstes_plateau(_kandidaten(True, True, False, True))
    assert len(plateau) == 2


# ---------------------------------------------------------------------------
# Der Holdout muss unerreichbar bleiben
# ---------------------------------------------------------------------------

def test_die_suche_kennt_keinen_teil_parameter():
    """Ein `teil`-Parameter würde erlauben, die Suche über den Holdout laufen
    zu lassen. Wer 13 Schwellen durchprobiert und die beste behält, hat 13-mal
    aus dem Holdout gelernt — er wäre damit verbraucht, wie das Ergebnis
    anschließend auch heißt."""
    assert "teil" not in inspect.signature(_zeilen_laden).parameters


def test_kandidaten_sind_aufsteigend_und_eindeutig():
    assert list(KANDIDATEN) == sorted(set(KANDIDATEN))
