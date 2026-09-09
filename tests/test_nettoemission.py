"""
tests/test_nettoemission.py — Nettoemission aus den SEC-XBRL-Daten (P2-06).

Der Schwerpunkt liegt auf **Split-Immunitaet**. Das ist keine Randbedingung,
sondern der Grund fuer den Zuschnitt des Moduls: Aktienzahlen der SEC sind
roh, und eine Einreichung stellt ihre Vergleichsperioden auf die aktuelle
Split-Basis um. Wer die Zahlen zweier Einreichungen vergleicht, misst fuer
NVDA nach dem 10:1-Split von 2024 eine Nettoemission von rund +887 Prozent,
wo tatsaechlich ein Rueckkauf von einem halben Prozent stattfand — ein frei
erfundener Extremwert in genau dem Quintil, das die Aussage traegt.

Die erste Testgruppe haelt darum mit echten NVDA-Zahlen fest, dass genau das
nicht passieren kann.
"""

from datetime import datetime

import pytest

from services.nettoemission import (
    MAX_BETRAG, VOLLE_HISTORIE, nettoemission_laden, paare_aus_einreichungen,
)
from snapshot_engine.auswertung.nettoemission import (
    QUANTILE, _spread, letzte_kennzahl_vor, quintil,
)


def _fakt(ende, val, accn, filed, start=None):
    e = {"end": ende, "val": val, "accn": accn, "filed": filed}
    if start:
        e["start"] = start
    return e


# ---------------------------------------------------------------------------
# Split-Immunitaet — der Kern
# ---------------------------------------------------------------------------

# Echte Zahlen aus `WeightedAverageNumberOfSharesOutstandingBasic` fuer NVDA,
# abgerufen am 2026-09-09. Die Einreichung von 2025 traegt dieselbe Periode
# 2023-01-29 mit dem Zehnfachen — der Split vom Juni 2024.
NVDA = [
    _fakt("2023-01-29", 2_487_000_000, "0001045810-24-000029", "2024-02-21"),
    _fakt("2024-01-28", 2_469_000_000, "0001045810-24-000029", "2024-02-21"),
    _fakt("2023-01-29", 24_870_000_000, "0001045810-25-000023", "2025-02-26"),
    _fakt("2024-01-28", 24_690_000_000, "0001045810-25-000023", "2025-02-26"),
    _fakt("2025-01-26", 24_555_000_000, "0001045810-25-000023", "2025-02-26"),
]


def test_der_split_erzeugt_keine_scheinemission():
    """Der eigentliche Zweck des Moduls, an echten Zahlen."""
    paare = paare_aus_einreichungen(NVDA)

    # 2024er Periode: aus der Einreichung von 2024, beide Werte vorspalt.
    p2024 = paare["2024-01-28"]
    assert p2024["aktien"] == 2_469_000_000
    assert p2024["aktien_vorjahr"] == 2_487_000_000

    # 2025er Periode: aus der Einreichung von 2025, beide Werte nachspalt.
    p2025 = paare["2025-01-26"]
    assert p2025["aktien"] == 24_555_000_000
    assert p2025["aktien_vorjahr"] == 24_690_000_000

    # Entscheidend: NIE ueber die Einreichungsgrenze hinweg. Ein Paar
    # (24.555 Mio / 2.487 Mio) waere Faktor 9,9 und damit die Scheinemission.
    for p in paare.values():
        verhaeltnis = p["aktien"] / p["aktien_vorjahr"]
        assert 0.5 < verhaeltnis < 2.0, (
            f"Verhaeltnis {verhaeltnis:.2f} — das ist ein Split, keine Emission")


def test_beide_werte_stammen_aus_derselben_accession():
    """Die Eigenschaft, aus der die Split-Immunitaet folgt."""
    paare = paare_aus_einreichungen(NVDA)
    # Jedes Paar nennt genau eine Accession; dass beide Werte daher stammen,
    # ist die Konstruktion von `paare_aus_einreichungen`.
    assert paare["2024-01-28"]["accession"] == "0001045810-24-000029"
    assert paare["2025-01-26"]["accession"] == "0001045810-25-000023"


def test_die_frueheste_einreichung_gewinnt():
    """Punkt-in-Zeit: spaetere Wiederholungen derselben Periode zaehlen nicht.

    Die Periode 2024-01-28 steht in beiden Einreichungen. Genommen wird die
    von 2024 — sonst waere die Kennzahl ein Jahr zu frueh datiert und traege
    zudem die spaetere Split-Basis.
    """
    paare = paare_aus_einreichungen(NVDA)
    assert paare["2024-01-28"]["bekannt_ab"].isoformat() == "2024-02-21"
    assert paare["2024-01-28"]["accession"] == "0001045810-24-000029"


