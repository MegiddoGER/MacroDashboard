"""
tests/test_aufholung.py — Die automatische Erneuerung des historischen Replays.

`aufholung_pruefen` laeuft alle drei Minuten im Drain. Sie darf die historische
Reihe weiterfuellen, ohne dass die App zu einer festen Uhrzeit offen sein muss
— und sie darf dabei nichts anfassen, was der Benutzer selbst entschieden hat.

Getestet wird deshalb vor allem, wann sie **nichts** tut. Ein Fehler in dieser
Richtung ist teuer und still: ein ungewollt gestarteter Lauf zieht das gesamte
Universum ueber Jahre herunter, und ein ueberschriebener Abbruch hebelt eine
ausdrueckliche Entscheidung aus.

Eigene In-Memory-Datenbank je Test, und das Universum wird ersetzt: ohne das
griffe `backfill_starten` ueber `aktives_universum` auf die
Index-Zusammensetzung im Netz zu. Geprueft wird die Job-Verwaltung, nicht der
Replay und nicht das Universum.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from snapshot_engine.models import (
    BackfillStatus, SignalBackfillJob, SignalBackfillTickerStatus,
)
from snapshot_engine.backfill_service import (
    AUFHOLUNG_ABSTAND_TAGE, aufholung_pruefen,
)

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


@pytest.fixture(autouse=True)
def universum_ohne_netz(monkeypatch):
    """Ersetzt das Ticker-Universum durch eine feste Liste.

    `backfill_starten` friert das Universum ein und holt es dafuer ueber
    `aktives_universum` — das laedt die Index-Zusammensetzung aus dem Netz.
    In einem Test ueber Job-Verwaltung ist das weder noetig noch zulaessig:
    es macht den Lauf langsam, abhaengig von einer fremden Seite, und bei
    fehlender Verbindung grundlos rot.

    `backfill_starten` importiert die Funktion erst im Funktionskoerper, das
    Patchen am Modul greift daher zur Aufrufzeit.
    """
    import snapshot_engine.universe as universe
    monkeypatch.setattr(universe, "aktives_universum",
                        lambda db: ["AAPL", "MSFT", "SAP.DE"])


def _job(db, status: str, beendet_vor_tagen: int | None = None,
         historie_jahre: int = 10, include_smc: bool = True,
         offene_ticker: int = 0) -> SignalBackfillJob:
    """Legt einen Backfill-Job mit definiertem Alter und Zustand an."""
    beendet = (JETZT - timedelta(days=beendet_vor_tagen)
               if beendet_vor_tagen is not None else None)
    job = SignalBackfillJob(
        status=status,
        gestartet_am=(beendet or JETZT) - timedelta(hours=2),
        beendet_am=beendet,
        historie_jahre=historie_jahre,
        include_smc=include_smc,
        ticker_gesamt=597,
    )
    db.add(job)
    db.flush()
    for i in range(offene_ticker):
        db.add(SignalBackfillTickerStatus(
            job_id=job.id, ticker=f"T{i}", status=BackfillStatus.AUSSTEHEND))
    db.commit()
    return job


# ---------------------------------------------------------------------------
# Wenn sie nichts tun darf
# ---------------------------------------------------------------------------

def test_ohne_vorgeschichte_passiert_nichts(db):
    """Der erste Backfill ist eine bewusste Entscheidung ueber Tiefe und SMC.
    Ohne einen vorherigen Lauf gibt es auch keine Parameter zu uebernehmen."""
    assert aufholung_pruefen(db, jetzt=JETZT) is None
    assert db.query(SignalBackfillJob).count() == 0


def test_laufender_job_wird_nicht_angetastet(db):
    _job(db, BackfillStatus.LAEUFT, offene_ticker=40)
    assert aufholung_pruefen(db, jetzt=JETZT) is None
    assert db.query(SignalBackfillJob).count() == 1


def test_abbruch_wird_nicht_ueberschrieben(db):
    """Ein Abbruch ist eine ausdrueckliche Entscheidung. Sie automatisch zu
    revidieren waere genau die Art stiller Eigenmaechtigkeit, die hier nicht
    passieren darf — auch nicht nach beliebig langer Zeit."""
    _job(db, BackfillStatus.ABGEBROCHEN, beendet_vor_tagen=90)
    assert aufholung_pruefen(db, jetzt=JETZT) is None
    assert db.query(SignalBackfillJob).count() == 1


def test_innerhalb_des_abstands_passiert_nichts(db):
    """Vor Ablauf der Kadenz gaebe es keinen neuen Stichtag zu holen — der Lauf
    wuerde nur dasselbe ueberspringen und dafuer alles neu herunterladen."""
    _job(db, BackfillStatus.FERTIG,
         beendet_vor_tagen=AUFHOLUNG_ABSTAND_TAGE - 1)
    assert aufholung_pruefen(db, jetzt=JETZT) is None
    assert db.query(SignalBackfillJob).count() == 1


def test_fehlerstatus_erneuert_nicht(db):
    """Ein Lauf mit Status FEHLER ist nicht fertig geworden. Ihn stillschweigend
    neu zu starten wuerde den Fehler im Takt der Kadenz wiederholen."""
    _job(db, BackfillStatus.FEHLER, beendet_vor_tagen=30)
    assert aufholung_pruefen(db, jetzt=JETZT) is None
    assert db.query(SignalBackfillJob).count() == 1


# ---------------------------------------------------------------------------
# Wenn sie erneuern soll
# ---------------------------------------------------------------------------

def test_nach_ablauf_des_abstands_wird_erneuert(db):
    _job(db, BackfillStatus.FERTIG, beendet_vor_tagen=AUFHOLUNG_ABSTAND_TAGE)
    neu = aufholung_pruefen(db, jetzt=JETZT)
    assert neu is not None
    assert neu.status == BackfillStatus.LAEUFT
    assert db.query(SignalBackfillJob).count() == 2


def test_parameter_des_letzten_laufs_werden_uebernommen(db):
    """Die volle Tiefe bleibt erhalten — nur so werden auch die Ticker
    nachgeholt, die beim letzten Lauf am Kursabruf gescheitert sind."""
    _job(db, BackfillStatus.FERTIG, beendet_vor_tagen=30,
         historie_jahre=10, include_smc=True)
    neu = aufholung_pruefen(db, jetzt=JETZT)
    assert neu is not None
    assert neu.historie_jahre == 10
    assert neu.include_smc is True


def test_abgeschaltetes_smc_bleibt_abgeschaltet(db):
    """Gegenprobe zur Parameteruebernahme: sie darf nicht auf die Vorgabe
    zurueckfallen, sonst schaltet die Erneuerung SMC wieder ein."""
    _job(db, BackfillStatus.FERTIG, beendet_vor_tagen=30,
         historie_jahre=3, include_smc=False)
    neu = aufholung_pruefen(db, jetzt=JETZT)
    assert neu is not None
    assert neu.historie_jahre == 3
    assert neu.include_smc is False


def test_zweiter_aufruf_startet_keinen_dritten_job(db):
    """Der Drain ruft alle drei Minuten auf. Nach einer Erneuerung laeuft ein
    Job, und der naechste Aufruf muss ein No-op sein."""
    _job(db, BackfillStatus.FERTIG, beendet_vor_tagen=30)
    erster = aufholung_pruefen(db, jetzt=JETZT)
    assert erster is not None
    assert aufholung_pruefen(db, jetzt=JETZT) is None
    assert db.query(SignalBackfillJob).count() == 2
