"""
tests/test_groesse.py — Groessenklassen fuer die Gegenprobe zu §2p.

Diese Schichtung entscheidet ueber den staerksten Befund des Projekts: traegt
die Nettoemission noch etwas, wenn man nur Titel gleicher Groesse vergleicht,
oder war §2p ein Groesseneffekt in anderer Verpackung? Ein Fehler hier wuerde
nicht auffallen — er faelschte eine Gegenprobe, nicht eine Anzeige.

Drei Eigenschaften tragen das Ergebnis, und alle drei sind hier festgehalten:

  * **Kein Look-ahead.** Das Umsatzfenster endet am Tag VOR dem Stichtag. Ein
    Umsatzsprung am Stichtag selbst darf die Klasse nicht mehr beeinflussen —
    sonst ordnete die Messung genau die Ereignisse ein, die sie vorhersagen
    soll.
  * **Split-Immunitaet.** Der Dollar-Umsatz ist gewaehlt, WEIL Kurs und
    Volumen dieselbe Bereinigung tragen und ihr Produkt den Split uebersteht.
    Faellt diese Eigenschaft, ist das Mass so kaputt wie die
    Marktkapitalisierung, die aus genau diesem Grund verworfen wurde.
  * **Ein Titel, eine Stimme.** Ein haeufig beobachteter Titel darf den
    Querschnitt nicht mehrfach besetzen, gegen den alle anderen gemessen
    werden.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, KursHistorie
from services.cross_sectional_momentum import raenge_je_woche
from snapshot_engine.auswertung.groesse import (
    FENSTER_TAGE, MIN_TAGE, dollar_umsatz_je_beobachtung, groessen_klasse,
    groessen_klassen,
)


@pytest.fixture
def db():
    """Frische In-Memory-Datenbank je Test — `data/` wird nicht beruehrt."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False,
                           expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _reihe(db, ticker: str, tage: int, kurs: float = 100.0,
           volumen: float = 1_000.0, start: datetime | None = None) -> None:
    """Aufeinanderfolgende Handelstage mit konstantem Kurs und Volumen."""
    beginn = start or datetime(2024, 1, 1)
    db.add_all([
        KursHistorie(ticker=ticker, datum=beginn + timedelta(days=i),
                     schluss=kurs, volumen=volumen, angepasst=True,
                     quelle="test")
        for i in range(tage)
    ])
    db.commit()


# ---------------------------------------------------------------------------
# Look-ahead — die teuerste denkbare Verwechslung
# ---------------------------------------------------------------------------

def test_der_stichtag_selbst_zaehlt_nicht_mit(db):
    """Ein Umsatzsprung AM Stichtag darf die Klasse nicht mehr beeinflussen."""
    _reihe(db, "AAA", tage=100, kurs=10.0, volumen=1_000.0)
    # Der Stichtag ist Tag 60; dort explodiert der Umsatz um das Tausendfache.
    stichtag = datetime(2024, 1, 1) + timedelta(days=60)
    zeile = (db.query(KursHistorie)
             .filter(KursHistorie.ticker == "AAA")
             .filter(KursHistorie.datum == stichtag).one())
    zeile.volumen = 1_000_000.0
    db.commit()

    werte = dollar_umsatz_je_beobachtung(db, {1: ("AAA", stichtag)})

    # 10 x 1.000 = 10.000 je Tag — der Sprung liegt ausserhalb des Fensters.
    assert werte[1] == pytest.approx(10_000.0)


def test_nur_tage_vor_dem_stichtag_im_fenster(db):
    """Die Trennung liegt exakt am Stichtag, nicht einen Tag daneben."""
    _reihe(db, "AAA", tage=30, kurs=10.0, volumen=1_000.0)
    # Ab Tag 30 ein zehnfacher Umsatz.
    _reihe(db, "AAA", tage=30, kurs=10.0, volumen=10_000.0,
           start=datetime(2024, 1, 31))

    # Stichtag genau am ersten teuren Tag: nur die billigen Tage zaehlen.
    werte = dollar_umsatz_je_beobachtung(
        db, {1: ("AAA", datetime(2024, 1, 31))}, fenster=30)
    assert werte[1] == pytest.approx(10_000.0)

    # Einen Tag spaeter ist genau ein teurer Tag im Fenster.
    werte = dollar_umsatz_je_beobachtung(
        db, {1: ("AAA", datetime(2024, 2, 1))}, fenster=30)
    erwartet = (29 * 10_000.0 + 1 * 100_000.0) / 30
    assert werte[1] == pytest.approx(erwartet)


# ---------------------------------------------------------------------------
# Split-Immunitaet — der Grund fuer die Wahl des Masses
# ---------------------------------------------------------------------------

