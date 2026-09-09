"""
tests/test_kerzenmuster.py — Erkennung der Kerzenmuster (Reiter Kursverhalten).

Der Schwerpunkt liegt auf zwei Dingen.

**Erstens die Trennung durch den Vortrend.** Hammer und Hanging Man sind
geometrisch IDENTISCH — dieselbe Kerze heisst je nach vorangegangener Bewegung
anders und zeigt in die Gegenrichtung. Dasselbe gilt fuer Inverted Hammer und
Shooting Star. Wer den Vortrend falsch herum anschliesst, dreht damit die halbe
Musterliste um, ohne dass eine einzelne Geometriepruefung fehlschlaegt. Die
erste Testgruppe haelt das fest.

**Zweitens die Ungueltigkeitsmarke.** Sie ist der eigentliche Ertrag der
Anzeige (siehe `KERZENMUSTER.md` Paragraph 2) und je Muster verschieden: bei
Engulfing das Tief der Signalkerze, bei Harami das Tief der VORkerze, beim
Morning Star das Tief der MITTLEREN. Eine Verwechslung faellt sonst nirgends
auf, weil die Zahl immer plausibel aussieht.
"""

from datetime import datetime, timedelta

import pytest

from services.kerzenmuster import (
    MUSTER, VORTREND_TAGE, Kerze, alle_treffer, erkennen,
    kerzen_aus_dataframe, letzte_treffer, umsatz_verhaeltnis, vortrend,
)


def _k(o, h, l, c, v=1000.0, tag=0):
    """Eine Kerze mit fortlaufendem Datum."""
    return Kerze(datum=datetime(2026, 1, 1) + timedelta(days=tag),
                 offen=o, hoch=h, tief=l, schluss=c, volumen=v)


def _vorlauf(richtung, anzahl=12, ende=100.0):
    """Unauffaellige Kerzen mit klarem Trend, endend bei `ende`.

    Braucht mindestens VORTREND_TAGE + 1 Zeilen, sonst ist `vortrend` per
    Definition 0 und jedes trendabhaengige Muster faellt heraus.
    """
    assert anzahl > VORTREND_TAGE
    kurs = ende - richtung * anzahl
    kerzen = []
    for n in range(anzahl):
        naechster = kurs + richtung
        o, c = kurs, naechster
        kerzen.append(_k(o, max(o, c) + 0.1, min(o, c) - 0.1, c, tag=n))
        kurs = naechster
    return kerzen


def _namen(treffer):
    return {t.muster for t in treffer}


def _finde(treffer, name):
    for t in treffer:
        if t.muster == name:
            return t
    raise AssertionError(f"{name} nicht erkannt, gefunden: {_namen(treffer)}")


# ---------------------------------------------------------------------------
# Der Vortrend trennt geometrisch identische Muster — der Kern
# ---------------------------------------------------------------------------

# Kleiner Koerper oben, langer unterer Docht: die Hammer-Geometrie.
# Koerper 0,5 · unterer Docht 2,0 (>= 2x Koerper) · oberer Docht 0,1 (<= Koerper)
HAMMER = dict(o=100.0, h=100.6, l=98.0, c=100.5)

# Spiegelbild: langer oberer Docht.
INVERS = dict(o=100.0, h=102.5, l=99.9, c=100.5)


@pytest.mark.parametrize("richtung, erwartet, unerwartet", [
    (-1, "Hammer", "Hanging Man"),
    (1, "Hanging Man", "Hammer"),
])
def test_hammer_und_hanging_man_trennt_nur_der_vortrend(richtung, erwartet,
                                                        unerwartet):
    """Dieselbe Kerze, zwei Namen — allein der Vortrend entscheidet."""
    kerzen = _vorlauf(richtung)
    i = len(kerzen)
    kerzen.append(_k(**HAMMER, tag=i))

    namen = _namen(erkennen(kerzen, i))
    assert erwartet in namen
    assert unerwartet not in namen


@pytest.mark.parametrize("richtung, erwartet, unerwartet", [
    (-1, "Inverted Hammer", "Shooting Star"),
    (1, "Shooting Star", "Inverted Hammer"),
])
def test_inverser_hammer_und_shooting_star_trennt_nur_der_vortrend(
        richtung, erwartet, unerwartet):
    kerzen = _vorlauf(richtung)
    i = len(kerzen)
    kerzen.append(_k(**INVERS, tag=i))

    namen = _namen(erkennen(kerzen, i))
    assert erwartet in namen
    assert unerwartet not in namen


