"""
tests/test_accruals.py — Periodenabgrenzungen als Signalquelle (P2-06).

Geprüft wird das, was diesen Befund still wertlos machen würde: eine Zahl aus
der Vergleichsspalte des Folgejahres, die als damals bekannt gilt; eine
Halbjahresgröße, die als Jahreswert durchgeht; eine Bilanzsumme von null als
Nenner; und ein umgedrehtes Vorzeichen, das Sloans Hypothese zur Widerlegung
macht.

Dazu die Kursnähe-Prüfung, die §2f zur stehenden Regel gemacht hat.
"""

from datetime import date, datetime, timedelta

import pytest

from services.accruals import (
    JAHRESDAUER, MAX_ALTER_TAGE, MIN_ABSTAND_TAGE, _erste_einreichung,
    accruals_laden, letzter_accrual_vor,
)
from snapshot_engine.auswertung.accruals import QUANTILE, _spread, quintil
from snapshot_engine.auswertung.kursnaehe import (
    SCHWELLE_KURSNAH, rangkorrelation,
)


def _fakt(start, ende, eingereicht, wert):
    fakt = {"end": ende, "filed": eingereicht, "val": wert}
    if start is not None:
        fakt["start"] = start
    return fakt


# ---------------------------------------------------------------------------
# Punkt-in-Zeit: die früheste Einreichung gewinnt
# ---------------------------------------------------------------------------

def test_die_frueheste_einreichung_gewinnt():
    """Der Kern der Punkt-in-Zeit-Datierung.

    Dieselbe Periode erscheint in mehreren Abschlüssen — im eigenen und als
    Vergleichsspalte der Folgejahre. Nur die erste Nennung ist der Zeitpunkt,
    an dem die Zahl öffentlich wurde. Die `frames`-Schnittstelle der SEC
    liefert stattdessen die letzte; für CY2020Q1 stammen dort 84 Prozent der
    Werte aus einer Einreichung von 2021.
    """
    gefunden = _erste_einreichung([
        _fakt("2020-01-01", "2020-12-31", "2022-02-01", 999.0),
        _fakt("2020-01-01", "2020-12-31", "2021-02-01", 100.0),
        _fakt("2020-01-01", "2020-12-31", "2023-02-01", 888.0),
    ], zeitraum=True)
    assert gefunden["2020-12-31"] == (date(2021, 2, 1), 100.0)


def test_nur_jahresgroessen_zaehlen():
    """Ein Halbjahreswert als Jahreswert gelesen halbierte den Zähler des
    Accruals, ohne dass irgendwo eine Zahl fehlte."""
    gefunden = _erste_einreichung([
        _fakt("2020-07-01", "2020-12-31", "2021-02-01", 50.0),   # 183 Tage
        _fakt("2020-01-01", "2020-12-31", "2021-02-01", 100.0),  # 365 Tage
    ], zeitraum=True)
    assert list(gefunden.values()) == [(date(2021, 2, 1), 100.0)]


@pytest.mark.parametrize("tage", [JAHRESDAUER[0], 365, JAHRESDAUER[1]])
def test_das_geschaeftsjahr_darf_von_365_tagen_abweichen(tage):
    """52/53-Wochen-Geschäftsjahre im Einzelhandel und Schaltjahre."""
    ende = date(2021, 1, 1)
    beginn = ende - timedelta(days=tage)
    gefunden = _erste_einreichung(
        [_fakt(beginn.isoformat(), ende.isoformat(), "2021-03-01", 7.0)],
        zeitraum=True)
    assert len(gefunden) == 1


def test_bestandsgroessen_haben_keinen_beginn():
    """Die Bilanzsumme ist ein Stichtagswert. Würde sie wie eine Stromgröße
    gelesen, fiele sie ganz heraus — und mit ihr jeder Accrual."""
    fakten = [_fakt(None, "2020-12-31", "2021-02-01", 5000.0),
              _fakt("2020-01-01", "2020-12-31", "2021-02-01", 100.0)]
    bestand = _erste_einreichung(fakten, zeitraum=False)
    strom = _erste_einreichung(fakten, zeitraum=True)
    assert bestand["2020-12-31"][1] == 5000.0
    assert strom["2020-12-31"][1] == 100.0


