"""
tests/test_universum.py — Universumszuschnitt und Abdeckung (Auftrag C).

Geprüft wird das, was diesen Zuschnitt still falsch machen würde: ein ETF, der
als Stammaktie durchgeht; ein Emittent, der aus der Punkt-in-Zeit-Liste fällt,
weil er heute nicht mehr gelistet ist (dann wäre die Liste genau das, was sie
ersetzen soll); ein Cluster-Kennzeichen, das dieselbe Person doppelt zählt;
und eine Abdeckungsquote, die eine survivorship-verseuchte Messung als
vollständig ausweist.

Die Archivform ist dieselbe wie in `tests/test_insider.py` — sie wurde am
2026-09-04 gegen den echten Datensatz 2024Q1 geprüft.
"""

from datetime import datetime

import pandas as pd
import pytest

from services.universum import (
    BOERSEN, _AUSSCHLUSS, abdeckung, abdeckung_text, emittenten_aus_archiv,
)
from tests.test_insider import _archiv, _einreichung, _geschaeft, _meldender


# ---------------------------------------------------------------------------
# Der Namensfilter: was ist ein Unternehmensanteil, was nicht
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "Apple Inc. - Common Stock",
    "Ford Motor Company Common Stock",
    "Berkshire Hathaway Inc. Class B",
    "Realty Income Corporation Common Stock",   # REIT, aber eine Aktie
])
def test_stammaktien_bleiben(name):
    assert not _AUSSCHLUSS.search(name), name


@pytest.mark.parametrize("name", [
    "State Street SPDR Dow Jones Industrial Average ETF Trust",
    "iShares Total USD Fixed Income Market ETF",
    "Aptus April Deep Buffer ETF",
    "John Hancock Financial Opportunities Fund Common Stock",
    "Jones Ventures INTL Acquisition1 Corp - Warrants",
    "Jones Ventures INTL Acquisition1 Corp - Units",
    "Jones Ventures INTL Acquisition1 Corp - Rights",
    "MAX Airlines 3X Leveraged ETNs",
    "Bank of America Corp - Depositary Shares",
])
def test_nicht_stammaktien_fallen_raus(name):
    assert _AUSSCHLUSS.search(name), name


def test_boersen_ohne_etf_plaetze():
    """NYSE ARCA und BATS sind ETF-Plätze und gehören nicht in ein Aktienuniversum.

    Der Filter läuft über die Börse und den Namen. Fiele die Börsenstufe weg,
    blieben rund 4.300 Fondszeilen übrig, die der Namensfilter nur teilweise
    fängt — ein ETF ohne 'ETF' im Namen gibt es durchaus.
    """
    assert "NYSE ARCA" not in BOERSEN
    assert "BATS" not in BOERSEN
    assert "OTC" not in BOERSEN
    assert set(BOERSEN) == {"NASDAQ", "NYSE", "AMEX"}


# ---------------------------------------------------------------------------
# Die Punkt-in-Zeit-Liste: sie darf Überlebende NICHT bevorzugen
# ---------------------------------------------------------------------------

def test_emittent_ohne_kauf_wird_trotzdem_gefuehrt():
    """Wer Form 4 eingereicht hat, existierte — auch ohne Marktkauf.

    Die Liste beantwortet 'welche Ticker gab es damals', nicht 'welche sind
    interessant'. Ein Filter auf Kaufaktivität würde genau die Firmen
    entfernen, deren Fehlen die Abdeckungsrechnung messen soll.
    """
    daten = _archiv([_einreichung(ticker="TOTE")], [_meldender()],
                    [_geschaeft(code="S")])
    ergebnis = emittenten_aus_archiv(daten)
    assert "TOTE" in ergebnis
    assert ergebnis["TOTE"]["kauf"] is False
    assert ergebnis["TOTE"]["cluster"] is False


