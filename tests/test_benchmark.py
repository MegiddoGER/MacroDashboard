"""
tests/test_benchmark.py — Marktrendite und Überrendite (P1-04).

Geprüft wird, was eine Überrendite unbrauchbar machen würde: ein falsch
zugeordneter Index (die Differenz wäre dann eine Währungsbewegung), eine
verwechselte Richtung (bei VERKAUF ist ein Rückstand des Titels der Treffer)
und eine Abdeckungszahl, die fehlenden Benchmark und fehlendes Richtungssignal
zusammenwirft.
"""

from datetime import datetime

import pandas as pd
import pytest

from snapshot_engine.auswertung.basis import (
    MARKT_NULLHYPOTHESE, MIN_VORSPRUNG_PP, STATUS_OK, STATUS_ZU_WENIG_DATEN,
    mit_ueberrendite,
)
from snapshot_engine.benchmark import (
    BENCHMARK_JE_SUFFIX, benchmark_fuer, benoetigte_benchmarks,
    erfolg_gegen_benchmark, rendite, ueberrendite,
)


# ---------------------------------------------------------------------------
# Index je Handelsplatz
# ---------------------------------------------------------------------------

def test_ticker_ohne_suffix_ist_us():
    assert benchmark_fuer("AAPL") == "^GSPC"


@pytest.mark.parametrize("ticker, index", [
    ("SAP.DE", "^GDAXI"),
    ("SIE.F", "^GDAXI"),
    ("NESN.SW", "^SSMI"),
    ("MC.PA", "^FCHI"),
    ("005930.KS", "^KS11"),
])
def test_bekannte_handelsplaetze(ticker, index):
    assert benchmark_fuer(ticker) == index


def test_suffix_wird_unabhaengig_von_der_schreibweise_erkannt():
    assert benchmark_fuer("sap.de") == benchmark_fuer("SAP.DE")


@pytest.mark.parametrize("ticker", ["VOD.L", "SHOP.TO", "BHP.AX", ""])
def test_unbekannter_markt_bekommt_keinen_index(ticker):
    """Lieber kein Vergleichswert als ein falscher.

    Ein Index in fremder Währung erzeugt eine Überrendite, die in Wahrheit eine
    Wechselkursbewegung ist — und die fällt später niemandem mehr auf.
    """
    assert benchmark_fuer(ticker) is None


def test_punkt_im_namen_gilt_als_unbekannter_markt():
    """BRK.B trägt eine Gattung im Suffix, keinen Handelsplatz — nicht raten."""
    assert benchmark_fuer("BRK.B") is None


def test_benoetigte_benchmarks_ist_entdoppelt_und_ohne_luecken():
    gebraucht = benoetigte_benchmarks(["AAPL", "MSFT", "SAP.DE", "VOD.L"])
    assert gebraucht == ["^GDAXI", "^GSPC"]


def test_us_ist_der_schluessel_ohne_suffix():
    assert BENCHMARK_JE_SUFFIX[""] == "^GSPC"


# ---------------------------------------------------------------------------
# Indexrendite über ein Fenster
# ---------------------------------------------------------------------------

def _reihe(kurse):
    index = pd.date_range("2025-01-01", periods=len(kurse), freq="D")
    return pd.DataFrame({"Close": kurse}, index=index)


def test_rendite_ueber_das_fenster():
    hist = _reihe([100.0 + i for i in range(10)])
    wert = rendite(hist, datetime(2025, 1, 1), datetime(2025, 1, 6))
    assert wert == pytest.approx(5.0)


def test_fallender_index_ergibt_negative_rendite():
    hist = _reihe([100.0 - i for i in range(10)])
    wert = rendite(hist, datetime(2025, 1, 1), datetime(2025, 1, 6))
    assert wert == pytest.approx(-5.0)


def test_stichtag_nach_dem_letzten_bar_ist_nicht_bewertbar():
    hist = _reihe([100.0] * 5)
    assert rendite(hist, datetime(2025, 1, 1), datetime(2025, 6, 1)) is None


def test_leere_reihe_ergibt_keine_rendite():
    assert rendite(None, datetime(2025, 1, 1), datetime(2025, 1, 6)) is None
    assert rendite(pd.DataFrame(), datetime(2025, 1, 1), datetime(2025, 1, 6)) is None


# ---------------------------------------------------------------------------
# Überrendite
# ---------------------------------------------------------------------------