def test_der_split_veraendert_den_dollar_umsatz_nicht(db):
    """Kurs /10 und Volumen x10 lassen das Produkt unveraendert.

    Genau diese Eigenschaft trennt den Dollar-Umsatz von der
    Marktkapitalisierung: dort trifft eine rueckwirkend bereinigte Kursreihe
    auf eine rohe Aktienzahl, und der Fehler ist der Splitfaktor.
    """
    _reihe(db, "VOR", tage=60, kurs=1_000.0, volumen=100.0)
    _reihe(db, "NACH", tage=60, kurs=100.0, volumen=1_000.0)

    stichtag = datetime(2024, 1, 1) + timedelta(days=60)
    werte = dollar_umsatz_je_beobachtung(
        db, {1: ("VOR", stichtag), 2: ("NACH", stichtag)})

    assert werte[1] == pytest.approx(werte[2])
    assert werte[1] == pytest.approx(100_000.0)


# ---------------------------------------------------------------------------
# Ausschluesse: lieber keine Klasse als eine falsche
# ---------------------------------------------------------------------------

def test_zu_kurzes_fenster_bekommt_keinen_wert(db):
    """Unter `MIN_TAGE` belegten Tagen ist der Mittelwert ein Zufall."""
    _reihe(db, "NEU", tage=MIN_TAGE - 1)
    stichtag = datetime(2024, 1, 1) + timedelta(days=MIN_TAGE + 5)
    assert dollar_umsatz_je_beobachtung(db, {1: ("NEU", stichtag)}) == {}


def test_genau_die_mindestzahl_reicht(db):
    """Die Grenze schliesst nicht eins zu viel aus."""
    _reihe(db, "NEU", tage=MIN_TAGE, volumen=1_000.0, kurs=10.0)
    stichtag = datetime(2024, 1, 1) + timedelta(days=MIN_TAGE)
    werte = dollar_umsatz_je_beobachtung(db, {1: ("NEU", stichtag)})
    assert werte[1] == pytest.approx(10_000.0)


def test_ticker_ohne_reihe_faellt_still_heraus(db):
    """Kein Eintrag, keine Klasse — und keine Ausnahme."""
    assert dollar_umsatz_je_beobachtung(
        db, {1: ("FEHLT", datetime(2024, 3, 1))}) == {}


def test_durchgehend_umsatzloser_titel_bekommt_keinen_wert(db):
    """Umsatz null ist keine Groesse, sondern eine fehlende Angabe."""
    _reihe(db, "TOT", tage=100, kurs=10.0, volumen=0.0)
    stichtag = datetime(2024, 1, 1) + timedelta(days=80)
    assert dollar_umsatz_je_beobachtung(db, {1: ("TOT", stichtag)}) == {}


def test_umsatzlose_tage_senken_den_mittelwert(db):
    """Handelslose Tage bleiben drin — sie sind eine echte Eigenschaft.

    Wer sie herausfiltert, macht illiquide Titel kuenstlich liquider und
    verschiebt sie genau in die Klasse, aus der die Schichtung sie trennen
    soll.
    """
    _reihe(db, "DUENN", tage=30, kurs=10.0, volumen=1_000.0)
    _reihe(db, "DUENN", tage=30, kurs=10.0, volumen=0.0,
           start=datetime(2024, 1, 31))

    stichtag = datetime(2024, 1, 1) + timedelta(days=60)
    werte = dollar_umsatz_je_beobachtung(db, {1: ("DUENN", stichtag)},
                                         fenster=60)
    assert werte[1] == pytest.approx(5_000.0)


# ---------------------------------------------------------------------------
# Die Klassenskala
# ---------------------------------------------------------------------------

def test_klasse_eins_ist_die_kleinste():
    """Die Richtung ist entgegengesetzt zu `quintil` in `nettoemission.py`."""
    assert groessen_klasse(0.0) == 1
    assert groessen_klasse(100.0) == 5


@pytest.mark.parametrize("rang, erwartet", [
    (0.0, 1), (19.99, 1), (20.0, 2), (39.99, 2), (40.0, 3),
    (59.99, 3), (60.0, 4), (79.99, 4), (80.0, 5), (100.0, 5),
])
def test_klassengrenzen(rang, erwartet):
    assert groessen_klasse(rang, klassen=5) == erwartet


def test_kein_rang_keine_klasse():
    assert groessen_klasse(None) is None


def test_klassenzahl_ist_einstellbar():
    assert groessen_klasse(0.0, klassen=10) == 1
    assert groessen_klasse(95.0, klassen=10) == 10


# ---------------------------------------------------------------------------
# Der Querschnitt je Woche
# ---------------------------------------------------------------------------

def _gruppe(_ticker: str) -> str:
    """Alle Titel auf einem Handelsplatz — die Trennung wird separat geprueft."""
    return "US"


