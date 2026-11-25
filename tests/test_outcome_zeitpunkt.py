"""
tests/test_outcome_zeitpunkt.py — Audit 2026-11-16, L1 und L2.

L1: Ein fälliges Outcome darf seine Versuche nicht verbrauchen, bevor der
bewertende Tagesbar überhaupt existiert. Vorher waren fünf Versuche nach
15 Minuten weg, und das Outcome fiel dauerhaft aus der Auswertung.

L2: Der Replay setzt das Raster eines Tickers fort, statt bei jedem Lauf neu
bei Bar 250 zu beginnen und die Historie auf verschobenem Raster zu
verdoppeln.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from snapshot_engine import snapshot_service
from snapshot_engine.backfill_service import (
    KADENZ_BARS, MIN_VORLAUF_BARS, _ticker_replayen,
)
from snapshot_engine.models import (
    AnalyseSnapshot, AnalyseSnapshotOutcome, Datenmodus, SignalBackfillJob,
)
from snapshot_engine.snapshot_service import _bewertbar_ab, outcomes_nachtragen


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


# ---------------------------------------------------------------------------
# L1 — _bewertbar_ab
# ---------------------------------------------------------------------------

def test_bewertbar_erst_nach_schluss_des_naechsten_handelstags():
    # Mittwoch 18:24 UTC fällig → bewertet der Donnerstagsbar
    assert _bewertbar_ab(datetime(2026, 11, 25, 18, 24)) == datetime(2026, 11, 26, 23)


def test_freitag_faellig_wartet_auf_montag():
    assert _bewertbar_ab(datetime(2026, 11, 27, 18, 0)) == datetime(2026, 11, 30, 23)


def test_samstag_faellig_wartet_auf_montag():
    assert _bewertbar_ab(datetime(2026, 11, 28, 0, 0)) == datetime(2026, 11, 30, 23)


# ---------------------------------------------------------------------------
# L1 — outcomes_nachtragen zählt keine Versuche, solange der Kurs nicht da sein kann
# ---------------------------------------------------------------------------

@pytest.fixture
def ohne_kursdaten(monkeypatch):
    """Jeder Download liefert nichts; protokolliert, ob überhaupt geladen wurde."""
    import services.market_data_batch as mdb
    import snapshot_engine.benchmark as benchmark
    aufrufe = []

    def leerer_download(tickers, **kwargs):
        aufrufe.append(list(tickers))
        return {}

    monkeypatch.setattr(mdb, "batch_download_ohlcv", leerer_download)
    monkeypatch.setattr(benchmark, "benchmark_reihen_laden", lambda *a, **k: {})
    return aufrufe


def _outcome(db, faellig: datetime) -> AnalyseSnapshotOutcome:
    snapshot = AnalyseSnapshot(
        ticker="AAPL", snapshot_zeitpunkt=faellig - timedelta(days=7),
        kurs_bei_snapshot=100.0, confidence=50.0, richtungssignal="KAUF",
        datenmodus=Datenmodus.LIVE)
    outcome = AnalyseSnapshotOutcome(
        snapshot=snapshot, horizont_tage=7, faellig_am=faellig,
        ausgewertet=False, versuche=0)
    db.add_all([snapshot, outcome])
    db.commit()
    return outcome


def test_am_faelligkeitstag_wird_nicht_abgefragt(db, ohne_kursdaten):
    outcome = _outcome(db, datetime.utcnow() - timedelta(hours=1))
    for _ in range(10):  # zehn Drain-Ticks
        outcomes_nachtragen(db)
    assert ohne_kursdaten == []
    assert outcome.versuche == 0


def test_fehlender_kurs_in_der_karenz_kostet_keinen_versuch(db, ohne_kursdaten):
    outcome = _outcome(db, datetime.utcnow() - timedelta(days=4))
    for _ in range(10):
        outcomes_nachtragen(db)
    assert ohne_kursdaten  # wurde abgefragt
    assert outcome.versuche == 0
    assert outcome.ausgewertet is False


def test_nach_der_karenz_wird_wie_bisher_aufgegeben(db, ohne_kursdaten):
    outcome = _outcome(db, datetime.utcnow()
                       - timedelta(days=snapshot_service.OUTCOME_KARENZ_TAGE + 1))
    for _ in range(snapshot_service.MAX_OUTCOME_VERSUCHE + 2):
        outcomes_nachtragen(db)
    assert outcome.versuche == snapshot_service.MAX_OUTCOME_VERSUCHE


# ---------------------------------------------------------------------------
# L2 — _ticker_replayen setzt das Raster fort
# ---------------------------------------------------------------------------

def _hist(bars: int, start: str) -> pd.DataFrame:
    index = pd.bdate_range(start, periods=bars)
    close = np.linspace(100, 200, bars)
    return pd.DataFrame({"Open": close, "High": close, "Low": close,
                         "Close": close, "Volume": 1_000_000}, index=index)


@pytest.fixture
def bewertete_stichtage(monkeypatch):
    """Ersetzt den Score: protokolliert den Stichtag und erzeugt nichts."""
    import services.scoring as scoring
    tage = []

    def score(fenster, include_smc=True):
        tage.append(fenster.index[-1].to_pydatetime())
        return None

    monkeypatch.setattr(scoring, "calc_technical_score", score)
    return tage


def _vorhanden(db, ticker: str, zeitpunkt: datetime) -> None:
    db.add(AnalyseSnapshot(
        ticker=ticker, snapshot_zeitpunkt=zeitpunkt, kurs_bei_snapshot=100.0,
        confidence=50.0, richtungssignal="NEUTRAL",
        datenmodus=Datenmodus.HISTORISCH))
    db.commit()


def test_erster_lauf_beginnt_bei_bar_250(db, bewertete_stichtage):
    hist = _hist(300, "2024-01-01")
    _ticker_replayen(db, "AAPL", hist, SignalBackfillJob(id=1, include_smc=False))
    assert bewertete_stichtage[0] == hist.index[MIN_VORLAUF_BARS].to_pydatetime()


def test_folgelauf_setzt_das_raster_fort_statt_neu_zu_beginnen(db, bewertete_stichtage):
    """Der zweite Download beginnt 20 Bars später — Bar 250 läge auf einem
    anderen Tag. Bewertet werden darf nur, was NACH dem letzten Stichtag kommt,
    im Abstand der Kadenz."""
    erster = _hist(400, "2024-01-01")
    letzter = erster.index[MIN_VORLAUF_BARS + 10 * KADENZ_BARS]
    _vorhanden(db, "AAPL", letzter.to_pydatetime())

    zweiter = erster.iloc[20:]
    _ticker_replayen(db, "AAPL", zweiter, SignalBackfillJob(id=2, include_smc=False))

    assert bewertete_stichtage, "neue Stichtage nach dem letzten erwartet"
    assert min(bewertete_stichtage) > letzter.to_pydatetime()
    erwartet = list(erster.index[MIN_VORLAUF_BARS + 11 * KADENZ_BARS::KADENZ_BARS])
    assert bewertete_stichtage == [t.to_pydatetime() for t in erwartet]