def test_ueberrendite_ist_die_differenz_in_prozentpunkten():
    assert ueberrendite(8.0, 3.0) == pytest.approx(5.0)
    assert ueberrendite(2.0, 8.0) == pytest.approx(-6.0)


@pytest.mark.parametrize("titel, markt", [(None, 3.0), (8.0, None), (None, None)])
def test_ohne_beide_werte_keine_ueberrendite(titel, markt):
    assert ueberrendite(titel, markt) is None


# ---------------------------------------------------------------------------
# Erfolg gegen den Markt statt gegen null
# ---------------------------------------------------------------------------

def test_kauf_der_den_markt_schlaegt_ist_ein_treffer():
    assert erfolg_gegen_benchmark("KAUF", 8.0, 3.0, MIN_VORSPRUNG_PP) is True


def test_kauf_im_plus_aber_hinter_dem_markt_ist_kein_treffer():
    """Der eigentliche Punkt von P1-04: +2 % in einem Monat, in dem der Index
    8 % zulegte, war keine gute Empfehlung — absolut zählt es trotzdem."""
    assert erfolg_gegen_benchmark("KAUF", 2.0, 8.0, MIN_VORSPRUNG_PP) is False


def test_verkauf_ist_spiegelbildlich():
    # Titel bleibt hinter dem Markt zurück → das VERKAUF-Signal lag richtig.
    assert erfolg_gegen_benchmark("VERKAUF", -5.0, 2.0, MIN_VORSPRUNG_PP) is True
    assert erfolg_gegen_benchmark("VERKAUF", 9.0, 2.0, MIN_VORSPRUNG_PP) is False


def test_verkauf_im_minus_aber_besser_als_der_markt_ist_kein_treffer():
    """Ein Titel, der nur 2 % verliert, während der Index 8 % einbricht, hat
    den Markt geschlagen — das VERKAUF-Signal lag also falsch."""
    assert erfolg_gegen_benchmark("VERKAUF", -2.0, -8.0, MIN_VORSPRUNG_PP) is False


def test_neutral_wird_nicht_bewertet():
    assert erfolg_gegen_benchmark("NEUTRAL", 8.0, 3.0, MIN_VORSPRUNG_PP) is None


def test_vorsprung_unter_der_schwelle_gilt_als_rauschen():
    knapp = MIN_VORSPRUNG_PP / 2
    assert erfolg_gegen_benchmark("KAUF", 3.0 + knapp, 3.0, MIN_VORSPRUNG_PP) is None


def test_ohne_vergleichswert_keine_bewertung():
    assert erfolg_gegen_benchmark("KAUF", 8.0, None, MIN_VORSPRUNG_PP) is None


# ---------------------------------------------------------------------------
# Kennzahlenzeile: mit_ueberrendite
# ---------------------------------------------------------------------------

def _zeile(n=100):
    return {"n": n}


def test_richtung_wird_beruecksichtigt():
    """Ein SHORT auf einen Titel, der hinter dem Markt bleibt, ist ein Treffer —
    obwohl seine rohe Überrendite negativ ist."""
    k = mit_ueberrendite(_zeile(60), [-4.0] * 60, [-1] * 60)
    assert k["markt_trefferquote"] == 100.0
    assert k["ueberrendite_mittel_pp"] == pytest.approx(4.0)


def test_long_und_short_sind_symmetrisch():
    long = mit_ueberrendite(_zeile(60), [3.0] * 60, [1] * 60)
    short = mit_ueberrendite(_zeile(60), [-3.0] * 60, [-1] * 60)
    assert long["markt_trefferquote"] == short["markt_trefferquote"]
    assert long["ueberrendite_mittel_pp"] == short["ueberrendite_mittel_pp"]


def test_abdeckung_misst_nur_die_gerichteten_beobachtungen():
    """NEUTRAL ist gegen den Markt nicht bewertbar und darf die Abdeckung nicht
    drücken — sonst sähe ein vollständiger Bestand nach einer Lücke aus."""
    ueberrenditen = [2.0] * 40 + [None] * 60      # 60 NEUTRAL-Zeilen
    richtungen = [1] * 40 + [None] * 60
    k = mit_ueberrendite(_zeile(100), ueberrenditen, richtungen)
    assert k["ueberrendite_n"] == 40
    assert k["ueberrendite_abdeckung_pct"] == 100.0


