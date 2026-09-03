"""
tests/test_kurshistorie.py — Die Kursreihe als eigener Bestand (BC-04, Schritt 1).

Geprüft wird das, was hier tatsächlich Schaden anrichten kann. Das Modul
**löscht**, bevor es schreibt — die einzige Stelle im Projekt, die einen
Bestand ersetzt statt ergänzt. Zwei Fehler wären teuer und beide still:

  * ein leerer Abruf, der einen vorhandenen Bestand wegräumt,
  * ein Mischbestand aus zwei Abrufen, der zwei Anpassungsbasen trüge und von
    außen wie eine Reihe aussähe (Split-Artefakte in jedem Kursverhältnis).

Dazu die Umwandlung aus dem DataFrame, wo NaN-Kurse und zeitzonenbehaftete
Indizes die realistischen Eingaben sind: yfinance liefert US-Ticker in
`America/New_York`, und ein Handelstag ohne Schlusskurs ist keine Beobachtung.

Anders als die übrigen Testdateien braucht diese eine Session. Sie legt dafür
eine eigene In-Memory-Datenbank an — die Datei unter `data/` wird nicht
berührt.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, KursHistorie
from services.kurshistorie import (
    bestand, fehlende_ticker, reihe_lesen, reihe_speichern, schlusskurs_paare,
    zeilen_aus_dataframe, zeilen_speichern,
)


@pytest.fixture
def db():
    """Frische In-Memory-Datenbank je Test."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False,
                           expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _zeilen(anzahl: int, start: datetime | None = None,
            kurs: float = 100.0) -> list[tuple]:
    """Aufeinanderfolgende Handelstage mit steigendem Kurs."""
    beginn = start or datetime(2024, 1, 1)
    return [
        (beginn + timedelta(days=i), kurs + i, kurs + i + 1.0,
         kurs + i - 1.0, kurs + i + 0.5, 1000.0 + i)
        for i in range(anzahl)
    ]


# ---------------------------------------------------------------------------
# Umwandlung aus dem DataFrame
# ---------------------------------------------------------------------------

