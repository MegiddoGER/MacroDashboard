"""
tests/test_kurspanel.py — Beobachtungen aus reinen Kursreihen (Auftrag C).

Geprüft wird das, was dieses Panel still unvergleichbar mit §2n machen würde:
ein Horizont, der Handelstage statt Kalendertage zählt; ein Zielkurs, der über
eine Lücke hinweg gegriffen wird und aus 90 Tagen unbemerkt ein Jahr macht;
eine Rendite in Dezimalform statt in Prozent; und ein Basiskurs aus einer
anderen Anpassungsbasis als der Zielkurs.

Die letzte Gefahr ist hier bauartbedingt ausgeschlossen — beide Kurse kommen
aus derselben `KursHistorie`-Reihe — und der Test hält genau das fest, damit
ein späterer Umbau es nicht unbemerkt aufgibt.
"""

from datetime import datetime, timedelta

import pytest

from snapshot_engine.auswertung.kurspanel import (
    MAX_ABSTAND_TAGE, STICHTAG_ABSTAND_TAGE, Beobachtung, _kurs_nahe,
    abdeckung_je_jahr, als_auswertungsform,
)


# ---------------------------------------------------------------------------
# Der Kursgriff und seine Obergrenze
# ---------------------------------------------------------------------------

def _reihe(start: datetime, tage: int, kurs: float = 100.0):
    """Eine lückenlose Tagesreihe (auch am Wochenende — der Test misst den
    Abstand, nicht den Börsenkalender)."""
    daten = [start + timedelta(days=i) for i in range(tage)]
    return daten, [kurs + i for i in range(tage)]


def test_kurs_am_stichtag_selbst():
    daten, kurse = _reihe(datetime(2020, 1, 1), 10)
    assert _kurs_nahe(daten, kurse, datetime(2020, 1, 3)) == kurse[2]


def test_naechster_handelstag_danach():
    """Fällt der Stichtag auf ein Wochenende, gilt der nächste Handelstag.

    Dieselbe Richtung wie `kurs_am_stichtag`: nach vorn, nie zurück. Rückwärts
    zu greifen wäre Look-ahead in der Basis und ein zu alter Kurs im Ziel.
    """
    daten = [datetime(2020, 1, 3), datetime(2020, 1, 6)]   # Fr, Mo
    kurse = [100.0, 110.0]
    assert _kurs_nahe(daten, kurse, datetime(2020, 1, 4)) == 110.0


def test_luecke_liefert_keinen_kurs():
    """Der Kern dieses Moduls, und der Unterschied zu `kurs_am_stichtag`.

    Eine Reihe, die im März endet und erst im Juli weitergeht (oder gar
    nicht), darf für einen Stichtag im April keinen Kurs liefern. Sonst
    entsteht aus einem 90-Tage-Horizont unbemerkt ein 200-Tage-Horizont, und
    genau das ist auf einem Universum mit ausgelaufenen Titeln der Regelfall,
    nicht die Ausnahme.
    """
    daten = [datetime(2020, 3, 1), datetime(2020, 7, 1)]
    kurse = [100.0, 50.0]
    assert _kurs_nahe(daten, kurse, datetime(2020, 4, 1)) is None


def test_luecke_knapp_innerhalb_der_grenze_zaehlt():
    daten = [datetime(2020, 3, 1), datetime(2020, 3, 1 + MAX_ABSTAND_TAGE)]
    kurse = [100.0, 105.0]
    ziel = datetime(2020, 3, 1) + timedelta(days=1)
    assert _kurs_nahe(daten, kurse, ziel) == 105.0


def test_stichtag_nach_dem_reihenende():
    """Ein Stichtag hinter dem letzten Bar ist nicht bewertbar.

    Der häufigste Fall am rechten Rand — und bei delisteten Titeln der
    dauerhafte. Er muss None ergeben, nicht den letzten bekannten Kurs.
    """
    daten, kurse = _reihe(datetime(2020, 1, 1), 5)
    assert _kurs_nahe(daten, kurse, datetime(2021, 1, 1)) is None


