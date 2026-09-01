"""
tests/test_marktregime.py — Marktregime als Bedingung (P2-03, §2i).

Geprüft wird das, was ein Regime-Gate still wertlos machen würde: eine
Schwelle, die aus dem Gesamtzeitraum stammt und damit die Zukunft mitbenutzt;
ein Zustand, der am Stichtag noch nicht feststand; und eine Auswertung, die
beide Regime gegen dieselbe Marktbasis rechnet, obwohl sich die Basis zwischen
ihnen um mehr als jeder gemessene Signalvorsprung unterscheidet.
"""

from datetime import datetime, timedelta

import pytest

from services.marktregime import (
    AB, AUF, HOCH, MA_FENSTER, MIN_ABSTAND_TAGE, NIEDRIG, VOLA_FENSTER,
    VOLA_VERGLEICH, regime_am, regime_reihe,
)
from snapshot_engine.auswertung.regime import REGIME_ARTEN, signal_nach_regime


BEGINN = datetime(2016, 1, 4)


def _rahmen(kurse: list[float]):
    """Minimaler Ersatz für eine Indexreihe: ein DataFrame mit Close."""
    import pandas as pd
    index = pd.DatetimeIndex([BEGINN + timedelta(days=i) for i in range(len(kurse))])
    return pd.DataFrame({"Close": kurse}, index=index)


def _ruhig(n: int) -> list[float]:
    """Gleichmäßiger Anstieg — Volatilität nahe null."""
    return [100.0 * (1.0002 ** i) for i in range(n)]


def _unruhig(n: int, ausschlag: float = 0.03) -> list[float]:
    """Abwechselnd auf und ab um denselben Betrag."""
    kurse = [100.0]
    for i in range(1, n):
        kurse.append(kurse[-1] * (1 + ausschlag if i % 2 else 1 - ausschlag))
    return kurse


# ---------------------------------------------------------------------------
# Volatilität und Fensterbesetzung
# ---------------------------------------------------------------------------

def test_unruhige_reihe_hat_hoehere_vola_als_ruhige():
    n = VOLA_FENSTER * 3
    ruhig = [e["vola"] for e in regime_reihe(_rahmen(_ruhig(n))) if e["vola"] is not None]
    unruhig = [e["vola"] for e in regime_reihe(_rahmen(_unruhig(n))) if e["vola"] is not None]
    assert ruhig and unruhig
    assert max(ruhig) < min(unruhig)


def test_am_anfang_gibt_es_noch_kein_regime():
    """Der nachlaufende Median braucht zwei Jahre Historie. Ihn vorher zu
    bilden hieße, aus einer halben Stichprobe zu raten — und der Zustand sähe
    hinterher genauso aus wie ein echter."""
    reihe = regime_reihe(_rahmen(_ruhig(VOLA_FENSTER * 2)))
    assert all(e["vola_regime"] is None for e in reihe)


def test_ohne_langes_fenster_keine_richtung():
    reihe = regime_reihe(_rahmen(_ruhig(MA_FENSTER - 5)))
    assert all(e["ueber_ma"] is None for e in reihe)


def test_steigende_reihe_steht_ueber_ihrem_mittel():
    reihe = regime_reihe(_rahmen(_ruhig(MA_FENSTER * 2)))
    letzte = reihe[-1]
    assert letzte["ueber_ma"] is True
    assert letzte["richtungs_regime"] == AUF


def test_fallende_reihe_steht_unter_ihrem_mittel():
    fallend = [100.0 * (0.9998 ** i) for i in range(MA_FENSTER * 2)]
    letzte = regime_reihe(_rahmen(fallend))[-1]
    assert letzte["ueber_ma"] is False
    assert letzte["richtungs_regime"] == AB


@pytest.mark.parametrize("kurse", [[], [100.0]])
def test_zu_kurze_reihe_liefert_nichts(kurse):
    assert regime_reihe(_rahmen(kurse)) == []


def test_reihe_ohne_close_liefert_nichts():
    import pandas as pd
    leer = pd.DataFrame({"Open": [1.0, 2.0]},
                        index=pd.DatetimeIndex([BEGINN, BEGINN + timedelta(days=1)]))
    assert regime_reihe(leer) == []


