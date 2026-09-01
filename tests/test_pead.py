"""
tests/test_pead.py — Post-Earnings-Announcement Drift (P2-06).

Geprüft wird das, was den Befund still wertlos machen würde: eine Zahl, die
zum Snapshot-Zeitpunkt noch nicht öffentlich war, ein Ereignisfenster ohne
obere Grenze, ein Quintil, das an der Bereichsgrenze kippt, und eine
Mehrfachtest-Korrektur, die nach dem Umzug nach `basis.py` andere Werte
liefert als die, auf denen die bisherigen Befunde beruhen.
"""

from datetime import datetime, timedelta

import pytest

from services.pead import (
    MAX_ALTER_TAGE, MIN_ABSTAND_TAGE, earnings_laden, letztes_ereignis_vor,
)
from snapshot_engine.auswertung.basis import (
    fehlerspanne_korrigiert, fehlerspanne_pp, z_korrigiert,
)
from snapshot_engine.auswertung.pead import (
    ALTERSBAENDER, QUANTILE, _band_fuer, quintil,
)


STICHTAG = datetime(2024, 6, 15)


def _reihe(*abstaende_und_werte) -> list:
    """(Tage vor dem Stichtag, Abweichung) → Reihe wie aus der Datenbank."""
    reihe = [(STICHTAG - timedelta(days=t), w) for t, w in abstaende_und_werte]
    reihe.sort(key=lambda e: e[0])
    return reihe


# ---------------------------------------------------------------------------
# Look-ahead: was zum Stichtag bekannt war
# ---------------------------------------------------------------------------

def test_die_juengste_bekannte_zahl_gewinnt():
    reihe = _reihe((200, 1.0), (40, 5.0), (130, 9.0))
    datum, surprise, alter = letztes_ereignis_vor(reihe, STICHTAG)
    assert surprise == 5.0
    assert alter == 40
    assert datum == STICHTAG - timedelta(days=40)


def test_die_zahl_von_heute_zaehlt_nicht():
    """Der Kern der Look-ahead-Sicherung.

    Yahoo sagt nicht, ob vor Handelsbeginn oder nach Handelsschluss berichtet
    wurde. Ein Snapshot desselben Tages könnte eine nachbörsliche Zahl nicht
    gekannt haben — und genau dort, in der ersten Reaktion, sitzt der größte
    Teil der Bewegung. Sie mitzunehmen erzeugte einen Vorsprung, den es beim
    Handeln nie gegeben hätte.
    """
    assert letztes_ereignis_vor(_reihe((0, 12.0)), STICHTAG) is None


def test_der_sicherheitsabstand_gilt_ab_dem_ersten_tag():
    """Ein Tag Abstand genügt, zwei wären zu viel: die erste Sitzung nach der
    Zahl gehört zum Messgegenstand, nicht zur Unsicherheit."""
    assert MIN_ABSTAND_TAGE == 1
    treffer = letztes_ereignis_vor(_reihe((MIN_ABSTAND_TAGE, 12.0)), STICHTAG)
    assert treffer is not None
    assert treffer[2] == MIN_ABSTAND_TAGE


def test_zu_alte_zahlen_fallen_heraus():
    """Ohne obere Grenze trüge jeder Snapshot irgendein Ereignis — notfalls
    eines von vor fünf Monaten. Die Messung vergliche dann nicht mehr Drift
    gegen Nicht-Drift, sondern alte Überraschungen gegen sehr alte."""
    assert letztes_ereignis_vor(_reihe((MAX_ALTER_TAGE + 1, 8.0)), STICHTAG) is None
    assert letztes_ereignis_vor(_reihe((MAX_ALTER_TAGE, 8.0)), STICHTAG) is not None


def test_eine_zu_alte_zahl_verdeckt_keine_juengere():
    """Die Suche läuft rückwärts und darf nicht am ersten zu alten Eintrag
    abbrechen, wenn davor noch ein gültiger liegt."""
    reihe = _reihe((300, 1.0), (30, 7.0))
    treffer = letztes_ereignis_vor(reihe, STICHTAG)
    assert treffer is not None and treffer[1] == 7.0


@pytest.mark.parametrize("reihe", [None, []])
def test_ohne_reihe_kein_ereignis(reihe):
    assert letztes_ereignis_vor(reihe, STICHTAG) is None


# ---------------------------------------------------------------------------
# Quintile
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rang, erwartet", [
    (0.0, 1), (19.9, 1), (20.0, 2), (50.0, 3), (79.9, 4), (80.0, 5), (100.0, 5),
])
def test_quintil_grenzen(rang, erwartet):
    """100 gehört ins oberste Quintil, nicht in ein sechstes."""
    assert quintil(rang) == erwartet


def test_ohne_rang_kein_quintil():
    assert quintil(None) is None


# ---------------------------------------------------------------------------
# Altersbänder
# ---------------------------------------------------------------------------

def test_die_baender_decken_das_fenster_lueckenlos_ab():
    """Eine Lücke zwischen zwei Bändern verwürfe Beobachtungen still — und
    zwar ausgerechnet die im Übergangsbereich, in dem der Drift abklingt."""
    assert ALTERSBAENDER[0][0] == MIN_ABSTAND_TAGE
    assert ALTERSBAENDER[-1][1] == MAX_ALTER_TAGE
    for (_, bis), (naechstes_von, _) in zip(ALTERSBAENDER, ALTERSBAENDER[1:]):
        assert naechstes_von == bis + 1