def test_ohne_ausreichende_historie_kein_trendmuster():
    """Vortrend 0 heisst „unklar" — und nicht „aufwaerts"."""
    # Genau eine Zeile zu wenig: `vortrend` greift auf i-1-VORTREND_TAGE zu.
    kerzen = [_k(110.0 - n, 110.2 - n, 108.8 - n, 109.0 - n, tag=n)
              for n in range(VORTREND_TAGE)]
    i = len(kerzen)
    kerzen.append(_k(**HAMMER, tag=i))

    assert vortrend(kerzen, i) == 0
    namen = _namen(erkennen(kerzen, i))
    assert "Hammer" not in namen and "Hanging Man" not in namen


def test_vortrend_zaehlt_die_musterkerze_nicht_mit():
    """Sonst machte eine grosse gruene Kerze ihren eigenen Vortrend."""
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    # Eine sehr grosse Aufwaertskerze — sie darf den Abwaertstrend nicht drehen.
    kerzen.append(_k(100.0, 140.0, 99.0, 139.0, tag=i))
    assert vortrend(kerzen, i) == -1


# ---------------------------------------------------------------------------
# Zwei-Kerzen-Muster
# ---------------------------------------------------------------------------

def test_bullisches_engulfing_mit_marke_am_tief():
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(102.0, 102.2, 99.8, 100.0, tag=i))          # baerisch
    kerzen.append(_k(99.5, 102.8, 99.0, 102.5, tag=i + 1))       # umschliesst

    t = _finde(erkennen(kerzen, i + 1), "Bullisches Engulfing")
    assert t.richtung == "long"
    assert t.ungueltig_bei == 99.0          # Tief der SIGNALkerze


def test_baerisches_engulfing_mit_marke_am_hoch():
    kerzen = _vorlauf(1)
    i = len(kerzen)
    kerzen.append(_k(100.0, 102.2, 99.8, 102.0, tag=i))          # bullisch
    kerzen.append(_k(102.5, 103.0, 99.2, 99.5, tag=i + 1))       # umschliesst

    t = _finde(erkennen(kerzen, i + 1), "Baerisches Engulfing")
    assert t.richtung == "short"
    assert t.ungueltig_bei == 103.0


def test_engulfing_greift_nicht_bei_unvollstaendiger_umschliessung():
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(102.0, 102.2, 99.8, 100.0, tag=i))
    # Schluss 101,5 liegt UNTER der Vorkerzen-Eroeffnung 102 — nicht umschlossen.
    kerzen.append(_k(99.5, 101.8, 99.0, 101.5, tag=i + 1))

    assert "Bullisches Engulfing" not in _namen(erkennen(kerzen, i + 1))


def test_piercing_line():
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(102.0, 102.3, 99.5, 100.0, tag=i))          # Koerpermitte 101
    kerzen.append(_k(99.0, 101.5, 98.8, 101.2, tag=i + 1))       # oeffnet unter 99,5

    t = _finde(erkennen(kerzen, i + 1), "Piercing Line")
    assert t.richtung == "long"
    assert t.ungueltig_bei == 98.8


def test_dark_cloud_cover():
    kerzen = _vorlauf(1)
    i = len(kerzen)
    kerzen.append(_k(100.0, 102.5, 99.8, 102.0, tag=i))          # Koerpermitte 101
    kerzen.append(_k(103.0, 103.2, 100.5, 100.8, tag=i + 1))     # oeffnet ueber 102,5

    t = _finde(erkennen(kerzen, i + 1), "Dark Cloud Cover")
    assert t.richtung == "short"
    assert t.ungueltig_bei == 103.2


def test_bullisches_harami_markiert_die_VORkerze():
    """Beim Harami liegt die Marke am Tief der Vorkerze, nicht der Signalkerze."""
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(103.0, 103.5, 98.5, 99.0, tag=i))           # grosse baerische
    kerzen.append(_k(100.0, 102.5, 99.8, 102.0, tag=i + 1))      # innerhalb

    t = _finde(erkennen(kerzen, i + 1), "Bullisches Harami")
    assert t.ungueltig_bei == 98.5          # Tief der VORkerze
    assert t.ungueltig_bei != 99.8


def test_baerisches_harami():
    kerzen = _vorlauf(1)
    i = len(kerzen)
    kerzen.append(_k(99.0, 103.5, 98.5, 103.0, tag=i))           # grosse bullische
    kerzen.append(_k(102.0, 102.5, 99.8, 100.0, tag=i + 1))      # innerhalb

    t = _finde(erkennen(kerzen, i + 1), "Baerisches Harami")
    assert t.ungueltig_bei == 103.5


# ---------------------------------------------------------------------------
# Drei-Kerzen-Muster
# ---------------------------------------------------------------------------