# ---------------------------------------------------------------------------
# Paarbildung
# ---------------------------------------------------------------------------

def test_ohne_vorjahr_kein_paar():
    """Eine einzelne Periode ergibt nichts — es fehlt der Bezugspunkt."""
    assert paare_aus_einreichungen(
        [_fakt("2024-01-28", 1000, "A", "2024-02-21")]) == {}


@pytest.mark.parametrize("ende,erwartet", [
    ("2025-01-28", True),    # rund ein Jahr
    ("2024-07-28", False),   # Halbjahr
    ("2027-01-28", False),   # zwei Jahre
])
def test_nur_jahresabstaende_werden_gepaart(ende, erwartet):
    eintraege = [_fakt("2024-01-28", 1000, "A", "2025-03-01"),
                 _fakt(ende, 1100, "A", "2025-03-01")]
    assert bool(paare_aus_einreichungen(eintraege)) is erwartet


def test_zeitraumwerte_muessen_ein_jahr_umfassen():
    """Quartalswerte tragen `start` und fallen ueber JAHRESDAUER heraus."""
    eintraege = [
        _fakt("2024-03-31", 1000, "A", "2025-03-01", start="2024-01-01"),
        _fakt("2025-03-31", 1100, "A", "2025-03-01", start="2025-01-01"),
    ]
    assert paare_aus_einreichungen(eintraege) == {}


def test_stichtagswerte_ohne_beginn_werden_durchgelassen():
    """`CommonStockSharesOutstanding` hat kein `start` und ist trotzdem gueltig."""
    eintraege = [_fakt("2024-01-28", 1000, "A", "2025-03-01"),
                 _fakt("2025-01-26", 1100, "A", "2025-03-01")]
    assert "2025-01-26" in paare_aus_einreichungen(eintraege)


@pytest.mark.parametrize("val", [0, -100, None])
def test_unbrauchbare_aktienzahlen_ergeben_kein_paar(val):
    """Null oder negativ ist kein Nenner und keine Aktienzahl."""
    eintraege = [_fakt("2024-01-28", val, "A", "2025-03-01"),
                 _fakt("2025-01-26", 1100, "A", "2025-03-01")]
    assert paare_aus_einreichungen(eintraege) == {}


def test_unvollstaendige_fakten_werden_uebergangen():
    eintraege = [
        {"end": "2024-01-28", "val": 1000, "accn": "A"},          # kein filed
        {"end": "2025-01-26", "val": 1100, "filed": "2025-03-01"},  # kein accn
    ]
    assert paare_aus_einreichungen(eintraege) == {}


# ---------------------------------------------------------------------------
# nettoemission_laden — Auswahl und Ausreisser
# ---------------------------------------------------------------------------

def test_das_bestabgedeckte_konzept_gewinnt(monkeypatch):
    """Nicht der erste Treffer, sondern der mit der laengsten Historie.

    Gemessen an GOOGL: das erste Konzept liefert drei Paare, ein spaeteres
    elf. Wer beim ersten nicht leeren Treffer stehen bleibt, verliert zwei
    Drittel der Historie, ohne dass es auffiele.
    """
    import services.nettoemission as m

    duenn = [_fakt("2024-12-31", 1000, "A", "2025-02-05"),
             _fakt("2025-12-31", 1010, "A", "2025-02-05")]
    dick = [_fakt(f"{j}-12-31", 1000 + j, "B", "2025-02-05")
            for j in range(2016, 2026)]

    def gefaelscht(cik, konzept):
        return duenn if konzept == m.KONZEPTE_AKTIEN[0] else dick

    monkeypatch.setattr(m, "_konzept_laden", gefaelscht)
    ergebnis = m.nettoemission_laden("X", "0000000001")
    assert len(ergebnis) > 1
    assert ergebnis[0]["konzept"] == m.KONZEPTE_AKTIEN[1]


def test_volle_historie_beendet_die_suche(monkeypatch):
    """Ab VOLLE_HISTORIE Paaren wird nicht weiter abgerufen — Abrufe kosten."""
    import services.nettoemission as m

    gerufen = []
    reihe = [_fakt(f"{j}-12-31", 1000, "A", f"{j + 1}-02-05")
             for j in range(2005, 2005 + VOLLE_HISTORIE + 2)]

    def gefaelscht(cik, konzept):
        gerufen.append(konzept)
        return reihe

    monkeypatch.setattr(m, "_konzept_laden", gefaelscht)
    m.nettoemission_laden("X", "0000000001")
    assert len(gerufen) == 1


