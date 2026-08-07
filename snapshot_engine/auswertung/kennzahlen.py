"""
snapshot_engine/auswertung/kennzahlen.py — Aggregierte Kennzahlen je Horizont.

Alle Auswertungen sind nach `datenmodus` getrennt: HISTORISCH-Snapshots
enthalten keine Fundamental-/Sentiment-Bewertung, ihre Confidence beruht auf
einer anderen Datenbasis. Beides zu vermischen würde die Kennzahlen wertlos
machen.
"""

import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    HORIZONTE_TAGE, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
    Datenmodus,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, kennzahlen_aus_returns,
)

logger = logging.getLogger(__name__)


def _ausgewertete_paare(db: Session, datenmodus: str | None = None,
                        horizont: int | None = None) -> list[tuple]:
    """Lädt (Snapshot, Outcome)-Paare aller ausgewerteten Beobachtungen."""
    query = (
        db.query(AnalyseSnapshot, AnalyseSnapshotOutcome)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
    )
    if datenmodus:
        query = query.filter(AnalyseSnapshot.datenmodus == datenmodus)
    if horizont:
        query = query.filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
    return query.all()


def kennzahlen_berechnen(db: Session, datenmodus: str | None = None,
                         minimum: int = MIN_STICHPROBE) -> dict:
    """Berechnet die Kernkennzahlen der Engine, aufgeschlüsselt nach Horizont.

    Returns:
        Dict mit Bestand, je-Horizont-Kennzahlen, Signal-Aufschlüsselung und
        Top-/Flop-Tickern.
    """
    ergebnis: dict = {
        "bestand": bestand_ermitteln(db),
        "horizonte": {},
        "je_signal": {},
        "top_ticker": [],
        "flop_ticker": [],
        "datenmodus": datenmodus or "ALLE",
    }

    try:
        for horizont in HORIZONTE_TAGE:
            paare = _ausgewertete_paare(db, datenmodus, horizont)
            returns = [o.outcome_return for _, o in paare]
            treffer = [o.war_erfolgreich for _, o in paare]

            ergebnis["horizonte"][horizont] = kennzahlen_aus_returns(
                returns, treffer, horizont_tage=horizont, minimum=minimum)

            # Aufschlüsselung je Richtungssignal
            je_signal: dict = {}
            for signal in ("KAUF", "NEUTRAL", "VERKAUF"):
                gefiltert = [(s, o) for s, o in paare if s.richtungssignal == signal]
                je_signal[signal] = kennzahlen_aus_returns(
                    [o.outcome_return for _, o in gefiltert],
                    [o.war_erfolgreich for _, o in gefiltert],
                    horizont_tage=horizont, minimum=minimum)
            ergebnis["je_signal"][horizont] = je_signal

        # Top-/Flop-Ticker auf dem kürzesten Horizont (meiste Daten)
        ergebnis["top_ticker"], ergebnis["flop_ticker"] = _top_flop_ticker(
            db, datenmodus, horizont=min(HORIZONTE_TAGE), minimum=minimum)

    except Exception as e:
        logger.error("Kennzahlen-Berechnung fehlgeschlagen: %s", e, exc_info=True)

    return ergebnis


def bestand_ermitteln(db: Session) -> dict:
    """Zählt Snapshots und Outcomes nach Datenmodus und Auswertungsstand."""
    bestand: dict = {
        "snapshots_gesamt": 0,
        "snapshots_live": 0,
        "snapshots_historisch": 0,
        "outcomes_ausgewertet": 0,
        "outcomes_offen": 0,
        "ticker_abgedeckt": 0,
    }

    try:
        bestand["snapshots_gesamt"] = db.query(AnalyseSnapshot).count()
        bestand["snapshots_live"] = db.query(AnalyseSnapshot).filter(
            AnalyseSnapshot.datenmodus == Datenmodus.LIVE).count()
        bestand["snapshots_historisch"] = db.query(AnalyseSnapshot).filter(
            AnalyseSnapshot.datenmodus == Datenmodus.HISTORISCH).count()
        bestand["outcomes_ausgewertet"] = db.query(AnalyseSnapshotOutcome).filter(
            AnalyseSnapshotOutcome.ausgewertet.is_(True)).count()
        bestand["outcomes_offen"] = db.query(AnalyseSnapshotOutcome).filter(
            AnalyseSnapshotOutcome.ausgewertet.is_(False)).count()
        bestand["ticker_abgedeckt"] = db.query(
            AnalyseSnapshot.ticker).distinct().count()
    except Exception as e:
        logger.error("Bestandsermittlung fehlgeschlagen: %s", e, exc_info=True)

    return bestand


def _top_flop_ticker(db: Session, datenmodus: str | None, horizont: int,
                     minimum: int = MIN_STICHPROBE,
                     min_pro_ticker: int = 5) -> tuple[list, list]:
    """Ermittelt die besten und schlechtesten Ticker (nur KAUF-Signale)."""
    paare = _ausgewertete_paare(db, datenmodus, horizont)

    je_ticker = defaultdict(list)
    for snapshot, outcome in paare:
        if snapshot.richtungssignal == "KAUF":
            je_ticker[snapshot.ticker].append(outcome.outcome_return)

    bewertet = []
    for ticker, returns in je_ticker.items():
        if len(returns) < min_pro_ticker:
            continue
        kennzahlen = kennzahlen_aus_returns(
            returns, horizont_tage=horizont, minimum=min_pro_ticker)
        bewertet.append({
            "ticker": ticker,
            "anzahl": len(returns),
            "avg_return": kennzahlen.get("avg_return"),
            "trefferquote": kennzahlen.get("trefferquote"),
        })

    if not bewertet:
        return [], []

    sortiert = sorted(bewertet, key=lambda x: x["avg_return"] or 0, reverse=True)
    return sortiert[:5], sortiert[-5:][::-1]
