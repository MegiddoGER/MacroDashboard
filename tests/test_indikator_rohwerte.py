"""
tests/test_indikator_rohwerte.py — Der Schreibpfad nach BC-04 (Schritt 3+4).

Zwei Änderungen werden hier festgehalten, und beide sind Aufzeichnungs-, keine
Bewertungsfragen — der Score bleibt unberührt (SCORE_VERSION 2.2.0).

**1. Die Rohgröße entscheidet, ob eine Beobachtung existiert.**
Bisher stand im Schreibpfad `if richtung is None: continue`, und das warf zwei
Fälle zusammen: "nicht berechenbar" (kein RSI mangels Historie) und
"berechenbar, aber neutral" (RSI 47). Der zweite ist eine vollwertige
Beobachtung. Weil er verworfen wurde, tragen von 274.840 Snapshots nur 30.216
eine RSI-Zeile — der Mittelbereich existiert im Bestand nicht, und die Frage
nach dem Verlauf des RSI war deshalb nie beantwortbar.

**2. OBV, VWMA und POC zeichneten ein Verkaufssignal auf, wo nichts war.**
`_score_volume` initialisiert die drei Bool-Flags mit False und lässt sie dort
stehen, wenn der Indikator gar nicht berechenbar ist. `_aus_bool` las das als
bearisch — das Scoring hatte an derselben Stelle weder `cat_scores` noch
`cat_max` erhöht. Die Richtung kommt jetzt aus dem Vorzeichen der Rohgröße.
"""

import math

import pytest

from snapshot_engine.models import AnalyseSnapshot, Granularitaet
from snapshot_engine.snapshot_service import (
    _SIGNAL_INDIKATOREN, _aus_rohwert, _rohwert, _signaltext,
    indikatoren_schreiben,
)


class _Sammler:
    """Minimaler Session-Ersatz: `indikatoren_schreiben` ruft nur `add`."""

    def __init__(self):
        self.zeilen = []

    def add(self, obj):
        self.zeilen.append(obj)


class _Ergebnis:
    def __init__(self, signals=None, checklist=None):
        self.signals = signals or {}
        self.checklist = checklist or []


def _schreiben(signals: dict, checklist=None):
    db = _Sammler()
    # Transienter Snapshot: die Beziehung braucht eine echte ORM-Instanz,
    # geschrieben wird nichts.
    indikatoren_schreiben(db, AnalyseSnapshot(), _Ergebnis(signals, checklist))
    return {z.indikator_name: z for z in db.zeilen}


# ---------------------------------------------------------------------------
# Rohwert-Umwandlung
# ---------------------------------------------------------------------------

def test_bool_ist_keine_rohgroesse():
    """`True` als 1.0 zu lesen wäre genau die Rundung, um die es geht."""
    assert _rohwert({"x": True}, "x") is None
    assert _rohwert({"x": False}, "x") is None


def test_nan_zaehlt_als_nicht_gemessen():
    """NaN ist kein Messwert null — sonst entstünde eine Beobachtung aus nichts."""
    assert _rohwert({"x": float("nan")}, "x") is None


def test_null_ist_ein_messwert():
    """Die klare Gegenprobe zu NaN: 0.0 ist gemessen und muss durchkommen."""
    assert _rohwert({"x": 0.0}, "x") == 0.0


def test_fehlender_schluessel_und_kein_schluessel():
    assert _rohwert({}, "x") is None
    assert _rohwert({"x": 1.0}, None) is None


# ---------------------------------------------------------------------------
# Richtung aus dem Vorzeichen
# ---------------------------------------------------------------------------

def test_richtung_folgt_dem_vorzeichen():
    assert _aus_rohwert({"x": 2.5}, "x") == 1
    assert _aus_rohwert({"x": -2.5}, "x") == -1


def test_ohne_rohgroesse_gibt_es_keine_richtung():
    """Der Kern der Korrektur: nicht berechenbar ist nicht bearisch."""
    assert _aus_rohwert({}, "x") is None
    assert _aus_rohwert({"x": None}, "x") is None


def test_exakte_null_folgt_der_scoring_logik():
    """`_score_volume` zählt die Null im else-Zweig als bearisch — außer beim POC.

    Diese Asymmetrie ist nicht schön, aber sie ist die bestehende Bewertung.
    Sie hier stillschweigend zu vereinheitlichen wäre eine Score-Änderung
    ohne Beleg.
    """
    assert _aus_rohwert({"x": 0.0}, "x") == -1
    assert _aus_rohwert({"x": 0.0}, "x", null_bearisch=False) is None


def test_signaltext_kennt_neutral():
    assert _signaltext(None) == "neutral"
    assert _signaltext(1) == "bullisch"
    assert _signaltext(-1) == "bearisch"


# ---------------------------------------------------------------------------
# Der neutrale RSI — die 89 Prozent, die es nie in den Bestand geschafft haben
# ---------------------------------------------------------------------------

def test_neutraler_rsi_wird_jetzt_aufgezeichnet():
    """RSI 47 ist eine Beobachtung, keine fehlende Messung.

    Vorher: keine Zeile, weil `_rsi_richtung` None liefert. Damit fehlten von
    274.840 Snapshots rund 89 % der RSI-Werte, und der Verlauf über den
    mittleren Bereich war nie im Bestand.
    """
    zeilen = _schreiben({"rsi_val": 47.0})

    assert "RSI (14)" in zeilen
    zeile = zeilen["RSI (14)"]
    assert zeile.wert_numeric == 47.0
    assert zeile.beitrag_numeric == 0.0
    assert zeile.signal_text == "neutral"