def test_morning_star_markiert_die_MITTLERE_kerze():
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(105.0, 105.2, 99.8, 100.0, tag=i))          # Koerper 5, Mitte 102,5
    kerzen.append(_k(99.5, 99.8, 98.9, 99.2, tag=i + 1))         # Koerper 0,3 (<= 1,5)
    kerzen.append(_k(100.0, 103.2, 99.9, 103.0, tag=i + 2))      # schliesst ueber 102,5

    t = _finde(erkennen(kerzen, i + 2), "Morning Star")
    assert t.richtung == "long"
    assert t.ungueltig_bei == 98.9          # Tief der MITTLEREN Kerze


def test_evening_star():
    kerzen = _vorlauf(1)
    i = len(kerzen)
    kerzen.append(_k(100.0, 105.2, 99.8, 105.0, tag=i))          # Mitte 102,5
    kerzen.append(_k(105.5, 106.1, 105.2, 105.8, tag=i + 1))     # kleiner Koerper
    kerzen.append(_k(105.0, 105.1, 101.8, 102.0, tag=i + 2))     # schliesst unter 102,5

    t = _finde(erkennen(kerzen, i + 2), "Evening Star")
    assert t.ungueltig_bei == 106.1


def test_morning_star_verlangt_einen_kleinen_mittelkoerper():
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(105.0, 105.2, 99.8, 100.0, tag=i))
    kerzen.append(_k(99.5, 103.2, 99.0, 103.0, tag=i + 1))       # Koerper 3,5 — zu gross
    kerzen.append(_k(103.0, 104.2, 102.9, 104.0, tag=i + 2))

    assert "Morning Star" not in _namen(erkennen(kerzen, i + 2))


def test_three_white_soldiers():
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(100.0, 102.2, 99.9, 102.0, tag=i))
    kerzen.append(_k(101.0, 103.7, 100.9, 103.5, tag=i + 1))
    kerzen.append(_k(102.5, 105.2, 102.4, 105.0, tag=i + 2))

    t = _finde(erkennen(kerzen, i + 2), "Three White Soldiers")
    assert t.ungueltig_bei == 99.9          # Tief der ERSTEN der drei


def test_three_white_soldiers_verlangt_eroeffnung_im_vorkoerper():
    """Eine Eroeffnungsluecke nach oben ist kein Soldat, sondern ein Gap."""
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(100.0, 102.2, 99.9, 102.0, tag=i))
    kerzen.append(_k(103.0, 105.2, 102.9, 105.0, tag=i + 1))     # oeffnet ueber 102
    kerzen.append(_k(105.5, 107.2, 105.4, 107.0, tag=i + 2))

    assert "Three White Soldiers" not in _namen(erkennen(kerzen, i + 2))


def test_three_black_crows():
    kerzen = _vorlauf(1)
    i = len(kerzen)
    kerzen.append(_k(105.0, 105.1, 102.8, 103.0, tag=i))
    kerzen.append(_k(104.0, 104.1, 101.3, 101.5, tag=i + 1))
    kerzen.append(_k(102.5, 102.6, 99.8, 100.0, tag=i + 2))

    t = _finde(erkennen(kerzen, i + 2), "Three Black Crows")
    assert t.ungueltig_bei == 105.1


# ---------------------------------------------------------------------------
# Einzelkerzen
# ---------------------------------------------------------------------------

def test_marubozu_hat_keine_dochte():
    kerzen = _vorlauf(1)
    i = len(kerzen)
    kerzen.append(_k(100.0, 102.0, 100.0, 102.0, tag=i))

    t = _finde(erkennen(kerzen, i), "Marubozu bullisch")
    assert t.richtung == "long"


def test_doji_traegt_keine_richtung_und_keine_marke():
    kerzen = _vorlauf(1)
    i = len(kerzen)
    kerzen.append(_k(100.0, 101.0, 99.0, 100.02, tag=i))

    t = _finde(erkennen(kerzen, i), "Doji")
    assert t.richtung == "keine"
    assert t.ungueltig_bei is None


def test_letzte_treffer_laesst_doji_weg():
    """Doji faellt auf rund 6 Prozent aller Zeilen und wuerde die Liste fuellen."""
    kerzen = _vorlauf(1)
    kerzen.append(_k(100.0, 101.0, 99.0, 100.02, tag=len(kerzen)))

    assert "Doji" not in {t.muster for t in letzte_treffer(kerzen)}
    assert "Doji" in {t.muster for t in letzte_treffer(kerzen, mit_doji=True)}


# ---------------------------------------------------------------------------
# Randfaelle
# ---------------------------------------------------------------------------

