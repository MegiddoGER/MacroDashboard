"""
tests/test_analyst_revisions.py — Analystenrevisionen als Signalquelle (P2-06).

Geprüft wird, was den Befund still verfälschen würde: die Null, die Yahoo
statt eines fehlenden Kursziels liefert, eine Handlung vom Tag des Snapshots,
ein Rückschaufenster ohne Untergrenze, und eine Wertegruppierung, die die
Null-Mehrheit des Netto-Ratings nicht als eigene Gruppe führt.
"""

from datetime import datetime, timedelta

import pytest

from services.analyst_revisions import (
    AKTION_HERAB, AKTION_HERAUF, FENSTER_TAGE, MIN_ABSTAND_TAGE, _positiv,
    fenster_verdichten, revisionen_laden, zielrevision,
)
from snapshot_engine.auswertung.analyst_revisions import (
    NETTO_GRUPPEN, QUANTILE, netto_gruppe, quintil,
)


STICHTAG = datetime(2024, 6, 15)


def _reihe(*eintraege) -> list:
    """(Tage vor dem Stichtag, Aktion, Revision) → Reihe wie aus der Datenbank."""
    reihe = [(STICHTAG - timedelta(days=t), a, r) for t, a, r in eintraege]
    reihe.sort(key=lambda e: e[0])
    return reihe


# ---------------------------------------------------------------------------
# Die Nullfalle
# ---------------------------------------------------------------------------

def test_null_ist_kein_kursziel():
    """Yahoo schreibt `0.0` statt `NaN`, wenn kein Vorziel existiert — bei rund
    einem Fünftel der Zeilen. Als Zahl gelesen ergäbe sie eine Revision von
    −100 % oder eine Division durch null."""
    assert _positiv(0.0) is None
    assert _positiv(-5.0) is None
    assert _positiv(None) is None
    assert _positiv(120.0) == 120.0


@pytest.mark.parametrize("neu, alt", [(100.0, 0.0), (100.0, None), (None, 100.0),
                                      (0.0, 100.0), (100.0, -1.0)])
def test_ohne_brauchbares_paar_keine_revision(neu, alt):
    assert zielrevision(neu, alt) is None


def test_zielrevision_ist_die_prozentuale_aenderung():
    assert zielrevision(110.0, 100.0) == pytest.approx(10.0)
    assert zielrevision(80.0, 100.0) == pytest.approx(-20.0)


# ---------------------------------------------------------------------------
# Rückschaufenster und Look-ahead
# ---------------------------------------------------------------------------

def test_die_handlung_von_heute_zaehlt_nicht():
    """Eine Hochstufung wirkt am Tag ihrer Veröffentlichung am stärksten — und
    genau an diesem Tag ist unklar, ob sie zum Snapshot-Zeitpunkt schon
    bekannt war."""
    assert fenster_verdichten(_reihe((0, AKTION_HERAUF, 12.0)), STICHTAG) is None


def test_der_sicherheitsabstand_gilt_ab_dem_ersten_tag():
    verdichtet = fenster_verdichten(
        _reihe((MIN_ABSTAND_TAGE, AKTION_HERAUF, 12.0)), STICHTAG)
    assert verdichtet is not None
    assert verdichtet["netto_rating"] == 1


def test_handlungen_vor_dem_fenster_zaehlen_nicht():
    """Ohne Untergrenze verdichtete das Fenster irgendwann die gesamte
    Historie, und ein Titel mit langer Abdeckung bekäme allein deshalb ein
    größeres Netto-Rating."""
    assert fenster_verdichten(
        _reihe((FENSTER_TAGE + 1, AKTION_HERAUF, 12.0)), STICHTAG) is None
    assert fenster_verdichten(
        _reihe((FENSTER_TAGE, AKTION_HERAUF, 12.0)), STICHTAG) is not None


def test_netto_rating_zaehlt_nur_echte_wechsel():
    """`main` und `reit` bestätigen ein Rating — sie sind rund drei Viertel
    aller Zeilen und dürfen das Netto nicht bewegen."""
    verdichtet = fenster_verdichten(_reihe(
        (5, AKTION_HERAUF, 8.0), (10, AKTION_HERAUF, 6.0),
        (15, AKTION_HERAB, -4.0), (20, "main", 2.0), (25, "reit", 1.0),
        (30, "init", None),
    ), STICHTAG)
    assert verdichtet["netto_rating"] == 1
    assert verdichtet["anzahl_rating"] == 3
    assert verdichtet["anzahl"] == 6


def test_zielrevision_mittelt_nur_ueber_brauchbare_paare():
    verdichtet = fenster_verdichten(_reihe(
        (5, "main", 10.0), (10, "main", 20.0), (15, "init", None),
    ), STICHTAG)
    assert verdichtet["ziel_revision"] == pytest.approx(15.0)
    assert verdichtet["anzahl_ziel"] == 2
    assert verdichtet["anzahl"] == 3


def test_fenster_ohne_kursziele_liefert_keine_revision():
    """Eine Gruppe reiner Rating-Meldungen hat kein Ziel — dort muss None
    stehen und nicht null, sonst wanderte sie in die mittleren Quintile."""
    verdichtet = fenster_verdichten(
        _reihe((5, AKTION_HERAUF, None), (9, "init", None)), STICHTAG)
    assert verdichtet["ziel_revision"] is None
    assert verdichtet["netto_rating"] == 1


@pytest.mark.parametrize("reihe", [None, []])
def test_ohne_reihe_keine_verdichtung(reihe):
    assert fenster_verdichten(reihe, STICHTAG) is None


# ---------------------------------------------------------------------------
# Gruppierung
# ---------------------------------------------------------------------------