def test_neutrale_zeile_bleibt_aus_den_leaderboards_heraus():
    """Die bestehenden Auswertungen filtern `beitrag_numeric != 0`.

    Deshalb 0.0 und nicht NULL: die neutrale Zeile fällt dort von selbst
    heraus, und NULL wäre nicht von den Info-Zeilen zu unterscheiden.
    """
    zeile = _schreiben({"rsi_val": 47.0})["RSI (14)"]
    assert zeile.beitrag_numeric == 0.0
    assert zeile.beitrag_numeric is not None


def test_nicht_berechenbarer_rsi_erzeugt_weiterhin_keine_zeile():
    """Die Gegenprobe. Ohne Messwert gibt es nichts aufzuzeichnen."""
    assert "RSI (14)" not in _schreiben({})


def test_extremer_rsi_behaelt_seinen_beitrag():
    """Die bisherige Aufzeichnung darf sich nicht verändern."""
    zeilen = _schreiben({"rsi_val": 22.0, "rsi_oversold": True})
    assert zeilen["RSI (14)"].beitrag_numeric == 1.0
    assert zeilen["RSI (14)"].wert_numeric == 22.0
    assert zeilen["RSI (14)"].signal_text == "bullisch"


# ---------------------------------------------------------------------------
# Die stille Fehlaufzeichnung bei OBV, VWMA und POC
# ---------------------------------------------------------------------------

def test_nicht_berechenbarer_vwma_ist_kein_verkaufssignal():
    """Der eigentliche Fehler: False hiess "bearisch", nicht "keine Aussage".

    `_score_volume` setzt `vwap_bullish = False` auch dann, wenn gar kein
    VWAP vorliegt (kein Volumen gemeldet), und zaehlt an dieser Stelle weder
    cat_scores noch cat_max. Der Snapshot trug trotzdem eine bearische Zeile.
    """
    zeilen = _schreiben({"vwap_bullish": False, "vwma_abstand_pct": None})
    assert "VWMA (20T)" not in zeilen


def test_berechenbarer_vwma_behaelt_seine_richtung():
    zeilen = _schreiben({"vwap_bullish": True, "vwma_abstand_pct": 3.2})
    assert zeilen["VWMA (20T)"].beitrag_numeric == 1.0
    assert zeilen["VWMA (20T)"].wert_numeric == pytest.approx(3.2)

    zeilen = _schreiben({"vwap_bullish": False, "vwma_abstand_pct": -1.4})
    assert zeilen["VWMA (20T)"].beitrag_numeric == -1.0


def test_nicht_berechenbarer_obv_trend_erzeugt_keine_zeile():
    """Unter 20 Stützstellen liefert `calc_order_flow` keine Steigung."""
    assert "OBV Trend" not in _schreiben({"obv_bullish": False, "obv_slope": None})


def test_kurs_exakt_auf_dem_poc_ist_neutral_und_wird_aufgezeichnet():
    """Weder bullisch noch bearisch — aber gemessen, also eine Beobachtung."""
    zeilen = _schreiben({"poc_bullish": False, "poc_abstand_pct": 0.0})
    assert zeilen["Volumen-Cluster (POC)"].beitrag_numeric == 0.0
    assert zeilen["Volumen-Cluster (POC)"].wert_numeric == 0.0


# ---------------------------------------------------------------------------
# Trend: der Fall, den §2h gemessen hat
# ---------------------------------------------------------------------------

def test_trend_traegt_den_abstand_statt_nur_das_vorzeichen():
    """Zwei Titel über der SMA 200, aber nicht derselbe Eingang.

    Genau diese Unterscheidung fehlte im Bestand — und der Kontrollversuch
    in §2h hat gemessen, was sie wert ist: 2,0 pp Spread mit monotonem
    Verlauf gegen nichts.
    """
    knapp = _schreiben({
        "trend_macro_bullish": True, "sma200_val": 100.0,
        "trend_sma200_abstand_pct": 0.5,
    })["Trend (SMA 200)"]
    weit = _schreiben({
        "trend_macro_bullish": True, "sma200_val": 100.0,
        "trend_sma200_abstand_pct": 45.0,
    })["Trend (SMA 200)"]

    assert knapp.beitrag_numeric == weit.beitrag_numeric == 1.0
    assert knapp.wert_numeric == 0.5
    assert weit.wert_numeric == 45.0


def test_macd_bleibt_info_und_traegt_trotzdem_seinen_wert():
    """MACD zählt bewusst nicht im Score (Redundanz mit dem SMA-Cross).

    Das ist eine Gewichtungsentscheidung, kein Grund, die Größe nicht
    aufzuzeichnen.
    """
    zeile = _schreiben({
        "macd_bullish": True, "macd_histogramm_pct": 0.42,
    })["MACD"]
    assert zeile.granularitaet == Granularitaet.INFO
    assert zeile.wert_numeric == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Vollständigkeit
# ---------------------------------------------------------------------------

def test_jedes_instrument_hat_eine_rohgroesse():
    """Der Zweck des ganzen Vorhabens, als Test.

    Bliebe ein Eintrag ohne Rohgrößen-Schlüssel, wäre nach dem neuen
    Durchlauf genau dieses Instrument wieder nur als Vorzeichen im Bestand —
    und der Mangel fiele erst bei der Auswertung auf, also nach Stunden.
    """
    ohne = [eintrag[0] for eintrag in _SIGNAL_INDIKATOREN if not eintrag[4]]
    assert ohne == []


def test_alle_eintraege_haben_die_erwartete_stelligkeit():
    assert all(len(eintrag) == 6 for eintrag in _SIGNAL_INDIKATOREN)
