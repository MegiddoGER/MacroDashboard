"""
tests/test_kodierung.py — Stetige gegen binäre Kodierung (§2h).

Geprüft wird das, was den Kontrollversuch entwerten würde: ein gleitendes
Mittel, das einen Kurs aus der Zukunft einschließt; ein Fenster, das aus drei
Stützstellen einen „Mittelwert" macht; ein Vorzeichen, das die Engine nicht
nachbildet, sondern verbessert; und ein Spread, dessen beide Fassungen
verschieden herum gerechnet sind.
"""

from datetime import datetime, timedelta

import pytest

from services.stetige_indikatoren import (
    FENSTER_KURZ_TAGE, FENSTER_LANG_TAGE, MIN_STUETZSTELLEN_LANG,
    gleitender_mittelwert, ma_spreizung, sma_abstand, vorzeichen,
)
from snapshot_engine.auswertung.kodierung import (
    GROESSEN, QUANTILE, _spread, quintil,
)


BEGINN = datetime(2024, 1, 1)


def _reihe(n: int, start: float = 100.0, schritt: float = 2.0,
           takt_tage: int = 8) -> list:
    """n Stützstellen im Achttagetakt — die gemessene Kadenz des Bestands."""
    return [(BEGINN + timedelta(days=takt_tage * i), start + schritt * i)
            for i in range(n)]


# ---------------------------------------------------------------------------
# Gleitendes Mittel
# ---------------------------------------------------------------------------

def test_das_mittel_ist_der_schnitt_des_fensters():
    reihe = [(BEGINN + timedelta(days=8 * i), 100.0) for i in range(30)]
    ende = reihe[-1][0]
    assert gleitender_mittelwert(reihe, ende, FENSTER_LANG_TAGE, 20) == pytest.approx(100.0)


def test_kein_kurs_aus_der_zukunft_geht_ein():
    """Der Kern der Look-ahead-Sicherung: dieselbe Reihe, einmal mit einem
    späteren Punkt ergänzt, muss am selben Stichtag denselben Wert liefern."""
    reihe = _reihe(40)
    stichtag = reihe[-1][0]
    mit_zukunft = reihe + [(stichtag + timedelta(days=8), 99_999.0)]
    assert (gleitender_mittelwert(mit_zukunft, stichtag, FENSTER_LANG_TAGE, 20)
            == gleitender_mittelwert(reihe, stichtag, FENSTER_LANG_TAGE, 20))


def test_der_kurs_des_stichtags_gehoert_dazu():
    """Kein Look-ahead, sondern die Definition: ein gleitendes Mittel schließt
    den aktuellen, zu diesem Zeitpunkt bekannten Kurs ein."""
    reihe = [(BEGINN, 100.0), (BEGINN + timedelta(days=8), 200.0)]
    assert gleitender_mittelwert(reihe, reihe[-1][0], 280, 2) == pytest.approx(150.0)


def test_ein_zu_duennes_fenster_liefert_nichts():
    """Bei acht Tagen Kadenz erwartet das lange Fenster rund 35 Stützstellen.
    Unter der Mindestzahl wäre der Mittelwert von Lücken getrieben statt vom
    Kursverlauf — und das fällt hinterher niemandem mehr auf."""
    assert gleitender_mittelwert(_reihe(5), _reihe(5)[-1][0],
                                 FENSTER_LANG_TAGE, MIN_STUETZSTELLEN_LANG) is None


def test_kurse_ausserhalb_des_fensters_zaehlen_nicht():
    lang = _reihe(80)
    stichtag = lang[-1][0]
    # Nur die letzten 280 Tage, also rund 35 der 80 Punkte.
    mittel = gleitender_mittelwert(lang, stichtag, FENSTER_LANG_TAGE, 20)
    gesamt = sum(k for _, k in lang) / len(lang)
    assert mittel > gesamt


@pytest.mark.parametrize("reihe", [None, []])
def test_ohne_reihe_kein_mittel(reihe):
    assert gleitender_mittelwert(reihe, BEGINN, FENSTER_LANG_TAGE, 20) is None


