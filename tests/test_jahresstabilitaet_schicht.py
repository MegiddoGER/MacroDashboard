"""
tests/test_jahresstabilitaet_schicht.py — Jahresstabilitaet je Groessenschicht.

Die schaerfste Pruefung des Kandidaten aus §2p, weil sie die beiden Filter
kombiniert, an denen bisher alles gestorben ist. §2p besteht die Jahrespruefung
**gepoolt** (10 von 10), §2q die Groessentrennung **im Querschnitt** (15 von
15) — und keine der beiden Aussagen schliesst aus, dass eine einzelne
Groessenklasse das Jahresergebnis traegt.

Geprueft wird hier die Rechnung, nicht der Befund: dass die Vorzeichenbilanz
das **haeufigere** Vorzeichen zaehlt (eine Familie, die zehnmal in die
Gegenrichtung zeigt, ist stabil widerlegt und nicht etwa unauffaellig), dass
Jahre ohne beide Randquintile herausfallen statt stillschweigend als
bestaetigt zu gelten, und dass jede Zelle gegen die Basis IHRES Jahres
gerechnet wird.
"""

import pytest

from snapshot_engine.auswertung.nettoemission import (
    QUANTILE, _jahreszeilen, _vorzeichenbilanz,
)


# ---------------------------------------------------------------------------
# Die Vorzeichenbilanz
# ---------------------------------------------------------------------------

def test_zaehlt_das_haeufigere_vorzeichen_nicht_das_positive():
    """Zehn Gegenjahre sind ebenso stabil wie zehn Bestaetigungen.

    Die Binomialtafel aus §2j gilt fuer beide Faelle gleich — sie misst, ob
    ein Vorzeichen haelt, nicht ob es das erhoffte ist.
    """
    zeilen = [{"spread_pp": -1.0} for _ in range(10)]
    assert _vorzeichenbilanz(zeilen, "spread_pp") == (10, 10)


def test_gemischte_jahre_ergeben_die_mehrheit():
    zeilen = [{"spread_pp": v} for v in (1.0, 1.0, 1.0, -1.0, -1.0)]
    assert _vorzeichenbilanz(zeilen, "spread_pp") == (3, 5)


def test_jahre_ohne_wert_zaehlen_nicht_mit():
    """Ein fehlender Ertrag-Spread darf die Bilanz nicht als Treffer aufblaehen."""
    zeilen = [{"ertrag_spread_pp": 1.0}, {"ertrag_spread_pp": None},
              {"ertrag_spread_pp": 1.0}]
    assert _vorzeichenbilanz(zeilen, "ertrag_spread_pp") == (2, 2)


def test_ohne_jahre_keine_bilanz():
    assert _vorzeichenbilanz([], "spread_pp") == (0, 0)


def test_die_null_gilt_nicht_als_positiv():
    """Ein Spread von exakt 0,0 ist kein Vorzeichen.

    Er landet in der Gegenzaehlung, damit ein Nullergebnis nicht als
    Bestaetigung durchgeht.
    """
    zeilen = [{"spread_pp": 0.0}, {"spread_pp": 1.0}]
    haeufiger, gesamt = _vorzeichenbilanz(zeilen, "spread_pp")
    assert gesamt == 2
    assert haeufiger == 1


# ---------------------------------------------------------------------------
# Die Jahreszeilen
# ---------------------------------------------------------------------------

def _jahr(q1_treffer: int, q1_n: int, q5_treffer: int, q5_n: int):
    """Ein Jahr als (gruppen, alle) — Renditen ueber/unter der Marktrendite.

    `zelle_gegen_markt` bekommt (rendite, ueberrendite)-Paare; die
    Trefferquote zaehlt Ueberrenditen > 0.
    """
    gruppen = {
        1: [(1.0, 1.0)] * q1_treffer + [(1.0, -1.0)] * (q1_n - q1_treffer),
        QUANTILE: [(1.0, 1.0)] * q5_treffer + [(1.0, -1.0)] * (q5_n - q5_treffer),
    }
    alle = [u for paare in gruppen.values() for _, u in paare]
    return gruppen, alle


def test_ein_jahr_mit_klarem_spread():
    """Q1 trifft haeufiger als Q5 — der Spread ist positiv."""
    gruppen, alle = _jahr(q1_treffer=800, q1_n=1000,
                          q5_treffer=200, q5_n=1000)
    zeilen = _jahreszeilen({2020: gruppen}, {2020: alle}, horizont=90)

    assert len(zeilen) == 1
    assert zeilen[0]["jahr"] == 2020
    assert zeilen[0]["n"] == 2000
    # 80 % gegen 20 % — Spread +60 pp.
    assert zeilen[0]["spread_pp"] == pytest.approx(60.0)


def test_jahr_ohne_randquintil_faellt_heraus():
    """Fehlt Q1 oder Q5, gibt es keinen Spread — und keine stille Null."""
    gruppen = {1: [(1.0, 1.0)] * 100}          # nur Q1, kein Q5
    alle = [1.0] * 100
    assert _jahreszeilen({2020: gruppen}, {2020: alle}, horizont=90) == []


def test_jede_zelle_gegen_die_basis_ihres_jahres():
    """Zwei Jahre mit gleicher Trennschaerfe, aber verschiedener Marktlage.

    Das gute Jahr trifft in beiden Quintilen haeufiger. Wuerde gegen eine
    gemeinsame Basis gerechnet, erschiene es als staerkeres Signal — es ist
    aber nur ein besserer Markt. Der Spread muss in beiden Jahren gleich sein.
    """
    schwach, schwach_alle = _jahr(q1_treffer=600, q1_n=1000,
                                  q5_treffer=400, q5_n=1000)
    stark, stark_alle = _jahr(q1_treffer=900, q1_n=1000,
                              q5_treffer=700, q5_n=1000)

    zeilen = _jahreszeilen({2020: schwach, 2021: stark},
                           {2020: schwach_alle, 2021: stark_alle},
                           horizont=90)

    assert len(zeilen) == 2
    # Beide Jahre trennen um 20 pp — die Marktlage ist herausgerechnet.
    assert zeilen[0]["spread_pp"] == pytest.approx(20.0)
    assert zeilen[1]["spread_pp"] == pytest.approx(20.0)


def test_jahre_kommen_aufsteigend():
    """Die Ausgabe wird gelesen — eine unsortierte Jahresreihe ist ein Aergernis."""
    a, a_alle = _jahr(700, 1000, 300, 1000)
    b, b_alle = _jahr(700, 1000, 300, 1000)
    c, c_alle = _jahr(700, 1000, 300, 1000)

    zeilen = _jahreszeilen({2022: a, 2020: b, 2021: c},
                           {2022: a_alle, 2020: b_alle, 2021: c_alle},
                           horizont=90)
    assert [z["jahr"] for z in zeilen] == [2020, 2021, 2022]