def test_kerze_ohne_spanne_ist_kein_muster():
    """Handelsstopp: Hoch gleich Tief. Sonst teilte jede Quote durch null."""
    kerzen = _vorlauf(1)
    i = len(kerzen)
    kerzen.append(_k(100.0, 100.0, 100.0, 100.0, tag=i))

    assert erkennen(kerzen, i) == []


def test_reihenanfang_bricht_nicht():
    """An Zeile 0 gibt es keine Vorkerze — kein Absturz, keine Mehrkerzenmuster."""
    kerzen = [_k(100.0, 102.0, 99.0, 101.0, tag=0)]
    treffer = erkennen(kerzen, 0)

    mehrkerzig = {m.name for m in MUSTER.values() if m.braucht > 0}
    assert not (_namen(treffer) & mehrkerzig)


@pytest.mark.parametrize("i", [-1, 99])
def test_index_ausserhalb_der_reihe(i):
    assert erkennen(_vorlauf(1), i) == []


def test_leere_reihe():
    assert alle_treffer([]) == []
    assert letzte_treffer([]) == []


# ---------------------------------------------------------------------------
# Umsatzverhaeltnis und Abstand
# ---------------------------------------------------------------------------

def test_umsatz_verhaeltnis_gegen_den_median():
    kerzen = [_k(100.0, 101.0, 99.0, 100.0, v=1000.0, tag=n) for n in range(10)]
    kerzen.append(_k(100.0, 101.0, 99.0, 100.0, v=2500.0, tag=10))

    assert umsatz_verhaeltnis(kerzen, 10) == 2.5


def test_umsatz_verhaeltnis_ohne_volumen():
    """Ein Handelsplatz ohne Volumenmeldung ist kein Tag ohne Umsatz."""
    kerzen = [Kerze(datetime(2026, 1, 1), 100.0, 101.0, 99.0, 100.0, None)
              for _ in range(10)]
    assert umsatz_verhaeltnis(kerzen, 9) is None


def test_abstand_prozent_zur_marke():
    kerzen = _vorlauf(-1)
    i = len(kerzen)
    kerzen.append(_k(102.0, 102.2, 99.8, 100.0, tag=i))
    kerzen.append(_k(99.5, 102.8, 99.0, 102.5, tag=i + 1))

    t = _finde(erkennen(kerzen, i + 1), "Bullisches Engulfing")
    # Marke 99,0 gegen Schluss 102,5 → −3,41 Prozent
    assert t.abstand_prozent == pytest.approx(-3.41, abs=0.01)


# ---------------------------------------------------------------------------
# Eingang aus dem DataFrame
# ---------------------------------------------------------------------------

def test_dataframe_wird_gelesen():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        {"Open": [100.0, 101.0], "High": [102.0, 103.0],
         "Low": [99.0, 100.0], "Close": [101.0, 102.0],
         "Volume": [1000, 1200]},
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )
    kerzen = kerzen_aus_dataframe(df)

    assert len(kerzen) == 2
    assert kerzen[0].offen == 100.0 and kerzen[1].schluss == 102.0
    assert kerzen[0].volumen == 1000


def test_dataframe_zeile_mit_nan_faellt_heraus():
    """Eine Kerze ohne Hoch ist keine Kerze mit Hoch 0."""
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame(
        {"Open": [100.0, 101.0], "High": [102.0, float("nan")],
         "Low": [99.0, 100.0], "Close": [101.0, 102.0]},
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )
    assert len(kerzen_aus_dataframe(df)) == 1


def test_dataframe_ohne_ohlc_spalten():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"Kurs": [100.0]}, index=pd.to_datetime(["2026-01-02"]))
    assert kerzen_aus_dataframe(df) == []


def test_dataframe_leer_oder_none():
    assert kerzen_aus_dataframe(None) == []


# ---------------------------------------------------------------------------
# Vollstaendigkeit — jedes definierte Muster muss erreichbar sein
# ---------------------------------------------------------------------------

def test_jedes_muster_traegt_richtung_und_marke():
    for schluessel, m in MUSTER.items():
        assert m.richtung in ("long", "short", "keine"), schluessel
        assert m.braucht >= 0, schluessel
        assert m.vortrend_noetig in (-1, 0, 1), schluessel


def test_sechzehn_gerichtete_muster_plus_doji():
    """Die Liste aus KERZENMUSTER.md Paragraph 6 — 16 gerichtete, ein Kontrollmuster."""
    gerichtet = [m for m in MUSTER.values() if m.richtung != "keine"]
    ohne_richtung = [m for m in MUSTER.values() if m.richtung == "keine"]

    assert len(gerichtet) == 16
    assert len(ohne_richtung) == 1