def test_kein_universumsfilter():
    """Anders als `geschaefte_aus_archiv` filtert diese Funktion nicht.

    Sie ist der einzige Ort im Projekt, der einen Ticker sieht, den kein
    heutiges Verzeichnis mehr kennt. Ein Universumsargument hier wäre der
    Zirkelschluss, den die Tabelle auflösen soll.
    """
    daten = _archiv(
        [_einreichung(nummer="a", ticker="AAPL"),
         _einreichung(nummer="b", ticker="XYZDELISTED")],
        [_meldender(nummer="a"), _meldender(nummer="b", cik="2")],
        [_geschaeft(nummer="a", sk="1"), _geschaeft(nummer="b", sk="2")])
    ergebnis = emittenten_aus_archiv(daten)
    assert set(ergebnis) == {"AAPL", "XYZDELISTED"}


def test_cluster_verlangt_zwei_verschiedene_personen():
    """Zwei Käufe derselben Person sind ein Käufer, keine Gruppe.

    Das ist das Kriterium aus §2n. Würde nach Zeilen statt nach Personen
    gezählt, machte ein einzelner Insider mit einem gestückelten Kauf jede
    Firma zum Cluster — und die Gruppe verlöre ihre Bedeutung.
    """
    daten = _archiv(
        [_einreichung(nummer="a", ticker="EINS"),
         _einreichung(nummer="b", ticker="EINS")],
        [_meldender(nummer="a", cik="0001111111"),
         _meldender(nummer="b", cik="0001111111")],   # dieselbe Person
        [_geschaeft(nummer="a", sk="1"), _geschaeft(nummer="b", sk="2")])
    ergebnis = emittenten_aus_archiv(daten)
    assert ergebnis["EINS"]["kauf"] is True
    assert ergebnis["EINS"]["cluster"] is False


def test_cluster_bei_zwei_personen():
    daten = _archiv(
        [_einreichung(nummer="a", ticker="ZWEI"),
         _einreichung(nummer="b", ticker="ZWEI")],
        [_meldender(nummer="a", cik="0001111111"),
         _meldender(nummer="b", cik="0002222222")],
        [_geschaeft(nummer="a", sk="1"), _geschaeft(nummer="b", sk="2")])
    assert emittenten_aus_archiv(daten)["ZWEI"]["cluster"] is True


def test_verkauf_macht_kein_cluster():
    """Die Hypothese ist der KAUF. Zwei Verkäufer sind das Gegenteil."""
    daten = _archiv(
        [_einreichung(nummer="a", ticker="RAUS"),
         _einreichung(nummer="b", ticker="RAUS")],
        [_meldender(nummer="a", cik="1"), _meldender(nummer="b", cik="2")],
        [_geschaeft(nummer="a", sk="1", code="S"),
         _geschaeft(nummer="b", sk="2", code="S")])
    ergebnis = emittenten_aus_archiv(daten)
    assert ergebnis["RAUS"]["kauf"] is False
    assert ergebnis["RAUS"]["cluster"] is False


def test_widerspruechliche_erwerbskennung_zaehlt_nicht():
    """0,19 % der echten Zeilen kennzeichnen ein P als Veräußerung.

    Dieselbe Prüfung wie in `services/insider.py`. Ohne sie zählte eine
    widersprüchliche Zeile als Käufer und könnte allein ein Cluster erzeugen.
    """
    daten = _archiv(
        [_einreichung(nummer="a", ticker="KRUM"),
         _einreichung(nummer="b", ticker="KRUM")],
        [_meldender(nummer="a", cik="1"), _meldender(nummer="b", cik="2")],
        [_geschaeft(nummer="a", sk="1"),
         _geschaeft(nummer="b", sk="2", ad="D")])   # P, aber als Abgang
    ergebnis = emittenten_aus_archiv(daten)
    assert ergebnis["KRUM"]["kauf"] is True
    assert ergebnis["KRUM"]["cluster"] is False


