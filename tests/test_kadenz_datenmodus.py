"""
tests/test_kadenz_datenmodus.py — Die Kadenz-Regel zaehlt je Datenmodus.

`ist_snapshot_faellig` entscheidet, ob eine neue Beobachtung ueberhaupt
entsteht. Die Regel hat zwei Aufgaben, die sich widersprechen koennen, und
deshalb steht sie unter Test:

  * Sie muss Pseudo-Replikation verhindern. Ohne sie erzeugte ein taeglicher
    Lauf bei 7/30/90-Tage-Horizonten fast identische, ueberlappende
    Beobachtungen — die Statistik saehe nach hunderten unabhaengigen
    Stichproben aus und jede Trefferquote damit scheinbar signifikant.

  * Sie darf die beiden Messreihen nicht aneinanderketten. HISTORISCH kennt
    nur trend/volume/oscillator (+SMC), LIVE zusaetzlich fundamental und
    sentiment. Sperrte ein rueckdatierter HISTORISCH-Stichtag die LIVE-Reihe,
    kostete jeder Aufhol-Replay genau die Beobachtungen, ueber die fundamental
    und sentiment ueberhaupt messbar sind — und die sind fuer vergangene
    Stichtage nicht rekonstruierbar, also auch nicht nachholbar.

Der zweite Punkt war bis 2026-10-04 verletzt: die Abfrage filterte nur auf
`analyse_modus`, nicht auf `datenmodus`.

Die Tests brauchen eine Session und legen dafuer eine eigene
In-Memory-Datenbank an — die Datei unter `data/` wird nicht beruehrt.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from snapshot_engine.models import AnalyseModus, AnalyseSnapshot, Datenmodus
from snapshot_engine.snapshot_service import ist_snapshot_faellig

JETZT = datetime(2026, 10, 4, 12, 0)


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


def _snapshot(db, ticker: str, vor_tagen: int, datenmodus: str,
              richtung: str = "KAUF",
              modus: str = AnalyseModus.NEUE_POSITION) -> AnalyseSnapshot:
    """Legt einen Snapshot mit definiertem Alter und Datenmodus an."""
    s = AnalyseSnapshot(
        ticker=ticker.upper(),
        snapshot_zeitpunkt=JETZT - timedelta(days=vor_tagen),
        kurs_bei_snapshot=100.0,
        confidence=60.0,
        richtungssignal=richtung,
        analyse_modus=modus,
        datenmodus=datenmodus,
    )
    db.add(s)
    db.commit()
    return s


# ---------------------------------------------------------------------------
# Die Kadenz an sich — innerhalb einer Reihe
# ---------------------------------------------------------------------------

def test_ohne_vorgeschichte_ist_faellig(db):
    assert ist_snapshot_faellig(db, "AAPL", zeitpunkt=JETZT) is True


def test_innerhalb_des_kuerzesten_horizonts_nicht_faellig(db):
    """Vier Tage alt: die 7-Tage-Kadenz sperrt. Das ist der Schutz gegen
    ueberlappende Beobachtungen und darf nicht verloren gehen."""
    _snapshot(db, "AAPL", vor_tagen=4, datenmodus=Datenmodus.LIVE)
    assert ist_snapshot_faellig(db, "AAPL", zeitpunkt=JETZT) is False


def test_nach_dem_kuerzesten_horizont_wieder_faellig(db):
    _snapshot(db, "AAPL", vor_tagen=8, datenmodus=Datenmodus.LIVE)
    assert ist_snapshot_faellig(db, "AAPL", zeitpunkt=JETZT) is True


def test_richtungswechsel_sticht_die_kadenz(db):
    """Ein gekipptes Signal ist ein echtes neues Ereignis und darf auch
    innerhalb der Sperrfrist erfasst werden."""
    _snapshot(db, "AAPL", vor_tagen=2, datenmodus=Datenmodus.LIVE,
              richtung="KAUF")
    assert ist_snapshot_faellig(db, "AAPL", richtung_neu="VERKAUF",
                                zeitpunkt=JETZT) is True
    assert ist_snapshot_faellig(db, "AAPL", richtung_neu="KAUF",
                                zeitpunkt=JETZT) is False


# ---------------------------------------------------------------------------
# Die Trennung der Messreihen — der eigentliche Gegenstand
# ---------------------------------------------------------------------------

def test_historischer_stichtag_sperrt_die_live_reihe_nicht(db):
    """Der Kern: ein gestern rueckdatierter Replay-Stichtag darf die
    LIVE-Erhebung nicht blockieren. Sonst verliert der Aufhol-Replay genau
    die Beobachtungen, die fundamental und sentiment messbar machen."""
    _snapshot(db, "AAPL", vor_tagen=1, datenmodus=Datenmodus.HISTORISCH)
    assert ist_snapshot_faellig(db, "AAPL", zeitpunkt=JETZT,
                                datenmodus=Datenmodus.LIVE) is True


def test_live_snapshot_sperrt_die_historische_reihe_nicht(db):
    """Dieselbe Trennung in die andere Richtung — die Reihen sind symmetrisch
    unabhaengig, nicht nur eine gegen die andere privilegiert."""
    _snapshot(db, "AAPL", vor_tagen=1, datenmodus=Datenmodus.LIVE)
    assert ist_snapshot_faellig(db, "AAPL", zeitpunkt=JETZT,
                                datenmodus=Datenmodus.HISTORISCH) is True


def test_innerhalb_desselben_modus_sperrt_es_weiter(db):
    """Die Trennung lockert die Kadenz nicht: innerhalb eines Modus gilt sie
    unveraendert. Ein frischer HISTORISCH-Stichtag sperrt HISTORISCH."""
    _snapshot(db, "AAPL", vor_tagen=1, datenmodus=Datenmodus.HISTORISCH)
    assert ist_snapshot_faellig(db, "AAPL", zeitpunkt=JETZT,
                                datenmodus=Datenmodus.HISTORISCH) is False


def test_live_ist_die_vorgabe(db):
    """Beide Aufrufstellen im Programm erheben LIVE und uebergeben den Modus
    nicht. Die Vorgabe muss deshalb LIVE sein — waere sie HISTORISCH, liefe
    das Gating still gegen die falsche Reihe."""
    _snapshot(db, "AAPL", vor_tagen=1, datenmodus=Datenmodus.LIVE)
    assert ist_snapshot_faellig(db, "AAPL", zeitpunkt=JETZT) is False

    _snapshot(db, "MSFT", vor_tagen=1, datenmodus=Datenmodus.HISTORISCH)
    assert ist_snapshot_faellig(db, "MSFT", zeitpunkt=JETZT) is True


def test_der_positionspfad_bleibt_unberuehrt(db):
    """Die Regel filtert weiterhin auf NEUE_POSITION. Ein Positions-Snapshot
    traegt eine andere Confidence-Bedeutung und darf die Einstiegs-Kadenz
    nicht beeinflussen."""
    _snapshot(db, "AAPL", vor_tagen=1, datenmodus=Datenmodus.LIVE,
              modus=AnalyseModus.BESTEHENDE_POSITION)
    assert ist_snapshot_faellig(db, "AAPL", zeitpunkt=JETZT,
                                datenmodus=Datenmodus.LIVE) is True