def test_zeile_ohne_schlusskurs_entfaellt():
    """NaN im Close ist kein Kurs von null, sondern keine Beobachtung.

    `schluss` ist die einzige nicht-nullbare Spalte der Tabelle. Ginge eine
    NaN-Zeile durch, stünde sie entweder als 0.0 im Bestand — ein Kurssturz
    auf null, den es nie gab — oder der ganze Block scheiterte am
    NOT-NULL-Constraint.
    """
    rahmen = pd.DataFrame(
        {"Open": [10.0, 11.0], "High": [11.0, 12.0], "Low": [9.0, 10.0],
         "Close": [10.5, float("nan")], "Volume": [100.0, 200.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    zeilen = zeilen_aus_dataframe(rahmen)
    assert len(zeilen) == 1
    assert zeilen[0][0] == datetime(2024, 1, 2)
    assert zeilen[0][4] == 10.5


def test_fehlendes_volumen_bleibt_none_und_kippt_die_zeile_nicht():
    """Ein Handelsplatz ohne Volumenmeldung ist ein Normalfall.

    Die Zeile muss erhalten bleiben — sonst verlöre man ganze Titel, weil
    eine einzelne Spalte fehlt. Und None muss von 0.0 unterscheidbar sein:
    "kein Umsatz gemeldet" ist nicht "kein Umsatz gehandelt".
    """
    rahmen = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.0], "Close": [10.5],
         "Volume": [float("nan")]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    zeilen = zeilen_aus_dataframe(rahmen)
    assert len(zeilen) == 1
    assert zeilen[0][5] is None


def test_zeitzone_wird_abgestreift():
    """yfinance liefert US-Ticker tz-bewusst, SQLite speichert keine Zeitzone.

    Bliebe der Versatz stehen, verglichen sich Kursdatum und
    `snapshot_zeitpunkt` um Stunden verschoben. Bei einem 280-Tage-Fenster
    fällt das nicht auf, bei einem Tagesabstand schon.
    """
    index = pd.to_datetime(["2024-01-02 09:30"]).tz_localize("America/New_York")
    rahmen = pd.DataFrame({"Close": [10.5]}, index=index)
    zeilen = zeilen_aus_dataframe(rahmen)
    assert zeilen[0][0].tzinfo is None
    assert zeilen[0][0] == datetime(2024, 1, 2, 9, 30)


def test_dataframe_ohne_close_liefert_nichts():
    rahmen = pd.DataFrame({"Open": [10.0]}, index=pd.to_datetime(["2024-01-02"]))
    assert zeilen_aus_dataframe(rahmen) == []


def test_leere_eingaben_liefern_nichts():
    assert zeilen_aus_dataframe(None) == []
    assert zeilen_aus_dataframe(pd.DataFrame()) == []


# ---------------------------------------------------------------------------
# Ersetzen statt ergänzen — die gefährliche Stelle
# ---------------------------------------------------------------------------

def test_reihe_wird_vollstaendig_ersetzt(db):
    """Zwei Abrufe dürfen keinen Mischbestand ergeben.

    Nach einem Split trägt dieselbe historische Zeile aus einem späteren
    Abruf einen anderen Wert. Blieben beide stehen, wäre jedes Kursverhältnis
    zwischen ihnen ein Split-Artefakt — und von außen nicht als solches
    erkennbar.
    """
    zeilen_speichern(db, "AAPL", _zeilen(5), quelle="lauf-1")
    assert bestand(db, "AAPL")["zeilen"] == 5

    # Zweiter Abruf: andere Anpassungsbasis, kürzere Reihe.
    geschrieben = zeilen_speichern(db, "AAPL", _zeilen(3, kurs=50.0),
                                   quelle="lauf-2")

    assert geschrieben == 3
    reihe = reihe_lesen(db, "AAPL")
    assert len(reihe) == 3
    assert {z.quelle for z in reihe} == {"lauf-2"}
    assert all(z.schluss < 100.0 for z in reihe)


def test_leerer_abruf_loescht_den_bestand_nicht(db):
    """Der teuerste denkbare Ausgang, und er wäre still.

    Ein fehlgeschlagener Abruf liefert einen leeren DataFrame. Würde daraus
    ein Ersetzen mit null Zeilen, wäre ein vollständiger Zehn-Jahres-Bestand
    weg, ohne dass irgendwo ein Fehler stünde.
    """
    zeilen_speichern(db, "AAPL", _zeilen(5))

    assert zeilen_speichern(db, "AAPL", []) == 0

    assert bestand(db, "AAPL")["zeilen"] == 5


def test_leerer_dataframe_loescht_den_bestand_nicht(db):
    """Derselbe Schutz auf dem Weg, den der Backfill tatsächlich nimmt."""
    zeilen_speichern(db, "AAPL", _zeilen(5))
    assert reihe_speichern(db, "AAPL", pd.DataFrame()) == 0
    assert bestand(db, "AAPL")["zeilen"] == 5


def test_doppelte_handelstage_werden_zusammengefasst(db):
    """Sonst rollt die Unique-Bedingung den ganzen Block zurück.

    Doppelte Zeilen kommen aus Zeitzonenwechseln und aus dem Abruf selbst.
    Ein einzelner Dublettentag würde ohne diese Zusammenfassung den gesamten
    Ticker verlieren — nicht nur den Tag.
    """
    tag = datetime(2024, 1, 2)
    zeilen = [
        (tag, 10.0, 11.0, 9.0, 10.5, 100.0),
        (tag, 10.0, 11.0, 9.0, 99.9, 200.0),   # gewinnt: der letzte Wert
        (datetime(2024, 1, 3), 11.0, 12.0, 10.0, 11.5, 150.0),
    ]
    assert zeilen_speichern(db, "TEST", zeilen) == 2

    reihe = reihe_lesen(db, "TEST")
    assert len(reihe) == 2
    assert reihe[0].schluss == 99.9


def test_andere_ticker_bleiben_unberuehrt(db):
    """Das Löschen filtert auf den Ticker — sonst räumt ein Abruf alles ab."""
    zeilen_speichern(db, "AAPL", _zeilen(4))
    zeilen_speichern(db, "MSFT", _zeilen(6))

    zeilen_speichern(db, "AAPL", _zeilen(2))

    assert bestand(db, "AAPL")["zeilen"] == 2
    assert bestand(db, "MSFT")["zeilen"] == 6


def test_ticker_ohne_namen_schreibt_nichts(db):
    assert zeilen_speichern(db, "", _zeilen(3)) == 0
    assert bestand(db)["zeilen"] == 0


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------

def test_reihe_kommt_aufsteigend_zurueck(db):
    """Jedes gleitende Mittel setzt die Sortierung voraus.

    `stetige_indikatoren.gleitender_mittelwert()` läuft die Reihe von hinten
    ab und bricht am Fensterrand ab — auf einer unsortierten Reihe endet das
    Fenster an der falschen Stelle.
    """
    zeilen = _zeilen(5)
    zeilen_speichern(db, "AAPL", list(reversed(zeilen)))

    daten = [z.datum for z in reihe_lesen(db, "AAPL")]
    assert daten == sorted(daten)


def test_bis_ist_einschliessend(db):
    """Der Kurs des Stichtags ist an diesem Tag bekannt.

    Dieselbe Festlegung wie in `services/stetige_indikatoren.py`: ein
    gleitendes Mittel schließt den Stichtag per Definition ein. Ein
    ausschließendes `bis` wäre kein Schutz vor Look-ahead, sondern ein
    Off-by-one.
    """
    zeilen_speichern(db, "AAPL", _zeilen(5, start=datetime(2024, 1, 1)))

    paare = schlusskurs_paare(db, "AAPL", bis=datetime(2024, 1, 3))

    assert len(paare) == 3
    assert paare[-1][0] == datetime(2024, 1, 3)


def test_schlusskurs_paare_haben_die_erwartete_form(db):
    """Die Form, die `gleitender_mittelwert()` erwartet: (Zeitpunkt, Kurs)."""
    zeilen_speichern(db, "AAPL", _zeilen(3))
    paare = schlusskurs_paare(db, "AAPL")
    assert len(paare) == 3
    assert all(isinstance(p[0], datetime) and isinstance(p[1], float)
               for p in paare)


def test_bestand_meldet_zeitraum_und_abdeckung(db):
    zeilen_speichern(db, "AAPL", _zeilen(5, start=datetime(2024, 1, 1)))
    zeilen_speichern(db, "MSFT", _zeilen(3, start=datetime(2023, 6, 1)))

    gesamt = bestand(db)
    assert gesamt["zeilen"] == 8
    assert gesamt["ticker"] == 2
    assert gesamt["von"] == datetime(2023, 6, 1)
    assert gesamt["bis"] == datetime(2024, 1, 5)


def test_leerer_bestand_meldet_nullen_statt_none(db):
    """Eine Kontrollausgabe darf nicht an einer leeren Datenbank scheitern."""
    assert bestand(db) == {"zeilen": 0, "ticker": 0, "von": None, "bis": None}


def test_fehlende_ticker_nennt_nur_die_leeren(db):
    """Der Wiederaufnahmepunkt eines abgebrochenen Durchlaufs."""
    zeilen_speichern(db, "AAPL", _zeilen(2))
    assert fehlende_ticker(db, ["AAPL", "MSFT", "SAP.DE"]) == ["MSFT", "SAP.DE"]
    assert fehlende_ticker(db, []) == []