def test_die_null_ist_eine_eigene_gruppe():
    """Der Kern der Bauweise: das Netto-Rating ist meistens null, und null
    heißt „kein Haus hat sich bewegt" — nicht „schwach positiv". Über Ränge
    gruppiert bekäme diese Mehrheit einen einzigen Durchschnittsrang, und die
    Quintilgrenzen lägen willkürlich mitten in ihr."""
    assert netto_gruppe(0) == "0"
    assert netto_gruppe(1) != netto_gruppe(0)
    assert netto_gruppe(-1) != netto_gruppe(0)


@pytest.mark.parametrize("wert, erwartet", [
    (-9, "<= -2"), (-2, "<= -2"), (-1, "-1"), (0, "0"), (1, "+1"),
    (2, ">= +2"), (99, ">= +2"),
])
def test_netto_gruppen_grenzen(wert, erwartet):
    assert netto_gruppe(wert) == erwartet


def test_die_netto_gruppen_decken_jeden_ganzzahligen_wert_ab():
    for wert in range(-50, 51):
        assert netto_gruppe(wert) is not None
    assert netto_gruppe(None) is None


def test_die_netto_gruppen_ueberlappen_nicht():
    for (_, von_a, bis_a), (_, von_b, bis_b) in zip(NETTO_GRUPPEN,
                                                    NETTO_GRUPPEN[1:]):
        assert bis_a < von_b


@pytest.mark.parametrize("rang, erwartet", [
    (0.0, 1), (19.9, 1), (20.0, 2), (50.0, 3), (79.9, 4), (80.0, 5), (100.0, 5),
])
def test_quintil_grenzen(rang, erwartet):
    assert quintil(rang) == erwartet


def test_ohne_rang_kein_quintil():
    assert quintil(None) is None
    assert QUANTILE == 5


# ---------------------------------------------------------------------------
# Abruf
# ---------------------------------------------------------------------------

def _tabelle(zeilen, index):
    import pandas as pd
    return pd.DataFrame(zeilen, index=pd.DatetimeIndex(index))


def _stelle_ticker(monkeypatch, tabelle):
    class _Ticker:
        def __init__(self, symbol):
            pass

        @property
        def upgrades_downgrades(self):
            return tabelle

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", _Ticker)


def test_gleiches_haus_zur_gleichen_zeit_wird_zusammengefuehrt(monkeypatch):
    """Zwei Zeilen mit gleichem Zeitstempel UND gleichem Haus wären am
    Unique-Index ein Abbruch, der per Rollback den ganzen Ticker verwirft —
    derselbe Fehler, der beim Earnings-Bestand 32 Ticker gekostet hat."""
    _stelle_ticker(monkeypatch, _tabelle({
        "Firm": ["Goldman", "Goldman"],
        "ToGrade": ["Buy", "Hold"], "FromGrade": ["Hold", "Buy"],
        "Action": ["up", "down"], "priceTargetAction": ["Raises", "Lowers"],
        "currentPriceTarget": [120.0, 90.0], "priorPriceTarget": [100.0, 100.0],
    }, ["2024-03-01 12:00", "2024-03-01 12:00"]))

    handlungen = revisionen_laden("XYZ")
    assert len(handlungen) == 1


def test_zwei_haeuser_am_selben_tag_bleiben_zwei_handlungen(monkeypatch):
    """Der Gegentest: das Haus gehört in den Schlüssel, sonst verschwände die
    halbe Trefferbreite eines Tages, an dem sich mehrere Analysten bewegen."""
    _stelle_ticker(monkeypatch, _tabelle({
        "Firm": ["Goldman", "Jefferies"],
        "ToGrade": ["Buy", "Buy"], "FromGrade": ["Hold", "Hold"],
        "Action": ["up", "up"], "priceTargetAction": ["Raises", "Raises"],
        "currentPriceTarget": [120.0, 125.0], "priorPriceTarget": [100.0, 100.0],
    }, ["2024-03-01 12:00", "2024-03-01 12:00"]))

    assert len(revisionen_laden("XYZ")) == 2


def test_das_nullziel_wird_beim_laden_zu_none(monkeypatch):
    _stelle_ticker(monkeypatch, _tabelle({
        "Firm": ["Citizens"], "ToGrade": ["Outperform"], "FromGrade": [""],
        "Action": ["init"], "priceTargetAction": ["Announces"],
        "currentPriceTarget": [350.0], "priorPriceTarget": [0.0],
    }, ["2024-03-01 12:00"]))

    handlung = revisionen_laden("XYZ")[0]
    assert handlung["ziel_alt"] is None
    assert handlung["ziel_neu"] == 350.0


def test_handlung_ohne_haus_wird_verworfen(monkeypatch):
    """Ohne Haus fehlt der dritte Teil des Schlüssels; zwei solche Zeilen
    desselben Tages ließen sich später nicht mehr trennen."""
    import numpy as np
    _stelle_ticker(monkeypatch, _tabelle({
        "Firm": [np.nan], "ToGrade": ["Buy"], "FromGrade": ["Hold"],
        "Action": ["up"], "priceTargetAction": ["Raises"],
        "currentPriceTarget": [120.0], "priorPriceTarget": [100.0],
    }, ["2024-03-01 12:00"]))

    assert revisionen_laden("XYZ") == []


def test_fehlende_spalten_liefern_leer_statt_muell(monkeypatch):
    _stelle_ticker(monkeypatch, _tabelle(
        {"Etwas Anderes": [1.0]}, ["2024-03-01"]))
    assert revisionen_laden("XYZ") == []


def test_leere_quelle_ist_kein_fehler(monkeypatch):
    """Bei deutschen Titeln der Normalfall — Yahoo führt für sie kein
    Handlungsprotokoll."""
    _stelle_ticker(monkeypatch, None)
    assert revisionen_laden("BMW.DE") == []
