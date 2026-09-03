"""
tests/test_volumen.py — Echter Umsatz als Eingang (BC-01).

Die erste Messung von Volumen in diesem Projekt. Was heute „volume" heisst,
ist dreimal Momentum (VWMA, OBV-Slope, POC), weshalb jeder bisherige
Nullbefund zu „Volumen" eine Aussage über Momentum unter falscher Flagge war.

Geprüft wird, was einen Befund still wertlos machen würde:

  * ein Fenster, das über den Stichtag hinausreicht — Look-ahead, und der
    Effekt sähe dann grossartig aus,
  * ein Bezugsmedian, der den Ausreisser enthält, den er bewerten soll,
  * None und 0 verwechselt: ein Handelsplatz ohne Volumenmeldung ist kein
    Tag ohne Umsatz. Genau diese Trennung ist der Kern von BC-04.
"""

from datetime import datetime, timedelta

import pytest

from services.volumen import (
    AUSBRUCH_PCT, FENSTER_KURZ, MIN_TAGE, ausbruchs_bestaetigung,
    eroeffnungsluecke, kennzahlen_am, relatives_volumen, tagesspanne,
    volumen_trend,
)


def _tag(i: int, schluss: float = 100.0, volumen: float | None = 1000.0,
         hoch: float | None = None, tief: float | None = None,
         eroeffnung: float | None = None) -> tuple:
    """(datum, eroeffnung, hoch, tief, schluss, volumen)"""
    return (datetime(2024, 1, 1) + timedelta(days=i),
            schluss if eroeffnung is None else eroeffnung,
            schluss + 1 if hoch is None else hoch,
            schluss - 1 if tief is None else tief,
            schluss, volumen)


def _ruhig(n: int = 25) -> list[tuple]:
    return [_tag(i) for i in range(n)]


# ---------------------------------------------------------------------------
# Look-ahead
# ---------------------------------------------------------------------------

def test_das_fenster_endet_am_stichtag():
    """Ein spaeterer Ausbruch darf am Stichtag nicht sichtbar sein.

    Der teuerste Fehler dieser Modulklasse: er macht jede Kennzahl
    hervorragend und ist an den Zahlen allein nicht zu erkennen.
    """
    reihe = _ruhig(20) + [_tag(20, schluss=105.0, volumen=5000.0)]
    daten = [z[0] for z in reihe]

    vorher = kennzahlen_am(reihe, datetime(2024, 1, 15), daten)
    am_tag = kennzahlen_am(reihe, reihe[-1][0], daten)

    assert vorher["Relatives Volumen"] == pytest.approx(1.0)
    assert am_tag["Relatives Volumen"] == pytest.approx(5.0)


def test_der_stichtag_selbst_gehoert_dazu():
    """Die Gegenprobe: sein Volumen ist zum Handelsschluss bekannt.

    Ein ausschliessendes Fenster waere kein Schutz vor Look-ahead, sondern
    ein Off-by-one — dieselbe Festlegung wie in stetige_indikatoren.py.
    """
    reihe = _ruhig(20) + [_tag(20, volumen=3000.0)]
    daten = [z[0] for z in reihe]
    assert kennzahlen_am(reihe, reihe[-1][0], daten)["Relatives Volumen"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Der Bezugsmedian
# ---------------------------------------------------------------------------

def test_der_ausreisser_hebt_seine_eigene_bezugsgroesse_nicht_an():
    """Der Stichtag bleibt aus seinem Vergleichsmedian heraus.

    Sonst verglichen sich Spitzen teilweise mit sich selbst, und je groesser
    der Ausschlag, desto kleiner erschiene er.
    """
    reihe = _ruhig(20) + [_tag(20, volumen=9000.0)]
    assert relatives_volumen(reihe) == pytest.approx(9.0)


def test_median_statt_mittelwert():
    """Ein einzelner Verfallstag darf die Normalitaet nicht wochenlang heben."""
    reihe = [_tag(i) for i in range(20)]
    reihe[5] = _tag(5, volumen=100_000.0)          # ein Ausreisser
    reihe.append(_tag(20, volumen=2000.0))
    # Mittelwert waere ~6.000 und ergaebe 0,33 — der Median bleibt bei 1.000.
    assert relatives_volumen(reihe) == pytest.approx(2.0)


def test_zu_kurze_reihe_liefert_nichts():
    """Ein Median aus drei Tagen beschreibt die Luecke, nicht den Titel."""
    assert relatives_volumen(_ruhig(MIN_TAGE - 1)) is None
    assert relatives_volumen([]) is None


# ---------------------------------------------------------------------------
# None ist nicht null
# ---------------------------------------------------------------------------

def test_fehlendes_volumen_ist_kein_umsatz_von_null():
    """Die Trennung aus BC-04, hier an der Quelle.

    Ein Handelsplatz ohne Volumenmeldung darf keine Kennzahl erzeugen — sonst
    entstuende eine Beobachtung aus einer Luecke.
    """
    reihe = [_tag(i, volumen=None) for i in range(25)]
    k = kennzahlen_am(reihe, reihe[-1][0])
    assert k["Relatives Volumen"] is None
    assert k["Volumen-Trend (20/60)"] is None
    assert k["Ausbruchs-Bestätigung"] is None
    # Spanne und Luecke haengen nicht am Volumen und bleiben berechenbar.
    assert k["Tagesspanne"] is not None


def test_median_volumen_null_liefert_keine_teilung():
    reihe = [_tag(i, volumen=0.0) for i in range(25)]
    assert relatives_volumen(reihe) is None


# ---------------------------------------------------------------------------
# Ausbruchs-Bestaetigung
# ---------------------------------------------------------------------------

def test_ausbruch_mit_umsatz_wird_erkannt():
    """Der Lehrbuchfall, in dieser Engine nie gemessen."""
    reihe = _ruhig(20) + [_tag(20, schluss=100.0 * (1 + AUSBRUCH_PCT / 100 + 0.01),
                               volumen=4000.0)]
    assert ausbruchs_bestaetigung(reihe) == pytest.approx(4.0, abs=0.2)


def test_ohne_bewegungstag_gibt_es_keine_bestaetigung():
    """None heisst "keine Aussage moeglich", nicht "keine Bestaetigung".

    Beides zu vermischen waere der Fehler aus §2h in neuer Form: eine 0 waere
    ein Messwert, den es nie gab.
    """
    assert ausbruchs_bestaetigung(_ruhig(25)) is None


# ---------------------------------------------------------------------------
# Spanne und Luecke
# ---------------------------------------------------------------------------

def test_tagesspanne_ist_prozentual():
    reihe = [_tag(i, schluss=100.0, hoch=103.0, tief=100.0) for i in range(20)]
    assert tagesspanne(reihe) == pytest.approx(3.0)


def test_eroeffnungsluecke_misst_den_betrag():
    """Die Richtung ist hier nicht die Frage — die Groesse der Nachtbewegung.

    Eine vorzeichenbehaftete Fassung mittelte sich ueber zwanzig Tage
    gegen null und maesse damit nichts.
    """
    reihe = [_tag(i, schluss=100.0, eroeffnung=102.0 if i % 2 else 98.0)
             for i in range(20)]
    assert eroeffnungsluecke(reihe) == pytest.approx(2.0)


def test_volumen_trend_vergleicht_kurz_gegen_lang():
    kurz = [_tag(i, volumen=2000.0) for i in range(20)]
    lang = [_tag(i, volumen=1000.0) for i in range(60)]
    assert volumen_trend(kurz, lang) == pytest.approx(2.0)