def test_nur_form_vier():
    """Form 3 ist der Ersteintrag beim Amtsantritt, keine Handelsentscheidung."""
    daten = _archiv([_einreichung(ticker="NURDREI", typ="3")],
                    [_meldender()], [_geschaeft()])
    assert emittenten_aus_archiv(daten) == {}


# ---------------------------------------------------------------------------
# Die Abdeckungsrechnung
# ---------------------------------------------------------------------------

class _Satz:
    """Ein EmittentPunktInZeit-Doppel ohne Datenbank."""

    def __init__(self, ticker, erstes="2016q1", letztes="2019q4",
                 cluster=0, gelistet=False):
        self.ticker = ticker
        self.erstes_quartal = erstes
        self.letztes_quartal = letztes
        self.quartale_aktiv = 4
        self.quartale_mit_kauf = cluster
        self.quartale_mit_cluster = cluster
        self.heute_gelistet = gelistet
        self.heute_boerse = "NASDAQ" if gelistet else None


class _DB:
    def __init__(self, saetze):
        self._saetze = saetze

    def query(self, *args):
        return self

    def __iter__(self):
        return iter(self._saetze)


def test_abdeckung_erkennt_die_ueberlebendenauswahl():
    """Der Kern von Auftrag C: die Zahl, die eine Messung ehrlich macht.

    Gesehen werden zwei Ticker, die beide überlebt haben; die zwei fehlenden
    sind beide verschwunden. Genau das ist die Lage von §2n (99,6 % der
    gemessenen Ticker gelistet, 45 % des Bestandes) — und die Rechnung muss
    sie sichtbar machen, statt eine Abdeckung von 50 % als unauffällig
    auszuweisen.
    """
    db = _DB([
        _Satz("LEBT1", gelistet=True), _Satz("LEBT2", gelistet=True),
        _Satz("TOT1", cluster=2), _Satz("TOT2", cluster=1),
    ])
    werte = abdeckung(db, ["LEBT1", "LEBT2"], von_jahr=2016, bis_jahr=2019)

    assert werte["universum"] == 4
    assert werte["gesehen"] == 2
    assert werte["anteil"] == 0.5
    assert werte["fehlend"] == 2
    assert werte["ueberlebensquote_gesehen"] == 1.0
    assert werte["ueberlebensquote_fehlend"] == 0.0
    # Beide fehlenden hatten einen Clusterkauf — das ist die Teilmenge, die
    # den Befund aus §2n direkt betrifft.
    assert werte["fehlend_mit_cluster"] == 2


def test_abdeckung_ohne_bestand_meldet_null_statt_hundert():
    """Ein leerer Punkt-in-Zeit-Bestand darf nicht als volle Abdeckung gelten.

    Der stille Fehler wäre: 0 von 0 gesehen ergibt rechnerisch keine Lücke,
    und die Messung sähe survivorship-frei aus, weil nie jemand nachgesehen hat.
    """
    werte = abdeckung(_DB([]), ["AAPL"])
    assert werte["universum"] == 0
    assert werte["anteil"] == 0.0
    assert "unbekannt" in abdeckung_text(werte)


def test_abdeckung_zaehlt_ueberlappende_emittenten_mit():
    """Wer 2014 anfing und 2018 noch da war, gehört in den Vergleich 2016-2019.

    Ohne die Überlappungsbedingung fielen alle Altfälle heraus — und das sind
    genau die mit der längsten Gelegenheit zu verschwinden.
    """
    db = _DB([_Satz("ALT", erstes="2014q1", letztes="2018q2", gelistet=False)])
    werte = abdeckung(db, [], von_jahr=2016, bis_jahr=2019)
    assert werte["universum"] == 1


def test_abdeckung_text_nennt_beide_quoten():
    db = _DB([_Satz("A", gelistet=True), _Satz("B", gelistet=False)])
    text = abdeckung_text(abdeckung(db, ["A"], von_jahr=2016, bis_jahr=2019))
    assert "1 von 2" in text
    assert "%" in text