def test_fehlender_benchmark_drueckt_die_abdeckung():
    ueberrenditen = [2.0] * 30 + [None] * 30
    richtungen = [1] * 60
    k = mit_ueberrendite(_zeile(60), ueberrenditen, richtungen)
    assert k["ueberrendite_n"] == 30
    assert k["ueberrendite_abdeckung_pct"] == 50.0


def test_zu_kleine_stichprobe_liefert_keine_quote():
    k = mit_ueberrendite(_zeile(5), [2.0] * 5, [1] * 5)
    assert k["ueberrendite_status"] == STATUS_ZU_WENIG_DATEN
    assert k["markt_trefferquote"] is None
    assert k["markt_vorsprung_pp"] is None


def test_ausreichende_stichprobe_wird_ausgewiesen():
    k = mit_ueberrendite(_zeile(60), [2.0] * 60, [1] * 60)
    assert k["ueberrendite_status"] == STATUS_OK


def test_vorsprung_wird_gegen_fuenfzig_gemessen_nicht_gegen_die_basisrate():
    """Der Index hat die Marktbewegung schon je Beobachtung herausgerechnet;
    die Nullhypothese ist damit der Münzwurf."""
    assert MARKT_NULLHYPOTHESE == 50.0
    haelfte = [3.0] * 30 + [-3.0] * 30
    k = mit_ueberrendite(_zeile(60), haelfte, [1] * 60)
    assert k["markt_trefferquote"] == 50.0
    assert k["markt_vorsprung_pp"] == 0.0
    assert k["markt_signifikant"] is False


def test_knappe_ueberrenditen_zaehlen_im_mittel_aber_nicht_in_der_quote():
    """Dieselbe Trennung wie zwischen avg_return und trefferquote."""
    knapp = MIN_VORSPRUNG_PP / 2
    werte = [5.0] * 40 + [knapp] * 20
    k = mit_ueberrendite(_zeile(60), werte, [1] * 60)
    assert k["markt_trefferquote"] == 100.0          # die 20 knappen zählen nicht
    assert k["ueberrendite_mittel_pp"] < 5.0         # im Mittel aber schon


def test_ohne_jede_richtung_bleibt_alles_leer():
    k = mit_ueberrendite(_zeile(50), [None] * 50, [None] * 50)
    assert k["ueberrendite_n"] == 0
    assert k["ueberrendite_abdeckung_pct"] is None
    assert k["markt_trefferquote"] is None


# ---------------------------------------------------------------------------
# Mindeststichprobe folgt der Aufrufstelle (P1-04b)
# ---------------------------------------------------------------------------

def test_minimum_folgt_der_aufrufstelle():
    """Die Marktquote darf nicht unter einer anderen Schwelle erscheinen als
    die absolute Quote neben ihr — sonst steht in einer Zeile eine Zahl und in
    der Nachbarspalte ein Strich, ohne dass die Datenlage sich unterscheidet."""
    streng = mit_ueberrendite(_zeile(60), [2.0] * 60, [1] * 60, minimum=200)
    assert streng["ueberrendite_status"] == STATUS_ZU_WENIG_DATEN
    assert streng["markt_trefferquote"] is None

    locker = mit_ueberrendite(_zeile(60), [2.0] * 60, [1] * 60, minimum=10)
    assert locker["ueberrendite_status"] == STATUS_OK
    assert locker["markt_trefferquote"] == 100.0


# ---------------------------------------------------------------------------
# Gate-Gruppen tragen die Marktzahlen mit (P1-04b)
# ---------------------------------------------------------------------------

def test_gate_gruppe_wird_auch_gegen_den_markt_bewertet():
    from snapshot_engine.auswertung.gate import _gruppe_bewerten
    # 40 Beobachtungen, die den Index jeweils um 3 pp schlagen.
    paare = [(8.0, 5.0)] * 40
    g = _gruppe_bewerten(paare, basisrate=55.0, horizont=30, minimum=10)
    assert g["trefferquote"] == 100.0          # absolut: alle im Plus
    assert g["markt_trefferquote"] == 100.0    # und alle vor dem Index
    assert g["ueberrendite_mittel_pp"] == pytest.approx(3.0)


def test_leere_gate_gruppe_faellt_nicht_um():
    from snapshot_engine.auswertung.gate import _gruppe_bewerten
    g = _gruppe_bewerten([], basisrate=55.0, horizont=30, minimum=10)
    assert g["n"] == 0
    assert g["trefferquote"] is None
    assert g["markt_trefferquote"] is None