def test_extreme_spruenge_werden_verworfen(monkeypatch):
    """Ein nicht rueckwirkend angewandter Split ist keine Emission.

    Verworfen statt gestutzt: ein gestutzter Extremwert landet immer noch im
    aeussersten Quintil und traegt dort das Ergebnis.
    """
    import services.nettoemission as m

    reihe = [_fakt("2024-12-31", 1_000, "A", "2025-02-05"),
             _fakt("2025-12-31", 10_000, "A", "2025-02-05")]   # ln(10) = 2,30
    monkeypatch.setattr(m, "_konzept_laden", lambda cik, konzept: reihe)
    assert m.nettoemission_laden("X", "0000000001") == []


def test_rueckkauf_ist_negativ(monkeypatch):
    """Vorzeichenkonvention: weniger Aktien als im Vorjahr ergibt < 0."""
    import services.nettoemission as m

    reihe = [_fakt("2024-12-31", 1_000, "A", "2025-02-05"),
             _fakt("2025-12-31", 900, "A", "2025-02-05")]
    monkeypatch.setattr(m, "_konzept_laden", lambda cik, konzept: reihe)
    ergebnis = m.nettoemission_laden("X", "0000000001")
    assert ergebnis[0]["nettoemission"] < 0
    assert ergebnis[0]["aktien"] == 900


def test_emission_ist_positiv(monkeypatch):
    import services.nettoemission as m

    reihe = [_fakt("2024-12-31", 1_000, "A", "2025-02-05"),
             _fakt("2025-12-31", 1_100, "A", "2025-02-05")]
    monkeypatch.setattr(m, "_konzept_laden", lambda cik, konzept: reihe)
    assert m.nettoemission_laden("X", "0000000001")[0]["nettoemission"] > 0


def test_die_grenze_liegt_bei_max_betrag(monkeypatch):
    """Knapp innerhalb bleibt, knapp ausserhalb faellt."""
    import services.nettoemission as m
    from math import exp

    for faktor, erwartet in [(exp(MAX_BETRAG * 0.9), 1), (exp(MAX_BETRAG * 1.1), 0)]:
        reihe = [_fakt("2024-12-31", 1_000, "A", "2025-02-05"),
                 _fakt("2025-12-31", 1_000 * faktor, "A", "2025-02-05")]
        monkeypatch.setattr(m, "_konzept_laden", lambda cik, konzept: reihe)
        assert len(m.nettoemission_laden("X", "0000000001")) == erwartet


# ---------------------------------------------------------------------------
# Punkt-in-Zeit beim Lesen
# ---------------------------------------------------------------------------

REIHE = [(datetime(2020, 3, 1), 0.05), (datetime(2021, 3, 1), -0.02)]


def test_die_juengste_bekannte_kennzahl_gewinnt():
    assert letzte_kennzahl_vor(REIHE, datetime(2021, 6, 1))[1] == -0.02


def test_die_heute_veroeffentlichte_zahl_zaehlt_nicht():
    """`bekannt_ab` traegt keine Uhrzeit — der Tag selbst ist noch nicht bekannt."""
    assert letzte_kennzahl_vor(REIHE, datetime(2020, 3, 1)) is None


def test_ueberholte_kennzahlen_fallen_heraus():
    assert letzte_kennzahl_vor(REIHE, datetime(2024, 6, 1)) is None


@pytest.mark.parametrize("reihe", [None, []])
def test_ohne_reihe_keine_kennzahl(reihe):
    assert letzte_kennzahl_vor(reihe, datetime(2021, 6, 1)) is None


# ---------------------------------------------------------------------------
# Quintile und Spread
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rang,erwartet", [
    (0.0, 1), (19.9, 1), (20.0, 2), (50.0, 3), (99.9, 5), (100.0, 5),
])
def test_quintil_grenzen(rang, erwartet):
    assert quintil(rang) == erwartet


def test_quintil_eins_sind_die_rueckkaeufer():
    """Richtungskonvention: unten ist gut, wie bei den Accruals."""
    assert quintil(0.0) == 1
    assert quintil(99.0) == QUANTILE


def test_der_spread_ist_q1_minus_q5():
    """Positiv heisst „Hypothese bestaetigt" — auch hier, wie bei accruals.py."""
    zeilen = [{"quintil": 1, "markt_trefferquote": 52.0},
              {"quintil": 5, "markt_trefferquote": 48.0}]
    assert _spread(zeilen, "markt_trefferquote") == 4.0


def test_ohne_beide_enden_kein_spread():
    zeilen = [{"quintil": 1, "markt_trefferquote": 52.0}]
    assert _spread(zeilen, "markt_trefferquote") is None


def test_fehlende_werte_ergeben_keinen_spread():
    zeilen = [{"quintil": 1, "markt_trefferquote": None},
              {"quintil": 5, "markt_trefferquote": 48.0}]
    assert _spread(zeilen, "markt_trefferquote") is None
