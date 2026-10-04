"""
tests/test_sektor_bestandteile.py — Zuordnung Sektor → Einzeltitel.

Die Aufschluesselung der Heatmap haengt daran, dass ein angezeigter
Sektorname auf die richtige Spalte der S&P-500-Liste trifft. Zwei Dinge sind
daran nicht offensichtlich und deshalb getestet:

  * "Ruestung & Luftfahrt" ist KEIN GICS-Sektor. ITA bildet eine Teilbranche
    innerhalb der Industrie ab und wird ueber "GICS Sub-Industry" aufgeloest.
    Wer nur ueber "GICS Sector" sucht, bekommt fuer diesen Sektor stillschweigend
    nichts.
  * Ein leeres Ergebnis heisst "nicht bestimmbar", nicht "Sektor ohne Titel".
    Der Aufrufer unterscheidet das, und die Funktion muss die Unterscheidung
    ueberhaupt erst ermoeglichen.

Reine Tabellenlogik, kein Netzabruf: die Bestandteilsliste wird gestellt.
"""

import pandas as pd

from services.market_data import sektor_aufschluesselbar, sektor_bestandteile


def _liste() -> pd.DataFrame:
    """Ausschnitt in der Form, die get_sp500_components() liefert."""
    return pd.DataFrame([
        {"Symbol": "AAPL", "Security": "Apple Inc.",
         "GICS Sector": "Information Technology",
         "GICS Sub-Industry": "Technology Hardware"},
        {"Symbol": "ADBE", "Security": "Adobe Inc.",
         "GICS Sector": "Information Technology",
         "GICS Sub-Industry": "Application Software"},
        {"Symbol": "BA", "Security": "Boeing",
         "GICS Sector": "Industrials",
         "GICS Sub-Industry": "Aerospace & Defense"},
        {"Symbol": "MMM", "Security": "3M",
         "GICS Sector": "Industrials",
         "GICS Sub-Industry": "Industrial Conglomerates"},
    ])


# ---------------------------------------------------------------------------
# Der gewoehnliche Weg: ueber den GICS-Sektor
# ---------------------------------------------------------------------------

def test_sektor_liefert_seine_titel_mit_namen():
    assert sektor_bestandteile(_liste(), "Technologie") == {
        "AAPL": "Apple Inc.",
        "ADBE": "Adobe Inc.",
    }


def test_sektor_grenzt_gegen_andere_ab():
    """Industrie darf keine Technologiewerte einsammeln."""
    industrie = sektor_bestandteile(_liste(), "Industrie")
    assert set(industrie) == {"BA", "MMM"}


# ---------------------------------------------------------------------------
# Die Ausnahme: ueber die Teilbranche
# ---------------------------------------------------------------------------

def test_ruestung_wird_ueber_die_teilbranche_aufgeloest():
    """Ueber "GICS Sector" waere dieser Sektor nicht auffindbar — es gibt ihn
    dort nicht. Ohne den Sub-Industry-Zweig bliebe die Kachel leer."""
    assert sektor_bestandteile(_liste(), "Rüstung & Luftfahrt") == {
        "BA": "Boeing"}


def test_ruestung_ist_teilmenge_der_industrie():
    """Keine Dopplung, sondern die Lage: der ITA-Korb liegt innerhalb der
    Industrie. Beide Kacheln duerfen denselben Titel zeigen."""
    liste = _liste()
    assert set(sektor_bestandteile(liste, "Rüstung & Luftfahrt")) <= set(
        sektor_bestandteile(liste, "Industrie"))


# ---------------------------------------------------------------------------
# Wenn nichts bestimmbar ist
# ---------------------------------------------------------------------------

def test_unbekannter_sektor_bleibt_leer():
    assert sektor_bestandteile(_liste(), "Krypto") == {}


def test_ohne_liste_bleibt_es_leer():
    assert sektor_bestandteile(None, "Technologie") == {}
    assert sektor_bestandteile(pd.DataFrame(), "Technologie") == {}


def test_fehlende_spalte_wirft_nicht():
    """Aendert Wikipedia die Spaltenbenennung, soll die Seite eine leere
    Aufschluesselung zeigen und nicht mit einem KeyError abstuerzen."""
    ohne = _liste().drop(columns=["GICS Sub-Industry"])
    assert sektor_bestandteile(ohne, "Rüstung & Luftfahrt") == {}
    assert sektor_bestandteile(ohne, "Technologie") != {}


# ---------------------------------------------------------------------------
# Verfuegbarkeit je Region
# ---------------------------------------------------------------------------

def test_europa_ist_nicht_aufschluesselbar():
    """Fuer den STOXX Europe 600 gibt es im Projekt keine Bestandteilsliste.
    Das muss VOR dem Kursabruf feststehen, sonst laedt die Seite minutenlang
    und zeigt am Ende nichts."""
    assert sektor_aufschluesselbar("Technologie", "eu") is False


def test_us_sektoren_sind_aufschluesselbar():
    assert sektor_aufschluesselbar("Technologie", "us") is True
    assert sektor_aufschluesselbar("Rüstung & Luftfahrt", "us") is True
    assert sektor_aufschluesselbar("Krypto", "us") is False


def test_alle_angezeigten_us_sektoren_sind_abgedeckt():
    """Die Heatmap zeigt zwoelf Kacheln. Bleibt eine davon ohne Zuordnung,
    fuehrt ihr Klick ins Leere — und zwar still."""
    from services.market_data import SECTOR_ETFS_US
    ohne = [name for name in SECTOR_ETFS_US.values()
            if not sektor_aufschluesselbar(name, "us")]
    assert ohne == []
