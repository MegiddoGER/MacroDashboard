"""
tests/test_renditespanne.py — Die Fehlerspanne auf der Rendite (S6).

Der blinde Fleck, der die ganze Messreihe begleitet hat: jedes Urteil hing an
der **Trefferquote** — wie oft ein Titel vorn liegt. Die mittlere Überrendite
wurde berechnet, aber nie auf Signifikanz geprüft, also nie zu einem Urteil.

Beide Größen können auseinanderlaufen. Ein Eingang, der nur in 50,3 % der
Fälle vorn liegt, dabei aber deutlich mehr gewinnt als verliert, ist nach der
Quote Rauschen und nach der Rendite ein Faktor. Die Literatur misst
durchgehend das Zweite.

Geprüft wird hier, was diese neue Zahl wertlos machen würde:

  * die Zeilenzahl statt der effektiven Stichprobe — der Fehler wäre dann bei
    90-Tage-Horizonten um den Faktor 3,5 zu klein und alles signifikant,
  * eine fehlende Korrektur bei vielen Zellen,
  * ein Urteil bei einer Stichprobe, die keines trägt.
"""

import math

import pytest

from snapshot_engine.auswertung.basis import (
    Z_95, effektive_stichprobe, fehlerspanne_mittelwert_pp, mit_ueberrendite,
    z_korrigiert, zelle_gegen_markt,
)


# ---------------------------------------------------------------------------
# Die Formel selbst
# ---------------------------------------------------------------------------

def test_fehlerspanne_ist_z_mal_standardfehler():
    """Streuung 5,0 über 100 unabhängige Beobachtungen → 1,96 · 0,5."""
    erwartet = Z_95 * 5.0 / 10.0
    assert fehlerspanne_mittelwert_pp(5.0, 100) == pytest.approx(erwartet, abs=0.001)


def test_groessere_stichprobe_verengt_die_spanne():
    eng = fehlerspanne_mittelwert_pp(5.0, 10_000)
    weit = fehlerspanne_mittelwert_pp(5.0, 100)
    assert eng < weit
    # Hundertfache Stichprobe → zehnfach engere Spanne (Wurzelgesetz).
    assert weit / eng == pytest.approx(10.0, rel=0.01)


def test_korrigiertes_z_weitet_die_spanne():
    """Bei 210 Zellen muss ein Fund deutlich größer ausfallen."""
    z = z_korrigiert(210)
    assert fehlerspanne_mittelwert_pp(5.0, 100, z) > fehlerspanne_mittelwert_pp(5.0, 100)


def test_ohne_streuung_oder_stichprobe_gibt_es_kein_urteil():
    assert fehlerspanne_mittelwert_pp(None, 100) is None
    assert fehlerspanne_mittelwert_pp(5.0, 0) is None
    assert fehlerspanne_mittelwert_pp(5.0, None) is None


# ---------------------------------------------------------------------------
# Die effektive Stichprobe — der teuerste mögliche Fehler
# ---------------------------------------------------------------------------

def test_ueberlappung_muss_die_spanne_weiten():
    """Mit der Zeilenzahl gerechnet wäre auf 90 Tagen fast alles signifikant.

    300 Beobachtungen mit 90-Tage-Horizont sind rund 23 unabhängige. Wer die
    Wurzel aus 300 statt aus 23 zieht, macht den Fehler um den Faktor 3,6 zu
    klein — und aus Rauschen einen Fund.
    """
    roh = 300
    effektiv = effektive_stichprobe(roh, 90)
    assert effektiv < roh / 3

    zu_klein = fehlerspanne_mittelwert_pp(5.0, roh)
    ehrlich = fehlerspanne_mittelwert_pp(5.0, effektiv)
    assert ehrlich > zu_klein * 3


# ---------------------------------------------------------------------------
# Im Zusammenspiel
# ---------------------------------------------------------------------------

def _zeile(ueberrenditen, horizont=7, basis_ertrag=0.0):
    richtungen = [1] * len(ueberrenditen)
    return mit_ueberrendite({}, ueberrenditen, richtungen, anteil_markt=50.0,
                            horizont_tage=horizont, minimum=1,
                            basis_ertrag=basis_ertrag)


def test_konstanter_vorsprung_ist_signifikant():
    """Kein Rauschen, nur Vorsprung — die Spanne muss verschwinden."""
    zeile = _zeile([1.0] * 500)
    assert zeile["ueberrendite_mittel_pp"] == pytest.approx(1.0)
    assert zeile["ueberrendite_streuung_pp"] == pytest.approx(0.0)
    assert zeile["ueberrendite_signifikant"] is True