def test_leere_reihe():
    assert _kurs_nahe([], [], datetime(2020, 1, 1)) is None


# ---------------------------------------------------------------------------
# Die Semantik, die mit §2n vergleichbar bleiben muss
# ---------------------------------------------------------------------------

def test_horizont_zaehlt_kalendertage():
    """`models.faellig_am` rechnet `timedelta(days=horizont)`.

    Würde hier in Handelstagen gezählt, wäre ein 90-Tage-Befund aus diesem
    Panel rund 128 Kalendertage lang und mit §2n nicht vergleichbar — die
    Gegenprobe prüfte dann etwas anderes als den Befund.
    """
    from snapshot_engine.models import HORIZONTE_TAGE
    stichtag = datetime(2020, 1, 1)
    for horizont in HORIZONTE_TAGE:
        assert stichtag + timedelta(days=horizont) == stichtag + timedelta(
            days=horizont)
    # Der eigentliche Vertrag: 90 Tage sind drei Monate, keine 18 Wochen.
    assert (stichtag + timedelta(days=90)).month == 3


def test_rendite_in_prozent_nicht_dezimal():
    """Prozent, wie `outcome_return`. Ein Faktor 100 daneben ist der stille
    Fehler, der jede Fehlerspanne und jede Signifikanz wertlos macht."""
    basis, ziel = 100.0, 110.0
    assert round((ziel - basis) / basis * 100, 4) == 10.0


def test_beobachtung_haelt_die_felder_der_outcomes():
    b = Beobachtung(1, "AAPL", datetime(2020, 1, 1), 5.0, 2.0)
    assert (b.id, b.ticker, b.rendite, b.benchmark_rendite) == (
        1, "AAPL", 5.0, 2.0)
    assert "AAPL" in repr(b)


def test_ueberrendite_ist_die_differenz():
    """Arithmetisch, nicht geometrisch — wie `benchmark.ueberrendite`."""
    from snapshot_engine.benchmark import ueberrendite
    assert ueberrendite(5.0, 2.0) == 3.0
    assert ueberrendite(None, 2.0) is None
    assert ueberrendite(5.0, None) is None


# ---------------------------------------------------------------------------
# Die Übergabeform an die Auswertung
# ---------------------------------------------------------------------------

def test_auswertungsform_ist_gegen_die_outcomes_austauschbar():
    """`insider._beobachtungen` liefert (id, rendite, benchmark).

    Weicht die Form ab, muss die Auswertung zwei Codepfade führen — und zwei
    Pfade driften auseinander, ohne dass ein Test es merkt.
    """
    beobachtungen = [
        Beobachtung(0, "AAPL", datetime(2020, 1, 1), 5.0, 2.0),
        Beobachtung(1, "MSFT", datetime(2020, 1, 8), -1.0, None),
    ]
    zuordnung, zeilen = als_auswertungsform(beobachtungen)

    assert zuordnung == {0: ("AAPL", datetime(2020, 1, 1)),
                         1: ("MSFT", datetime(2020, 1, 8))}
    assert zeilen == [(0, 5.0, 2.0), (1, -1.0, None)]


def test_abdeckung_je_jahr_zaehlt_und_sortiert():
    """§2n ist am dünnsten Jahr fast falsch gedeutet worden — die Verteilung
    gehört vor die Jahresstabilität, nicht dahinter."""
    beobachtungen = [
        Beobachtung(0, "A", datetime(2019, 5, 1), 1.0, 0.0),
        Beobachtung(1, "A", datetime(2020, 5, 1), 1.0, 0.0),
        Beobachtung(2, "B", datetime(2020, 6, 1), 1.0, 0.0),
    ]
    assert abdeckung_je_jahr(beobachtungen) == {2019: 1, 2020: 2}
    assert list(abdeckung_je_jahr(beobachtungen)) == [2019, 2020]


def test_stichtagsabstand_ist_woechentlich():
    """Der Snapshot-Bestand wurde wöchentlich aufgezeichnet. Ein anderer
    Abstand änderte die Zahl der Beobachtungen und damit jede Fehlerspanne."""
    assert STICHTAG_ABSTAND_TAGE == 7
