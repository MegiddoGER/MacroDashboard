"""
tests/test_holdout.py — Train/Holdout-Trennung (P1-05).

Geprüft wird die Eigenschaft, an der die Trennung steht oder fällt: dass
zwischen Training und Holdout eine Sperrzone von mindestens einem vollen
Horizont liegt, und dass kein Aufruferfehler still zum Gesamtbestand führt.
"""

from datetime import datetime, timedelta

import pytest

from snapshot_engine.models import HORIZONTE_TAGE
from snapshot_engine.auswertung.holdout import (
    EMBARGO, EMBARGO_TAGE, HOLDOUT, HOLDOUT_ANTEIL, TEILE, TRAIN,
    split_filter, split_zuordnen,
)

GRENZE = datetime(2025, 7, 1)


# ---------------------------------------------------------------------------
# Zuordnung
# ---------------------------------------------------------------------------

def test_vor_der_grenze_ist_training():
    assert split_zuordnen(GRENZE - timedelta(days=1), GRENZE) == TRAIN


def test_grenze_selbst_ist_schon_sperrzone():
    """Die Grenze gehört nicht mehr zum Training — sonst reichte das Label
    des letzten Trainings-Snapshots exakt bis zum Holdout-Beginn."""
    assert split_zuordnen(GRENZE, GRENZE) == EMBARGO


def test_letzter_tag_der_sperrzone():
    ende = GRENZE + timedelta(days=EMBARGO_TAGE)
    assert split_zuordnen(ende - timedelta(seconds=1), GRENZE) == EMBARGO
    assert split_zuordnen(ende, GRENZE) == HOLDOUT


def test_ohne_grenze_keine_zuordnung():
    assert split_zuordnen(GRENZE, None) is None


# ---------------------------------------------------------------------------
# Die eigentliche Schutzeigenschaft
# ---------------------------------------------------------------------------

def test_sperrzone_deckt_den_laengsten_horizont():
    """Kernbedingung: das Ergebnis des SPÄTESTEN Trainings-Snapshots muss
    feststehen, bevor der Holdout beginnt.

    Sonst wäre sein Label teilweise aus Kursbewegungen innerhalb des
    Holdout-Zeitraums bestimmt — Leckage durch die Hintertür.
    """
    spaetester_train = GRENZE - timedelta(seconds=1)
    faellig = spaetester_train + timedelta(days=max(HORIZONTE_TAGE))
    holdout_start = GRENZE + timedelta(days=EMBARGO_TAGE)
    assert faellig < holdout_start


def test_embargo_ist_mindestens_der_laengste_horizont():
    assert EMBARGO_TAGE >= max(HORIZONTE_TAGE)


def test_die_drei_mengen_sind_lueckenlos_und_ueberschneidungsfrei():
    """Jeder Zeitpunkt landet in genau einer Menge."""
    proben = [
        GRENZE - timedelta(days=400),
        GRENZE - timedelta(seconds=1),
        GRENZE,
        GRENZE + timedelta(days=EMBARGO_TAGE // 2),
        GRENZE + timedelta(days=EMBARGO_TAGE),
        GRENZE + timedelta(days=400),
    ]
    for p in proben:
        teil = split_zuordnen(p, GRENZE)
        assert teil in TEILE, p


# ---------------------------------------------------------------------------
# split_filter — Fehler dürfen nicht still durchgehen
# ---------------------------------------------------------------------------

class _QueryAttrappe:
    """Merkt sich, ob und wie oft gefiltert wurde."""

    def __init__(self):
        self.filter_aufrufe = 0

    def filter(self, *args):
        self.filter_aufrufe += 1
        return self


def test_ohne_teil_bleibt_die_query_unveraendert():
    """teil=None ist der Gesamtbestand — ausdrücklich in-sample."""
    q = _QueryAttrappe()
    assert split_filter(q, None, GRENZE) is q
    assert q.filter_aufrufe == 0


@pytest.mark.parametrize("teil", TEILE)
def test_jeder_teil_filtert(teil):
    q = _QueryAttrappe()
    split_filter(q, teil, GRENZE)
    assert q.filter_aufrufe == 1


def test_unbekannter_teil_wirft():
    """Ein Tippfehler darf nicht stillschweigend den Gesamtbestand liefern —
    das wäre genau die Vermischung, die das Modul verhindern soll."""
    with pytest.raises(ValueError, match="Unbekannter Teil"):
        split_filter(_QueryAttrappe(), "holdut", GRENZE)


def test_teil_ohne_grenze_wirft():
    """Ohne festgelegte Grenze gibt es keinen Holdout — dann lieber ein
    Fehler als eine Zahl, die nach Out-of-Sample aussieht."""
    with pytest.raises(ValueError, match="verlangt eine festgelegte Grenze"):
        split_filter(_QueryAttrappe(), HOLDOUT, None)


# ---------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------

def test_holdout_anteil_ist_ein_echter_anteil():
    assert 0 < HOLDOUT_ANTEIL < 1


def test_grenze_festlegen_lehnt_unsinnige_anteile_ab():
    from snapshot_engine.auswertung.holdout import grenze_festlegen
    for anteil in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="zwischen 0 und 1"):
            grenze_festlegen(None, anteil=anteil)


# ---------------------------------------------------------------------------
# Rückwirkende Holdouts
# ---------------------------------------------------------------------------

def test_parameter_ohne_datum_gilt_als_rueckwirkend():
    """Unbekannte Herkunft muss als unsauber gelten. Die Unschuldsvermutung
    schützte hier in die falsche Richtung: sie erzeugte ein Gütesiegel für
    eine Zahl, deren Zustandekommen niemand kennt."""
    from snapshot_engine.auswertung.holdout import holdout_rueckwirkend
    assert holdout_rueckwirkend(None) is True


def test_gate_weist_die_aktuelle_schwelle_als_rueckwirkend_aus():
    """Die Oszillator-Schwelle stammt aus dem Gesamtbestand — der Holdout
    belegt für sie nichts, und das Ergebnis muss das sagen."""
    from snapshot_engine.auswertung import gate
    assert gate.SCHWELLE_BESTIMMT_AM is None