def test_symmetrisches_rauschen_ist_nicht_signifikant():
    """Mittelwert null bei grosser Streuung — kein Ertrag, egal wie viele Zeilen."""
    zeile = _zeile([10.0, -10.0] * 500)
    assert zeile["ueberrendite_mittel_pp"] == pytest.approx(0.0)
    assert zeile["ueberrendite_signifikant"] is False


def test_quote_und_rendite_koennen_auseinanderlaufen():
    """Der Fall, für den diese Zahl gebaut wurde.

    Neun kleine Verluste, ein grosser Gewinn: die Trefferquote liegt bei
    10 Prozent — nach der Quote ein Desaster. Der Mittelwert ist deutlich
    positiv. Genau diese Konstellation konnte die Engine bisher nicht sehen.
    """
    zeile = _zeile(([-1.0] * 9 + [20.0]) * 60)
    assert zeile["markt_trefferquote"] == pytest.approx(10.0, abs=0.1)
    assert zeile["ueberrendite_mittel_pp"] > 0
    assert zeile["ueberrendite_signifikant"] is True


def test_zu_kleine_stichprobe_faellt_die_felder_auf_none():
    zeile = mit_ueberrendite({}, [1.0, 2.0], [1, 1], anteil_markt=50.0,
                             horizont_tage=90, minimum=20, basis_ertrag=0.0)
    assert zeile["ueberrendite_fehler_pp"] is None
    assert zeile["ueberrendite_signifikant"] is None


def test_zelle_gegen_markt_traegt_beide_urteile():
    """Quote und Rendite stehen nebeneinander, keines ersetzt das andere."""
    ueberrenditen = ([-1.0] * 9 + [20.0]) * 60
    zeile = zelle_gegen_markt([u for u in ueberrenditen], ueberrenditen,
                              basis_markt=50.0, horizont_tage=7, minimum=1,
                              z=z_korrigiert(210), basis_ertrag=0.0)

    assert "signifikant_korrigiert" in zeile
    assert "ueberrendite_signifikant_korrigiert" in zeile
    # Nach der Quote schlecht, nach der Rendite gut — beide Urteile sichtbar.
    assert zeile["markt_trefferquote"] < 50
    assert zeile["ueberrendite_mittel_pp"] > 0


# ---------------------------------------------------------------------------
# Der Bezugspunkt — der Fehler, der beim ersten Anlauf 47 Funde erzeugt hat
# ---------------------------------------------------------------------------

def test_eine_zelle_auf_hoehe_der_basis_ist_kein_fund():
    """Der Regressionstest fuer einen selbst gemachten Fehler.

    Beim ersten Anlauf wurde gegen NULL geprueft statt gegen die
    Grundgesamtheit. Ergebnis: 47 von 150 Zellen erschienen signifikant, und
    zwar Q1 UND Q5 desselben Instruments, bei allen zehn Instrumenten, mit
    Werten proportional zum Horizont (+0,04 / +0,30 / +0,83 pp). Das war die
    Drift des Bestandes, kein Signal.

    Dieselbe Falle wie 50 % statt 48,1 % bei der Trefferquote, nur
    gespiegelt: gegen null sieht JEDE Auswahl nach einem Vorsprung aus.
    """
    # Zelle liegt exakt auf der Basis — es gibt nichts zu finden.
    zeile = _zeile([0.83] * 2000, horizont=90, basis_ertrag=0.83)
    assert zeile["ueberrendite_mittel_pp"] == pytest.approx(0.83)
    assert zeile["ueberrendite_vorsprung_pp"] == pytest.approx(0.0)
    assert zeile["ueberrendite_signifikant"] is False

    # Gegen null geprueft waere dieselbe Zelle ein klarer "Fund".
    falsch = _zeile([0.83] * 2000, horizont=90, basis_ertrag=0.0)
    assert falsch["ueberrendite_signifikant"] is True


def test_ohne_basis_gibt_es_kein_renditeurteil():
    """Eine Renditeaussage ohne Bezugspunkt ist so wenig interpretierbar
    wie eine Trefferquote ohne Basisrate — dann bleibt das Urteil leer."""
    zeile = mit_ueberrendite({}, [1.0] * 100, [1] * 100, anteil_markt=50.0,
                             horizont_tage=7, minimum=1, basis_ertrag=None)
    assert zeile["ueberrendite_mittel_pp"] == pytest.approx(1.0)
    assert zeile["ueberrendite_vorsprung_pp"] is None
    assert zeile["ueberrendite_signifikant"] is None