def test_unvollstaendige_fakten_werden_uebergangen():
    assert _erste_einreichung([
        {"end": "2020-12-31", "val": 1.0},                       # ohne filed
        {"filed": "2021-02-01", "val": 1.0},                     # ohne end
        _fakt("2020-01-01", "2020-12-31", "2021-02-01", None),   # ohne Wert
    ], zeitraum=True) == {}


# ---------------------------------------------------------------------------
# Zusammensetzung der Kennzahl
# ---------------------------------------------------------------------------

def _stelle_konzepte(monkeypatch, gewinn, cashflow, bilanz):
    import services.accruals as modul

    def _laden(cik, konzept):
        if konzept in modul.KONZEPTE_GEWINN:
            return gewinn
        if konzept in modul.KONZEPTE_CASHFLOW:
            return cashflow
        return bilanz

    monkeypatch.setattr(modul, "_konzept_laden", _laden)


def test_accrual_ist_gewinn_minus_cashflow_durch_bilanzsumme(monkeypatch):
    _stelle_konzepte(
        monkeypatch,
        [_fakt("2020-01-01", "2020-12-31", "2021-02-10", 300.0)],
        [_fakt("2020-01-01", "2020-12-31", "2021-02-10", 200.0)],
        [_fakt(None, "2020-12-31", "2021-02-10", 1000.0)])

    kennzahl = accruals_laden("XYZ", "0000000001")[0]
    assert kennzahl["accrual"] == pytest.approx(0.1)
    assert kennzahl["bekannt_ab"] == datetime(2021, 2, 10)


def test_bekannt_ab_ist_der_spaeteste_bestandteil(monkeypatch):
    """Berechenbar ist die Kennzahl erst, wenn alle drei Zahlen öffentlich
    sind. Das früheste Datum zu nehmen wäre Look-ahead um die Differenz."""
    _stelle_konzepte(
        monkeypatch,
        [_fakt("2020-01-01", "2020-12-31", "2021-02-10", 300.0)],
        [_fakt("2020-01-01", "2020-12-31", "2021-05-20", 200.0)],
        [_fakt(None, "2020-12-31", "2021-03-01", 1000.0)])

    assert accruals_laden("XYZ", "0000000001")[0]["bekannt_ab"] == datetime(2021, 5, 20)


def test_bilanzsumme_null_liefert_keine_kennzahl(monkeypatch):
    """Kein Nenner, kein Accrual — und keine Division durch null."""
    _stelle_konzepte(
        monkeypatch,
        [_fakt("2020-01-01", "2020-12-31", "2021-02-10", 300.0)],
        [_fakt("2020-01-01", "2020-12-31", "2021-02-10", 200.0)],
        [_fakt(None, "2020-12-31", "2021-02-10", 0.0)])

    assert accruals_laden("XYZ", "0000000001") == []


def test_ohne_cashflow_keine_kennzahl(monkeypatch):
    """Banken und Versicherer zeichnen den operativen Cashflow oft anders aus;
    dann bleibt der Titel ohne Kennzahl statt mit einer halben."""
    _stelle_konzepte(
        monkeypatch,
        [_fakt("2020-01-01", "2020-12-31", "2021-02-10", 300.0)],
        [],
        [_fakt(None, "2020-12-31", "2021-02-10", 1000.0)])

    assert accruals_laden("XYZ", "0000000001") == []


def test_nur_perioden_mit_allen_drei_bestandteilen(monkeypatch):
    _stelle_konzepte(
        monkeypatch,
        [_fakt("2019-01-01", "2019-12-31", "2020-02-10", 100.0),
         _fakt("2020-01-01", "2020-12-31", "2021-02-10", 300.0)],
        [_fakt("2020-01-01", "2020-12-31", "2021-02-10", 200.0)],
        [_fakt(None, "2019-12-31", "2020-02-10", 900.0),
         _fakt(None, "2020-12-31", "2021-02-10", 1000.0)])

    kennzahlen = accruals_laden("XYZ", "0000000001")
    assert [k["periode_ende"] for k in kennzahlen] == [datetime(2020, 12, 31)]


# ---------------------------------------------------------------------------
# Auswahl zum Snapshot-Zeitpunkt
# ---------------------------------------------------------------------------

STICHTAG = datetime(2024, 6, 15)


def _reihe(*abstaende_und_werte):
    reihe = [(STICHTAG - timedelta(days=t), w) for t, w in abstaende_und_werte]
    reihe.sort(key=lambda e: e[0])
    return reihe


