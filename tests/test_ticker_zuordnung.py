"""
tests/test_ticker_zuordnung.py — Die Bruecke von der Notierung zum SEC-Emittenten.

Der eigentliche Zweck dieser Datei ist **eine** Sorte Fehler: die stille
Falschzuordnung. Eine fehlende Zuordnung kostet eine leere Anzeige und faellt
sofort auf. Eine falsche liefert plausible Zahlen zum falschen Unternehmen und
faellt nie auf — bis eine Entscheidung darauf steht.

Die beiden echten Fallen aus der Watchlist, an denen der naheliegende Weg
(Endung abschneiden) scheitert:

    ALV.DE  ist Allianz SE.       `ALV`  bei der SEC ist Autoliv.
    DTE.DE  ist Deutsche Telekom. `DTE`  bei der SEC ist DTE Energy.

Beide Ticker existieren, beide Zuordnungen waeren falsch. Die erste
Testgruppe haelt fest, dass sie nicht zustande kommen — und zwar nicht,
weil der Ticker gesondert behandelt wuerde, sondern weil er an der
Entscheidung ueberhaupt nicht beteiligt ist.

Kein Test hier geht ans Netz: `zuordnung_bestimmen` bekommt Firmenname, Land
und Namensindex uebergeben.
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, TickerZuordnung
from services.ticker_zuordnung import (
    manuell_setzen, normalisieren, us_ticker_fuer, zuordnung_bestimmen,
    zuordnung_speichern, zuordnungen_auffrischen,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False,
                           expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# Ausschnitt aus dem echten SEC-Verzeichnis, normalisiert wie im Betrieb.
# Enthaelt die beiden Fallen (Autoliv unter ALV, DTE Energy unter DTE) und
# die Aktienklassen von Alphabet.
INDEX = {
    "NVIDIA": [("NVDA", "0001045810")],
    "ALPHABET": [("GOOGL", "0001652044"), ("GOOG", "0001652044"),
                 ("GOOGM", "0001652044")],
    "ORACLE": [("ORCL", "0001341439"), ("ORCL-PD", "0001341439")],
    "BROADCOM": [("AVGO", "0001730168")],
    "AMAZON": [("AMZN", "0001018724")],
    "AUTOLIV": [("ALV", "0001034670")],
    "DTE ENERGY": [("DTE", "0000936340")],
    # Konstruierter Mehrdeutigkeitsfall: zwei Emittenten, ein Name.
    "ZWILLING": [("ZWA", "0000000001"), ("ZWB", "0000000002")],
}


# ---------------------------------------------------------------------------
# Die Fallen — der Grund fuer dieses Modul
# ---------------------------------------------------------------------------

def test_allianz_bekommt_nicht_autoliv():
    """ALV.DE ist Allianz. `ALV` bei der SEC ist Autoliv."""
    e = zuordnung_bestimmen("ALV.DE", "Allianz SE", "Germany", INDEX)

    assert e["gefunden"] is False
    assert e["cik"] is None
    assert e["us_ticker"] is None
    # Und zwar mit Begruendung, nicht stillschweigend.
    assert "kein SEC-Emittent" in e["begruendung"]


def test_deutsche_telekom_bekommt_nicht_dte_energy():
    """DTE.DE ist Deutsche Telekom. `DTE` bei der SEC ist DTE Energy."""
    e = zuordnung_bestimmen("DTE.DE", "Deutsche Telekom AG", "Germany", INDEX)

    assert e["gefunden"] is False
    assert e["us_ticker"] is None


def test_der_tickerstamm_wird_nirgends_gelesen():
    """Derselbe Firmenname unter beliebigem Kuerzel ergibt dieselbe Zuordnung.

    Das ist die strukturelle Aussage hinter den beiden Tests oben: die
    Entscheidung haengt am Namen, nicht am Ticker. Waere es anders, koennte
    sie fuer ein Kuerzel anders ausfallen als fuer ein anderes.
    """
    a = zuordnung_bestimmen("NVD.DE", "NVIDIA Corporation", "United States",
                            INDEX)
    b = zuordnung_bestimmen("ALV.DE", "NVIDIA Corporation", "United States",
                            INDEX)
    assert a["cik"] == b["cik"] == "0001045810"


# ---------------------------------------------------------------------------
# Die echten Titel der Watchlist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("notierung, name, us_ticker, cik", [
    ("ABEA.DE", "Alphabet Inc.", "GOOG", "0001652044"),
    ("ORC.DE", "Oracle Corporation", "ORCL", "0001341439"),
    ("NVD.DE", "NVIDIA Corporation", "NVDA", "0001045810"),
    ("1YD.DE", "Broadcom Inc.", "AVGO", "0001730168"),
])
def test_frankfurter_notierungen_finden_ihren_emittenten(
        notierung, name, us_ticker, cik):
    e = zuordnung_bestimmen(notierung, name, "United States", INDEX)
    assert e["gefunden"] is True
    assert e["us_ticker"] == us_ticker
    assert e["cik"] == cik


def test_aktienklassen_fallen_auf_eine_cik_zusammen():
    """GOOGL/GOOG/GOOGM sind drei Ticker, ein Emittent — kein Mehrdeutigkeitsfall.

    Deshalb wird die Eindeutigkeit auf CIK-Ebene geprueft und nicht auf
    Tickerebene: sonst faenden gerade die grossen Titel keine Zuordnung.
    """
    e = zuordnung_bestimmen("ABEA.DE", "Alphabet Inc.", "United States", INDEX)
    assert e["gefunden"] is True
    assert e["cik"] == "0001652044"


def test_kuerzester_ticker_gewinnt():
    """Unter Aktienklassen wird die Stammnotierung gewaehlt."""
    e = zuordnung_bestimmen("ABEA.DE", "Alphabet Inc.", "United States", INDEX)
    assert e["us_ticker"] == "GOOG"


# ---------------------------------------------------------------------------
# Lieber keine Zuordnung als die falsche
# ---------------------------------------------------------------------------

def test_mehrdeutigkeit_fuehrt_zu_keiner_zuordnung():
    """Zwei CIKs zu einem Namen: ein Mensch entscheidet, nicht der Zufall."""
    e = zuordnung_bestimmen("XX.DE", "Zwilling AG", "Germany", INDEX)

    assert e["gefunden"] is False
    assert "mehrdeutig" in e["begruendung"]
    # Beide CIKs stehen in der Begruendung, damit die Handeingabe weiss, worum
    # es geht.
    assert "0000000001" in e["begruendung"]
    assert "0000000002" in e["begruendung"]


def test_ohne_firmenname_keine_zuordnung():
    e = zuordnung_bestimmen("XX.DE", None, None, INDEX)
    assert e["gefunden"] is False
    assert "kein Firmenname" in e["begruendung"]


def test_name_der_nur_aus_rechtsform_besteht_zaehlt_nicht():
    """"Inc." allein identifiziert niemanden."""
    e = zuordnung_bestimmen("XX.DE", "Inc.", "United States", INDEX)
    assert e["gefunden"] is False
    assert "kein Firmenname" in e["begruendung"]


def test_jede_nichtzuordnung_traegt_eine_begruendung():
    """Die drei Gruende verlangen verschiedene Reaktionen — sie muessen
    unterscheidbar bleiben."""
    faelle = [
        zuordnung_bestimmen("A.DE", None, None, INDEX),
        zuordnung_bestimmen("B.DE", "Gibt Es Nicht SE", "Germany", INDEX),
        zuordnung_bestimmen("C.DE", "Zwilling AG", "Germany", INDEX),
    ]
    begruendungen = [f["begruendung"] for f in faelle]
    assert all(b for b in begruendungen)
    assert len(set(begruendungen)) == 3


# ---------------------------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("roh, erwartet", [
    ("NVIDIA Corporation", "NVIDIA"),
    ("NVIDIA CORP", "NVIDIA"),
    ("Amazon.com, Inc.", "AMAZON"),
    ("AMAZON COM INC", "AMAZON"),
    ("Alphabet Inc.", "ALPHABET"),
    ("Allianz SE", "ALLIANZ"),
    ("Deutsche Telekom AG", "DEUTSCHE TELEKOM"),
])
def test_normalisierung(roh, erwartet):
    assert normalisieren(roh) == erwartet


def test_yfinance_und_sec_schreibweise_treffen_sich():
    """Der Kern der Sache: zwei Quellen, zwei Schreibweisen, ein Name."""
    assert normalisieren("NVIDIA Corporation") == normalisieren("NVIDIA CORP")
    assert normalisieren("Amazon.com, Inc.") == normalisieren("AMAZON COM INC")


def test_normalisierung_haelt_leeres_aus():
    assert normalisieren(None) == ""
    assert normalisieren("") == ""
    assert normalisieren("   ") == ""


# ---------------------------------------------------------------------------
# Der Nachschlag, den das Dashboard benutzt
# ---------------------------------------------------------------------------

def test_us_ticker_bleibt_er_selbst(db):
    """Ein Ticker ohne Boersenkuerzel braucht keine Zeile."""
    assert us_ticker_fuer(db, "AMZN") == "AMZN"
    assert db.query(TickerZuordnung).count() == 0


def test_notierung_ohne_zeile_ergibt_nichts(db):
    assert us_ticker_fuer(db, "ABEA.DE") is None


def test_gespeicherte_zuordnung_wird_genutzt(db):
    zuordnung_speichern(db, zuordnung_bestimmen(
        "ABEA.DE", "Alphabet Inc.", "United States", INDEX))
    assert us_ticker_fuer(db, "ABEA.DE") == "GOOG"


def test_negative_zuordnung_bleibt_negativ(db):
    """Ein `gefunden=False` ist ein Ergebnis und wird nicht als Treffer gelesen."""
    zuordnung_speichern(db, zuordnung_bestimmen(
        "ALV.DE", "Allianz SE", "Germany", INDEX))
    assert us_ticker_fuer(db, "ALV.DE") is None
    # Aber die Zeile existiert — damit nicht bei jedem Aufruf neu gesucht wird.
    assert db.get(TickerZuordnung, "ALV.DE") is not None


# ---------------------------------------------------------------------------
# Handeingabe
# ---------------------------------------------------------------------------

def test_manuell_schlaegt_automatik(db):
    """Wer von Hand zugeordnet hat, wusste mehr als der Namensabgleich."""
    manuell_setzen(db, "XX.DE", "GOOG", cik="0001652044")
    # Ein automatischer Lauf darf das nicht ueberschreiben.
    zuordnung_speichern(db, {
        "notierung": "XX.DE", "cik": "9999999999", "us_ticker": "FALSCH",
        "firmenname": None, "land": None, "gefunden": True,
        "begruendung": "automatisch"}, quelle="auto-name")

    zeile = db.get(TickerZuordnung, "XX.DE")
    assert zeile.quelle == "manuell"
    assert zeile.us_ticker == "GOOG"


def test_manuelle_zuordnung_kann_manuell_geaendert_werden(db):
    manuell_setzen(db, "XX.DE", "GOOG", cik="0001652044")
    manuell_setzen(db, "XX.DE", "ORCL", cik="0001341439")
    assert db.get(TickerZuordnung, "XX.DE").us_ticker == "ORCL"


# ---------------------------------------------------------------------------
# Der Lauf
# ---------------------------------------------------------------------------

def test_bereits_geprueftes_wird_nicht_erneut_erfragt(db):
    """Auch ein Nichttreffer ist ein Ergebnis — sonst fragt jeder Lauf neu."""
    zuordnung_speichern(db, zuordnung_bestimmen(
        "ALV.DE", "Allianz SE", "Germany", INDEX))
    statistik = zuordnungen_auffrischen(db, ["ALV.DE", "AMZN"])

    # Nichts zu tun: ALV.DE ist geprueft, AMZN braucht keine Zuordnung.
    assert statistik["geprueft"] == 0
    assert statistik["uebersprungen"] == 2


def test_us_ticker_werden_uebersprungen(db):
    statistik = zuordnungen_auffrischen(db, ["AMZN", "NVDA"])
    assert statistik["geprueft"] == 0
    assert db.query(TickerZuordnung).count() == 0


def test_ohne_namensindex_wird_nichts_geschrieben(db, monkeypatch):
    """Ein SEC-Ausfall darf keine leeren Zuordnungen hinterlassen.

    Sonst stuende nach einem Netzproblem fuer jeden Titel `gefunden=False` im
    Bestand, und der naechste Lauf ueberspraenge ihn als geprueft.
    """
    monkeypatch.setattr("services.ticker_zuordnung.sec_namensindex",
                        lambda: {})
    statistik = zuordnungen_auffrischen(db, ["ABEA.DE"])

    assert statistik["neu"] == 0
    assert db.query(TickerZuordnung).count() == 0