def test_jedes_alter_im_fenster_findet_ein_band():
    for alter in range(MIN_ABSTAND_TAGE, MAX_ALTER_TAGE + 1):
        assert _band_fuer(alter) is not None


@pytest.mark.parametrize("alter", [0, MAX_ALTER_TAGE + 1])
def test_ausserhalb_des_fensters_kein_band(alter):
    assert _band_fuer(alter) is None


# ---------------------------------------------------------------------------
# Mehrfachtest-Korrektur
# ---------------------------------------------------------------------------

def test_korrektur_liefert_die_bisher_belegten_werte():
    """Regressionsschutz für den Umzug aus `schwellensuche.py` nach `basis.py`.

    Auf diesen drei Werten beruhen bereits veröffentlichte Befunde: 1,96 beim
    Einzeltest, 2,88 bei den dreizehn Schwellenkandidaten (P1-07) und 3,65 bei
    den 198 Sektorzellen (§2d). Eine abweichende Formel würde die alten
    Befunde stillschweigend mit den neuen unvergleichbar machen.
    """
    assert z_korrigiert(1) == pytest.approx(1.96, abs=0.005)
    assert z_korrigiert(13) == pytest.approx(2.88, abs=0.005)
    assert z_korrigiert(198) == pytest.approx(3.65, abs=0.005)


def test_mehr_tests_verlangen_mehr_vorsprung():
    assert z_korrigiert(20) > z_korrigiert(5) > z_korrigiert(1)
    assert z_korrigiert(0) == z_korrigiert(1)


def test_korrigierte_spanne_ist_weiter_als_die_unkorrigierte():
    quote, n = 55.0, 400
    assert (fehlerspanne_korrigiert(quote, n, z_korrigiert(20))
            > fehlerspanne_pp(quote, n))


@pytest.mark.parametrize("quote, n", [(None, 400), (55.0, 0), (55.0, None)])
def test_ohne_grundlage_keine_spanne(quote, n):
    assert fehlerspanne_korrigiert(quote, n, 2.0) is None


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------

def test_doppelte_zeitstempel_werden_zusammengefuehrt(monkeypatch):
    """Yahoo liefert für manche Titel zwei Zeilen mit identischem Zeitstempel
    (CSCO, 2002-08-06). Ungefiltert bricht der Bestandsaufbau am Unique-Index
    ab und verwirft per Rollback den gesamten Ticker — der Titel fehlt danach
    vollständig, ohne dass es an der Zeilenzahl auffiele.
    """
    import pandas as pd

    zeitpunkt = pd.Timestamp("2002-08-06 16:00:00")
    tabelle = pd.DataFrame(
        {"EPS Estimate": [0.12, 0.12], "Reported EPS": [0.14, 0.15],
         "Surprise(%)": [19.7, 25.0]},
        index=pd.DatetimeIndex([zeitpunkt, zeitpunkt]),
    )

    class _Ticker:
        def __init__(self, symbol):
            pass

        def get_earnings_dates(self, limit=None):
            return tabelle

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", _Ticker)

    ereignisse = earnings_laden("CSCO")
    assert len(ereignisse) == 1
    # Die spätere Zeile gewinnt — sie entspräche einer Korrektur.
    assert ereignisse[0]["surprise_pct"] == 25.0


def test_termine_ohne_ergebnis_sind_keine_ereignisse(monkeypatch):
    """Zeilen ohne berichtetes EPS sind angekündigte Termine. Als Ereignis
    gezählt bekämen künftige Quartale einen Rang."""
    import numpy as np
    import pandas as pd

    tabelle = pd.DataFrame(
        {"EPS Estimate": [1.0, 1.0],
         "Reported EPS": [np.nan, 1.2],
         "Surprise(%)": [np.nan, 20.0]},
        index=pd.DatetimeIndex(["2026-11-01 16:00", "2026-08-01 16:00"]),
    )

    class _Ticker:
        def __init__(self, symbol):
            pass

        def get_earnings_dates(self, limit=None):
            return tabelle

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", _Ticker)

    ereignisse = earnings_laden("XYZ")
    assert len(ereignisse) == 1
    assert ereignisse[0]["surprise_pct"] == 20.0


def test_fehlende_spalten_liefern_leer_statt_muell(monkeypatch):
    """Ändert yfinance die Struktur, ist eine leere Antwort das richtige
    Ergebnis — ein halb gefüllter Bestand wäre schlimmer, weil er später wie
    eine Abdeckungslücke aussähe."""
    import pandas as pd

    class _Ticker:
        def __init__(self, symbol):
            pass

        def get_earnings_dates(self, limit=None):
            return pd.DataFrame({"Etwas Anderes": [1.0]},
                                index=pd.DatetimeIndex(["2024-01-01"]))

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", _Ticker)

    assert earnings_laden("XYZ") == []


def test_quantile_und_baender_passen_zusammen():
    """Beide Größen bestimmen die Zahl der Zellen und damit die Korrektur.
    Wächst eine, ohne dass die Korrektur mitwächst, entstehen Zufallsfunde."""
    assert QUANTILE == 5
    assert len(ALTERSBAENDER) >= 3