def test_die_juengste_bekannte_kennzahl_gewinnt():
    treffer = letzter_accrual_vor(_reihe((400, 0.01), (100, 0.05)), STICHTAG)
    assert treffer[1] == 0.05 and treffer[2] == 100


def test_die_heute_veroeffentlichte_zahl_zaehlt_nicht():
    assert letzter_accrual_vor(_reihe((0, 0.05)), STICHTAG) is None
    assert letzter_accrual_vor(_reihe((MIN_ABSTAND_TAGE, 0.05)), STICHTAG) is not None


def test_ueberholte_abschluesse_fallen_heraus():
    """Ohne Obergrenze würde ein Titel, der seit Jahren nichts Auswertbares
    veröffentlicht, dauerhaft an einer Zahl von 2019 gemessen."""
    assert letzter_accrual_vor(_reihe((MAX_ALTER_TAGE + 1, 0.05)), STICHTAG) is None
    assert letzter_accrual_vor(_reihe((MAX_ALTER_TAGE, 0.05)), STICHTAG) is not None


@pytest.mark.parametrize("reihe", [None, []])
def test_ohne_reihe_keine_kennzahl(reihe):
    assert letzter_accrual_vor(reihe, STICHTAG) is None


# ---------------------------------------------------------------------------
# Richtung der Hypothese
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rang, erwartet", [
    (0.0, 1), (19.9, 1), (20.0, 2), (79.9, 4), (80.0, 5), (100.0, 5),
])
def test_quintil_grenzen(rang, erwartet):
    assert quintil(rang) == erwartet


def test_der_spread_ist_hier_umgekehrt_gerechnet():
    """Bei Sloan ist unten gut: niedrige Abgrenzungen, bessere Folgerendite.
    `_spread` rechnet deshalb Q1 minus Q5, damit ein positiver Wert auch in
    diesem Modul „Hypothese bestätigt" heißt und nicht das Gegenteil."""
    zeilen = [{"quintil": 1, "markt_trefferquote": 52.0},
              {"quintil": QUANTILE, "markt_trefferquote": 48.0}]
    assert _spread(zeilen) == 4.0

    umgekehrt = [{"quintil": 1, "markt_trefferquote": 48.0},
                 {"quintil": QUANTILE, "markt_trefferquote": 52.0}]
    assert _spread(umgekehrt) == -4.0


def test_ohne_beide_enden_kein_spread():
    assert _spread([{"quintil": 1, "markt_trefferquote": 52.0}]) is None
    assert _spread([{"quintil": 1, "markt_trefferquote": None},
                    {"quintil": QUANTILE, "markt_trefferquote": 48.0}]) is None


# ---------------------------------------------------------------------------
# Kursnähe — die stehende Regel aus §2f
# ---------------------------------------------------------------------------

def test_rangkorrelation_erkennt_gleich_und_gegenlauf():
    assert rangkorrelation([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)
    assert rangkorrelation([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)


def test_rangkorrelation_rechnet_auf_raengen_nicht_auf_werten():
    """Beide Größen haben schwere Ränder — eine Kurszielanhebung um 1875 Prozent
    kam in den echten Daten vor. Auf Rohwerten würde ein einzelner Ausreißer
    die Korrelation bestimmen."""
    ohne = [1.0, 2.0, 3.0, 4.0, 5.0]
    mit_ausreisser = [1.0, 2.0, 3.0, 4.0, 10_000.0]
    assert (rangkorrelation(ohne, mit_ausreisser)
            == pytest.approx(rangkorrelation(ohne, ohne)))


def test_bindungen_bekommen_denselben_rang():
    assert rangkorrelation([1, 1, 2, 2], [1, 1, 2, 2]) == pytest.approx(1.0)


@pytest.mark.parametrize("a, b", [
    ([1, 1, 1, 1], [1, 2, 3, 4]),   # konstante Reihe
    ([1, 2], [1, 2]),               # zu kurz
    ([1, 2, 3], [1, 2]),            # ungleich lang
])
def test_ohne_grundlage_keine_rangkorrelation(a, b):
    assert rangkorrelation(a, b) is None


def test_die_schwelle_liegt_unter_dem_gemessenen_fall():
    """Die Zielrevision der Analysten lag bei 0,47 und gilt als kursnah — die
    Schwelle muss darunter liegen, sonst hätte die Regel den Fall nicht
    erkannt, für den sie eingeführt wurde."""
    assert SCHWELLE_KURSNAH < 0.47