# ---------------------------------------------------------------------------
# Die stetigen Größen
# ---------------------------------------------------------------------------

def test_steigende_reihe_liegt_ueber_ihrem_mittel():
    reihe = _reihe(40)
    assert sma_abstand(reihe, reihe[-1][0]) > 0


def test_fallende_reihe_liegt_unter_ihrem_mittel():
    reihe = _reihe(40, start=200.0, schritt=-2.0)
    assert sma_abstand(reihe, reihe[-1][0]) < 0


def test_flache_reihe_hat_abstand_null():
    reihe = [(BEGINN + timedelta(days=8 * i), 100.0) for i in range(40)]
    assert sma_abstand(reihe, reihe[-1][0]) == pytest.approx(0.0)


def test_die_staerke_bleibt_erhalten():
    """Der ganze Zweck des Moduls: zwei Titel, beide über ihrem Mittel, müssen
    unterschiedliche Werte bekommen. In der Kodierung der Engine sind sie
    beide +1 — 274.839 Zeilen mit genau zwei verschiedenen Werten."""
    schwach = _reihe(40, start=100.0, schritt=0.05)
    stark = _reihe(40, start=100.0, schritt=5.0)
    a = sma_abstand(schwach, schwach[-1][0])
    b = sma_abstand(stark, stark[-1][0])
    assert 0 < a < b
    assert vorzeichen(a) == vorzeichen(b) == 1


def test_die_spreizung_vergleicht_kurzes_mit_langem_mittel():
    reihe = _reihe(40)
    assert ma_spreizung(reihe, reihe[-1][0]) > 0
    assert FENSTER_KURZ_TAGE < FENSTER_LANG_TAGE


def test_ohne_langes_fenster_keine_spreizung():
    kurz = _reihe(8)
    assert ma_spreizung(kurz, kurz[-1][0]) is None


# ---------------------------------------------------------------------------
# Das Vorzeichen bildet die Engine nach
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("wert, erwartet", [
    (5.0, 1), (0.001, 1), (0.0, 1), (-0.001, -1), (-5.0, -1),
])
def test_vorzeichen_null_gilt_als_bullisch(wert, erwartet):
    """`services/scoring.py` bildet das Flag aus einem `>=`-Vergleich. Die
    Kontrolle muss die Engine nachbilden, nicht verbessern — sonst vergliche
    der Versuch zwei verschiedene Dinge."""
    assert vorzeichen(wert) == erwartet


def test_ohne_wert_kein_vorzeichen():
    assert vorzeichen(None) is None


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rang, erwartet", [
    (0.0, 1), (19.9, 1), (20.0, 2), (79.9, 4), (80.0, 5), (100.0, 5),
])
def test_quintil_grenzen(rang, erwartet):
    assert quintil(rang) == erwartet


def test_beide_fassungen_rechnen_oben_minus_unten():
    """Sonst wäre der Vergleich zwischen stetiger und binärer Fassung ein
    Vorzeichenfehler statt einer Aussage."""
    stetig = [{"quintil": 1, "markt_trefferquote": 48.0},
              {"quintil": QUANTILE, "markt_trefferquote": 51.0}]
    binaer = [{"vorzeichen": -1, "markt_trefferquote": 48.0},
              {"vorzeichen": 1, "markt_trefferquote": 51.0}]
    assert _spread(stetig, "quintil", QUANTILE, 1) == 3.0
    assert _spread(binaer, "vorzeichen", 1, -1) == 3.0


def test_ohne_beide_enden_kein_spread():
    assert _spread([{"quintil": 1, "markt_trefferquote": 48.0}],
                   "quintil", QUANTILE, 1) is None


def test_die_groessen_heissen_wie_die_indikatoren_der_engine():
    """Ein Befund muss ohne Umweg auf `services/scoring.py` zeigen können."""
    assert "Trend (SMA 200)" in GROESSEN
    assert "SMA-Cross (20/50)" in GROESSEN
    assert all(callable(f) for f in GROESSEN.values())
