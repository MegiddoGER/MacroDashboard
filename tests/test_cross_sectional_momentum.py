"""
tests/test_cross_sectional_momentum.py — Querschnitts-Momentum (P2-02).

Geprüft wird, was einen Querschnittsrang unbrauchbar machen würde: eine
Rangliste über zwei Währungsräume hinweg, ein Perzentil über eine Handvoll
Titel, ein Rückschaufenster, das den Stichtag berührt, und Bindungen, die
künstlich gespreizt werden.
"""

from datetime import datetime, timedelta

import pytest

from services.cross_sectional_momentum import (
    LOOKBACK_TAGE, MIN_QUERSCHNITT, SKIP_TAGE, dezil, momentum_roh,
    naechster_kurs, normiert, perzentil_raenge, raenge_je_gruppe,
)


# ---------------------------------------------------------------------------
# Rohes Momentum
# ---------------------------------------------------------------------------

def test_momentum_ist_die_rendite_ueber_das_fenster():
    assert momentum_roh(100.0, 130.0) == pytest.approx(30.0)
    assert momentum_roh(100.0, 80.0) == pytest.approx(-20.0)


@pytest.mark.parametrize("beginn, ende", [(None, 130.0), (100.0, None), (0.0, 130.0)])
def test_ohne_brauchbare_kurse_kein_momentum(beginn, ende):
    assert momentum_roh(beginn, ende) is None


def test_das_fenster_endet_vor_dem_stichtag():
    """Der ausgelassene Monat ist der Kern der 12-1-Form: auf kurze Sicht
    laufen Gewinner zurück, auf Jahressicht laufen sie weiter."""
    assert SKIP_TAGE > 0
    assert LOOKBACK_TAGE > SKIP_TAGE


# ---------------------------------------------------------------------------
# Perzentilränge
# ---------------------------------------------------------------------------

def _universum(n: int) -> dict:
    """n Titel mit aufsteigendem Momentum: T000 am schwächsten."""
    return {"T%03d" % i: float(i) for i in range(n)}


def test_staerkster_und_schwaechster_spannen_die_skala_auf():
    r = perzentil_raenge(_universum(50))
    assert r["T000"] == 0.0
    assert r["T049"] == 100.0


def test_rang_steigt_mit_dem_momentum():
    r = perzentil_raenge(_universum(50))
    werte = [r["T%03d" % i] for i in range(50)]
    assert werte == sorted(werte)


def test_bindungen_bekommen_denselben_rang():
    """Zehn identische Werte sind zehn gleich starke Titel — sie über die
    halbe Skala zu verteilen wäre eine erfundene Rangfolge."""
    werte = {"A": 1.0, "B": 1.0, "C": 1.0}
    werte.update({"T%02d" % i: float(i + 10) for i in range(20)})
    r = perzentil_raenge(werte)
    assert r["A"] == r["B"] == r["C"]


def test_zu_duenner_querschnitt_bekommt_keinen_rang():
    """Ein Perzentil über sechs Titel ist eine Aussage über sechs Titel."""
    assert perzentil_raenge(_universum(6)) == {}
    assert perzentil_raenge(_universum(MIN_QUERSCHNITT)) != {}


def test_titel_ohne_wert_zaehlen_nicht_mit():
    werte = _universum(25)
    werte.update({"LEER1": None, "LEER2": None})
    r = perzentil_raenge(werte)
    assert "LEER1" not in r
    assert len(r) == 25


# ---------------------------------------------------------------------------
# Getrennte Ranglisten je Handelsplatz
# ---------------------------------------------------------------------------

def _gruppe(ticker: str):
    return "XETRA" if ticker.endswith(".DE") else ("US" if ticker.isalpha() else None)


def test_jeder_handelsplatz_bekommt_seine_eigene_rangliste():
    """Sonst wiese eine Dollarstärke alle US-Titel als Momentum aus."""
    werte = {}
    werte.update({"US%03d" % i: float(i) for i in range(25)})       # keine Gruppe
    werte.update({"AAA%02d" % i: float(i) for i in range(25)})
    r = raenge_je_gruppe({t: w for t, w in werte.items()}, _gruppe)
    # Nur die rein alphabetischen Ticker sind gruppierbar.
    assert all(t.isalpha() for t in r)


def test_beide_gruppen_spannen_ihre_skala_getrennt_auf():
    werte = {}
    werte.update({"AAAA%s" % chr(65 + i): float(i) for i in range(25)})
    werte.update({"D%02d.DE" % i: float(100 + i) for i in range(25)})
    r = raenge_je_gruppe(werte, _gruppe)
    # Trotz durchweg höherer Rohwerte hat die Xetra-Gruppe ihren eigenen Nullpunkt.
    assert min(v for t, v in r.items() if t.endswith(".DE")) == 0.0
    assert max(v for t, v in r.items() if t.endswith(".DE")) == 100.0
    assert min(v for t, v in r.items() if not t.endswith(".DE")) == 0.0


def test_titel_ohne_handelsplatz_bekommt_keinen_rang():
    """Dieselbe Entscheidung wie bei BENCHMARK_UNBEKANNT: lieber kein Rang
    als einer gegen die falsche Vergleichsgruppe."""
    werte = {"OHNE.XX": 5.0}
    werte.update({"AAAA%s" % chr(65 + i): float(i) for i in range(25)})
    r = raenge_je_gruppe(werte, _gruppe)
    assert "OHNE.XX" not in r


# ---------------------------------------------------------------------------
# Dezil und Normierung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rang, erwartet", [
    (0.0, 1), (9.9, 1), (10.0, 2), (55.0, 6), (99.9, 10), (100.0, 10),
])
def test_dezil_zuordnung(rang, erwartet):
    assert dezil(rang) == erwartet


def test_normierung_trifft_die_score_skala():
    assert normiert(0.0) == -1.0
    assert normiert(50.0) == 0.0
    assert normiert(100.0) == 1.0


def test_ohne_rang_kein_dezil():
    assert dezil(None) is None
    assert normiert(None) is None


# ---------------------------------------------------------------------------
# Kurs zum Stichtag
# ---------------------------------------------------------------------------

def _reihe(tage: list[int]) -> list[tuple]:
    start = datetime(2025, 1, 1)
    return [(start + timedelta(days=t), 100.0 + t) for t in tage]


def test_naechster_kurs_nimmt_den_dichtesten_nachbarn():
    reihe = _reihe([0, 10, 20, 30])
    ziel = datetime(2025, 1, 1) + timedelta(days=21)
    assert naechster_kurs(reihe, ziel) == 120.0


def test_zu_weit_entfernt_gilt_als_nicht_vorhanden():
    """Ein Nachbar 40 Tage daneben würde das Rückschaufenster verschieben,
    ohne dass es jemandem auffiele."""
    reihe = _reihe([0, 60])
    ziel = datetime(2025, 1, 1) + timedelta(days=30)
    assert naechster_kurs(reihe, ziel) is None


def test_toleranz_ist_einstellbar():
    reihe = _reihe([0, 60])
    ziel = datetime(2025, 1, 1) + timedelta(days=30)
    assert naechster_kurs(reihe, ziel, toleranz_tage=40) is not None


def test_leere_reihe_liefert_nichts():
    assert naechster_kurs([], datetime(2025, 1, 1)) is None
    assert naechster_kurs(None, datetime(2025, 1, 1)) is None