# ---------------------------------------------------------------------------
# Die Schwelle kommt aus der Vergangenheit, nicht aus dem Gesamtzeitraum
# ---------------------------------------------------------------------------

def test_die_schwelle_benutzt_nur_vergangenheit():
    """Der Kern der Punkt-in-Zeit-Sicherung.

    Eine Reihe, die erst ruhig und dann unruhig wird, muss im ruhigen Teil
    dieselben Zustände liefern wie eine Reihe, die nur aus dem ruhigen Teil
    besteht. Läge die Schwelle über dem Gesamtzeitraum, würde die spätere
    Unruhe den früheren Median anheben — und rückwirkend entscheiden, was
    damals als hohe Volatilität galt.
    """
    n = VOLA_VERGLEICH + VOLA_FENSTER * 2
    ruhig = _ruhig(n)
    gemischt = ruhig + _unruhig(300)

    nur_ruhig = regime_reihe(_rahmen(ruhig))
    mit_spaeter = regime_reihe(_rahmen(gemischt))[:len(nur_ruhig)]

    a = [e["vola_regime"] for e in nur_ruhig]
    b = [e["vola_regime"] for e in mit_spaeter]
    assert a == b


def test_der_zustand_kennt_beide_auspraegungen():
    """Eine Reihe, die von ruhig auf unruhig kippt, muss beide Zustände
    zeigen — sonst prüft der Test nur, dass die Funktion nicht abstürzt."""
    kurse = _ruhig(VOLA_VERGLEICH + VOLA_FENSTER) + _unruhig(300)
    zustaende = {e["vola_regime"] for e in regime_reihe(_rahmen(kurse))
                 if e["vola_regime"] is not None}
    assert zustaende == {HOCH, NIEDRIG}


# ---------------------------------------------------------------------------
# Look-ahead beim Nachschlagen
# ---------------------------------------------------------------------------

def _reihe_mit_daten(n: int = 5) -> list[dict]:
    return [{"datum": BEGINN + timedelta(days=i), "vola": float(i),
             "vola_regime": HOCH, "ueber_ma": True, "richtungs_regime": AUF}
            for i in range(n)]


def test_der_zustand_von_heute_zaehlt_nicht():
    """Ein Index-Schlusskurs steht erst nach Handelsschluss fest; ein Snapshot
    kann früher am selben Tag entstanden sein."""
    reihe = _reihe_mit_daten()
    stichtag = reihe[-1]["datum"]
    assert regime_am(reihe, stichtag)["datum"] < stichtag


def test_der_sicherheitsabstand_gilt_ab_dem_ersten_tag():
    reihe = _reihe_mit_daten()
    stichtag = reihe[-1]["datum"] + timedelta(days=MIN_ABSTAND_TAGE)
    assert regime_am(reihe, stichtag)["datum"] == reihe[-1]["datum"]


def test_vor_dem_beginn_gibt_es_keinen_zustand():
    assert regime_am(_reihe_mit_daten(), BEGINN - timedelta(days=10)) is None


@pytest.mark.parametrize("reihe", [None, []])
def test_ohne_reihe_kein_zustand(reihe):
    assert regime_am(reihe, BEGINN) is None


# ---------------------------------------------------------------------------
# Die Auswertung nimmt keine unbekannten Größen an
# ---------------------------------------------------------------------------

def test_unbekannte_regimegroesse_wird_abgelehnt():
    """Ein Tippfehler darf nicht stillschweigend auf eine andere Bedingung
    ausweichen — dieselbe Entscheidung wie bei `holdout.split_filter`."""
    with pytest.raises(ValueError):
        signal_nach_regime(None, groesse="SMA-Cross (20/50)",
                           regime_art="gibt_es_nicht")


def test_unbekannte_signalgroesse_wird_abgelehnt():
    with pytest.raises(ValueError):
        signal_nach_regime(None, groesse="gibt_es_nicht",
                           regime_art="vola_regime")


def test_die_regimegroessen_sind_benannt():
    assert "vola_regime" in REGIME_ARTEN
    assert "richtungs_regime" in REGIME_ARTEN
