"""
tests/test_kursnaehe_panel.py — Die Kursnaehe-Pruefung auf dem Kurspanel.

§2p musste diese Pruefung schuldig bleiben: sie las Snapshot-Kurse, und der
Panel-Weg hat keine Snapshots. Sie stand deshalb ausdruecklich auf `None` —
mit der Begruendung, die Kennzahl sei aus Bilanzdaten gerechnet und koenne den
Kurs konstruktiv nicht enthalten.

**Genau diese Begruendung stand auch bei §2f**, bevor gemessen wurde, dass die
Zielrevision der Analysten zu 0,47 mit der Vorrendite korreliert. Eine
fundamentale Quelle ist noch keine fundamentale Groesse. Die Pruefung laeuft
jetzt aus `KursHistorie`, und diese Datei haelt fest, dass sie das Richtige
misst:

  * **Kein Look-ahead.** Das Fenster endet am letzten Handelstag STRIKT vor
    dem Stichtag. Eine Vorrendite, die den Stichtagskurs enthielte, wuerde mit
    dem Signal ueber den Kurs zusammenhaengen, den das Signal erklaeren soll.
  * **Split-Sicherheit.** Beide Kurse stammen aus derselben Reihe und damit
    aus derselben Anpassungsbasis.
  * **Die Korrelation zeigt an, was sie soll** — 1,0 bei einem umetikettierten
    Kurssignal, nahe 0 bei einer unabhaengigen Groesse.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, KursHistorie
from snapshot_engine.auswertung.kursnaehe import (
    SCHWELLE_KURSNAH, kursnaehe_pruefen_panel, rangkorrelation,
    vorrendite_je_beobachtung,
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


def _reihe(db, ticker: str, kurse: list[float],
           start: datetime | None = None) -> None:
    """Aufeinanderfolgende Kalendertage mit den angegebenen Schlusskursen."""
    beginn = start or datetime(2024, 1, 1)
    db.add_all([
        KursHistorie(ticker=ticker, datum=beginn + timedelta(days=i),
                     schluss=k, volumen=1_000.0, angepasst=True, quelle="test")
        for i, k in enumerate(kurse)
    ])
    db.commit()


# ---------------------------------------------------------------------------
# Kein Look-ahead
# ---------------------------------------------------------------------------

def test_der_stichtagskurs_gehoert_nicht_ins_fenster(db):
    """Am Stichtag verdoppelt sich der Kurs — die Vorrendite sieht das nicht."""
    # 100 Tage flach auf 10, dann am Stichtag ein Sprung auf 20.
    _reihe(db, "AAA", [10.0] * 100 + [20.0])
    stichtag = datetime(2024, 1, 1) + timedelta(days=100)

    werte = vorrendite_je_beobachtung(db, {1: ("AAA", stichtag)},
                                      fenster_tage=90)

    # Fenster liegt komplett in der flachen Phase.
    assert werte[1] == pytest.approx(0.0)


def test_das_fenster_endet_am_tag_davor(db):
    """Der letzte einbezogene Kurs ist der vom Vortag, nicht vom Stichtag."""
    # Tag 0..9 steigend 10,11,...,19; Stichtag ist Tag 9.
    _reihe(db, "AAA", [10.0 + i for i in range(10)])
    stichtag = datetime(2024, 1, 1) + timedelta(days=9)

    werte = vorrendite_je_beobachtung(db, {1: ("AAA", stichtag)},
                                      fenster_tage=9)

    # Beginn = Tag 0 (Kurs 10), Ende = Tag 8 (Kurs 18), nicht Tag 9 (19).
    assert werte[1] == pytest.approx((18.0 - 10.0) / 10.0 * 100)


def test_ohne_vorgeschichte_keine_vorrendite(db):
    """Der erste Handelstag einer Reihe hat kein Fenster hinter sich."""
    _reihe(db, "NEU", [10.0, 11.0, 12.0])
    assert vorrendite_je_beobachtung(
        db, {1: ("NEU", datetime(2024, 1, 1))}) == {}


def test_ticker_ohne_reihe_faellt_still_heraus(db):
    assert vorrendite_je_beobachtung(
        db, {1: ("FEHLT", datetime(2024, 6, 1))}) == {}


# ---------------------------------------------------------------------------
# Split-Sicherheit
# ---------------------------------------------------------------------------

def test_die_vorrendite_kommt_aus_einer_reihe(db):
    """Beide Kurse stammen aus derselben Anpassungsbasis.

    `services/kurshistorie.py` schreibt eine Reihe immer als Ganzes aus einem
    Abruf. Ein rueckwirkend bereinigter Kurs teilt sich durch einen ebenso
    bereinigten — der Splitfaktor kuerzt sich heraus.
    """
    # Dieselbe Kursentwicklung, einmal vor und einmal nach einem 10:1-Split
    # bereinigt. Die Rendite muss identisch sein.
    _reihe(db, "ROH", [100.0 + i for i in range(40)])
    _reihe(db, "BEREINIGT", [(100.0 + i) / 10 for i in range(40)])

    stichtag = datetime(2024, 1, 1) + timedelta(days=39)
    werte = vorrendite_je_beobachtung(
        db, {1: ("ROH", stichtag), 2: ("BEREINIGT", stichtag)},
        fenster_tage=30)

    assert werte[1] == pytest.approx(werte[2])


# ---------------------------------------------------------------------------
# Was die Korrelation anzeigt
# ---------------------------------------------------------------------------

def test_ein_umetikettiertes_kurssignal_faellt_auf(db):
    """Ein Signal, das die Vorrendite IST, korreliert mit 1,0 — und gilt als kursnah."""
    zuordnung = {}
    stichtag = datetime(2024, 3, 1)
    for i in range(30):
        ticker = f"T{i:02d}"
        # Jeder Titel laeuft anders stark; der Endkurs steigt mit i.
        _reihe(db, ticker, [100.0] * 30 + [100.0 + i] * 5,
               start=stichtag - timedelta(days=34))
        zuordnung[i] = (ticker, stichtag)

    vorrendite = vorrendite_je_beobachtung(db, zuordnung, fenster_tage=30)
    # Das "Signal" ist exakt die Vorrendite.
    ergebnis = kursnaehe_pruefen_panel(db, dict(vorrendite), zuordnung,
                                       vorrendite=vorrendite)

    assert ergebnis["rangkorrelation"] == pytest.approx(1.0)
    assert ergebnis["kursnah"] is True
    assert ergebnis["quelle"] == "kurs_historie"


def test_eine_unabhaengige_groesse_gilt_nicht_als_kursnah():
    """Gegenprobe auf der reinen Rechnung: entgegengesetzte Reihen, Korrelation −1."""
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    b = [5.0, 4.0, 3.0, 2.0, 1.0]
    assert rangkorrelation(a, b) == pytest.approx(-1.0)


def test_die_schwelle_gilt_in_beide_richtungen(db):
    """`kursnah` fragt den BETRAG — ein stark negativer Zusammenhang zaehlt auch.

    Sonst ginge ein Signal durch, das exakt die Umkehrung der Vorrendite ist
    und damit genauso wenig Neues traegt.
    """
    zuordnung = {}
    stichtag = datetime(2024, 3, 1)
    for i in range(30):
        ticker = f"T{i:02d}"
        _reihe(db, ticker, [100.0] * 30 + [100.0 + i] * 5,
               start=stichtag - timedelta(days=34))
        zuordnung[i] = (ticker, stichtag)

    vorrendite = vorrendite_je_beobachtung(db, zuordnung, fenster_tage=30)
    gespiegelt = {i: -w for i, w in vorrendite.items()}
    ergebnis = kursnaehe_pruefen_panel(db, gespiegelt, zuordnung,
                                       vorrendite=vorrendite)

    assert ergebnis["rangkorrelation"] == pytest.approx(-1.0)
    assert ergebnis["kursnah"] is True
    assert abs(ergebnis["rangkorrelation"]) >= SCHWELLE_KURSNAH


def test_ohne_gemeinsame_beobachtungen_kein_urteil(db):
    """Kein Wert ist None, nicht False — ein Nichtwissen ist kein Freispruch."""
    ergebnis = kursnaehe_pruefen_panel(db, {}, {}, vorrendite={})
    assert ergebnis["n"] == 0
    assert ergebnis["rangkorrelation"] is None
    assert ergebnis["kursnah"] is None