def test_ein_titel_besetzt_den_querschnitt_nur_einmal():
    """Sonst verschoebe ein haeufig beobachteter Titel die Verteilung."""
    montag = datetime(2024, 1, 1)
    # AAA liegt dreimal in derselben Woche, BBB..TTT je einmal.
    zuordnung = {1: ("AAA", montag), 2: ("AAA", montag + timedelta(days=1)),
                 3: ("AAA", montag + timedelta(days=2))}
    werte = {1: 5.0, 2: 5.0, 3: 5.0}
    for i, name in enumerate("BCDEFGHIJKLMNOPQRSTU", start=4):
        zuordnung[i] = (name * 3, montag)
        werte[i] = float(i)

    raenge = raenge_je_woche(werte, zuordnung, _gruppe, minimum=20)

    # Alle drei AAA-Beobachtungen erben denselben Rang.
    assert raenge[1] == raenge[2] == raenge[3]


def test_zu_duenner_querschnitt_bekommt_keinen_rang():
    """Unter `minimum` Titeln ist ein Rang eine Scheinaussage."""
    montag = datetime(2024, 1, 1)
    zuordnung = {1: ("AAA", montag), 2: ("BBB", montag)}
    assert raenge_je_woche({1: 1.0, 2: 2.0}, zuordnung, _gruppe,
                           minimum=20) == {}


def test_der_rang_gilt_je_woche_nicht_ueber_die_jahre():
    """Ein Titel, dessen Umsatz mit dem Markt mitwaechst, behaelt seine Klasse.

    Sonst wiese die Schichtung das Wachstum der Boersenumsaetze als
    Groessenwechsel aus und ordnete jeden alten Stichtag in die kleinen
    Klassen ein.
    """
    frueh = datetime(2016, 1, 4)
    spaet = datetime(2024, 1, 1)
    zuordnung: dict[int, tuple] = {}
    werte: dict[int, float] = {}

    # Zwei Wochen, in der spaeten ist jeder Umsatz hundertfach.
    for i in range(20):
        zuordnung[i] = (f"T{i:02d}", frueh)
        werte[i] = float(i + 1)
    for i in range(20, 40):
        zuordnung[i] = (f"T{i - 20:02d}", spaet)
        werte[i] = float(i - 19) * 100.0

    raenge = raenge_je_woche(werte, zuordnung, _gruppe, minimum=20)

    # Derselbe Titel steht in beiden Wochen an derselben Stelle.
    assert raenge[0] == raenge[20]
    assert raenge[19] == raenge[39]


def test_handelsplaetze_werden_getrennt_gerangt():
    """Eine gemeinsame Liste wiese den Waehrungsunterschied als Groesse aus."""
    montag = datetime(2024, 1, 1)
    zuordnung: dict[int, tuple] = {}
    werte: dict[int, float] = {}
    for i in range(20):
        zuordnung[i] = (f"US{i:02d}", montag)
        werte[i] = float(i + 1) * 1_000.0
    for i in range(20, 40):
        zuordnung[i] = (f"DE{i - 20:02d}", montag)
        werte[i] = float(i - 19)

    def platz(ticker: str) -> str:
        return "DE" if ticker.startswith("DE") else "US"

    raenge = raenge_je_woche(werte, zuordnung, platz, minimum=20)

    # Trotz tausendfach kleinerer Umsaetze deckt die DE-Gruppe die volle Skala
    # ab — sie wird gegen sich selbst gerangt, nicht gegen die US-Titel.
    de = [raenge[i] for i in range(20, 40)]
    assert min(de) == pytest.approx(0.0)
    assert max(de) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Der Durchstich
# ---------------------------------------------------------------------------

def test_groessen_klassen_ordnet_nach_umsatz_ein(db):
    """Der grosse Titel landet oben, der kleine unten — ueber den ganzen Weg."""
    stichtag = datetime(2024, 4, 1)
    zuordnung = {}
    for i in range(25):
        ticker = f"T{i:02d}"
        # Umsatz steigt streng mit dem Index.
        _reihe(db, ticker, tage=FENSTER_TAGE + 10, kurs=10.0,
               volumen=1_000.0 * (i + 1),
               start=stichtag - timedelta(days=FENSTER_TAGE + 10))
        zuordnung[i] = (ticker, stichtag)

    klassen, werte = groessen_klassen(db, zuordnung, _gruppe, klassen=5)

    assert len(klassen) == 25
    assert klassen[0] == 1           # duennster Umsatz
    assert klassen[24] == 5          # dickster Umsatz
    assert werte[24] > werte[0]
    # Monoton: ein hoeherer Umsatz fuehrt nie in eine kleinere Klasse.
    folge = [klassen[i] for i in range(25)]
    assert folge == sorted(folge)
