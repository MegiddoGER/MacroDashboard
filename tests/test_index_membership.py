"""
tests/test_index_membership.py — Index-Zugehörigkeit (P4-07).

Der interessante Fall ist hier nicht True und nicht False, sondern **None**.
Die Wikipedia-Tabelle führt nur die HEUTIGEN Mitglieder; ein Ticker, der fehlt,
ist entweder gar kein S&P-Wert (jeder Xetra-Titel) oder ein früheres Mitglied,
das entfernt wurde. Aus der Tabelle sind diese beiden Fälle nicht zu
unterscheiden — und beide falsch zu behandeln zerstört die Prüfung auf
entgegengesetzte Weise: als „nicht Mitglied" verwirft sie das halbe Universum,
als „Mitglied" wird sie wirkungslos.
"""

from datetime import datetime

from services.index_membership import SPALTE_DATUM, SPALTE_SYMBOL, war_mitglied

AUFNAHMEN = {
    "AAPL": datetime(1982, 11, 30),
    "RDDT": datetime(2026, 8, 18),
}


def test_lange_vor_dem_stichtag_aufgenommen():
    assert war_mitglied("AAPL", datetime(2023, 5, 1), AUFNAHMEN) is True


def test_erst_nach_dem_stichtag_aufgenommen():
    """Der Kern von P4-07: Reddit steckt mit seiner ganzen Vorgeschichte im
    Universum, war 2023 aber kein Indexmitglied."""
    assert war_mitglied("RDDT", datetime(2023, 5, 1), AUFNAHMEN) is False


def test_der_aufnahmetag_selbst_zaehlt_als_mitglied():
    assert war_mitglied("RDDT", datetime(2026, 8, 18), AUFNAHMEN) is True


def test_schreibweise_spielt_keine_rolle():
    assert war_mitglied(" aapl ", datetime(2023, 5, 1), AUFNAHMEN) is True


# ---------------------------------------------------------------------------
# Die Unbekannt-Fälle
# ---------------------------------------------------------------------------

def test_unbekannter_ticker_ist_unbekannt_nicht_kein_mitglied():
    """SAP.DE ist kein S&P-Wert; ORCL könnte ein entferntes Mitglied sein.
    Beide sind aus dieser Tabelle nicht zu beurteilen."""
    assert war_mitglied("SAP.DE", datetime(2023, 5, 1), AUFNAHMEN) is None
    assert war_mitglied("EHEMALIG", datetime(2023, 5, 1), AUFNAHMEN) is None


def test_ohne_aufnahmedaten_keine_aussage():
    """Wenn der Abruf gescheitert ist, darf die Prüfung nicht stillschweigend
    alles durchlassen."""
    assert war_mitglied("AAPL", datetime(2023, 5, 1), None) is None
    assert war_mitglied("AAPL", datetime(2023, 5, 1), {}) is None


def test_ohne_ticker_oder_zeitpunkt_keine_aussage():
    assert war_mitglied("", datetime(2023, 5, 1), AUFNAHMEN) is None
    assert war_mitglied("AAPL", None, AUFNAHMEN) is None


# ---------------------------------------------------------------------------
# Feldnamen
# ---------------------------------------------------------------------------

def test_spaltennamen_sind_die_geprueften():
    """Gegen eine echte Antwort bestätigt (2026-08-31, 503 Zeilen). Ändert
    Wikipedia die Spalten, erkennt der Service das und liefert None statt
    stillschweigend falscher Daten."""
    assert SPALTE_SYMBOL == "Symbol"
    assert SPALTE_DATUM == "Date added"
