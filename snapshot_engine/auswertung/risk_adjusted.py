"""
snapshot_engine/auswertung/risk_adjusted.py — Risikoadjustierte Auswertung.

Stellt die Kennzahlen bereit, die andere Programmteile aus der Signal-Historie
beziehen (Kelly-Positionsgrößen, Journal-Statistik) — und löst damit
services/signal_history.py ab.
"""

import logging
import statistics
from collections import defaultdict

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome, Datenmodus,
)
from snapshot_engine.auswertung.basis import STATUS_OK, kennzahlen_aus_returns

logger = logging.getLogger(__name__)

# Kelly-Berechnung braucht eine belastbare Basis — darunter bleibt es beim
# konservativen Default des Aufrufers (Kelly-Anteil 0).
MIN_STICHPROBE_KELLY = 30

# Standard-Horizont für Positionsgrößen: entspricht einer typischen Swing-Trade-Haltedauer.
KELLY_HORIZONT_TAGE = 30


def _paare(db: Session, horizont: int, datenmodus: str | None = None,
           nur_gerichtete: bool = True) -> list[tuple]:
    """Lädt ausgewertete Beobachtungen als schlanke Tupel.

    Rückgabe je Zeile:
        (ticker, richtungssignal, confidence, zeitpunkt, outcome_return, war_erfolgreich)

    Keine ORM-Objekte — diese Funktion wird u.a. bei jeder Positionsgrößen-
    Berechnung aufgerufen und darf mit wachsendem Datenbestand nicht langsamer werden.
    """
    query = (
        db.query(AnalyseSnapshot.ticker,
                 AnalyseSnapshot.richtungssignal,
                 AnalyseSnapshot.confidence,
                 AnalyseSnapshot.snapshot_zeitpunkt,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.war_erfolgreich)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
    )
    if datenmodus:
        query = query.filter(AnalyseSnapshot.datenmodus == datenmodus)
    if nur_gerichtete:
        query = query.filter(AnalyseSnapshot.richtungssignal.in_(["KAUF", "VERKAUF"]))
    return query.all()


def kelly_parameter(db: Session, horizont: int = KELLY_HORIZONT_TAGE,
                    minimum: int = MIN_STICHPROBE_KELLY) -> dict | None:
    """Liefert Trefferquote und Gewinn/Verlust-Verhältnis für die Kelly-Formel.

    Anders als die abgelöste Implementierung in services/signal_history.py
    wird das Verhältnis aus der VOLLSTÄNDIGEN Verteilung berechnet, nicht aus
    den Top-3/Flop-3-Signalen. Extremwerte allein überschätzen beide Seiten
    massiv und verzerren das Verhältnis.

    Returns:
        {"win_rate": 0..1, "avg_win_loss_ratio": float, "n": int} oder None,
        wenn die Datenlage nicht ausreicht.
    """
    try:
        paare = _paare(db, horizont)
        if len(paare) < minimum:
            return None

        kennzahlen = kennzahlen_aus_returns(
            [z[4] for z in paare], [z[5] for z in paare],
            horizont_tage=horizont, minimum=minimum)

        if kennzahlen.get("status") != STATUS_OK:
            return None
        if kennzahlen.get("trefferquote") is None:
            return None

        avg_gewinn = kennzahlen.get("avg_gewinn") or 0.0
        avg_verlust = kennzahlen.get("avg_verlust") or 0.0
        if avg_verlust <= 0:
            return None  # Ohne Verluste ist das Verhältnis nicht bestimmbar

        return {
            "win_rate": kennzahlen["trefferquote"] / 100.0,
            "avg_win_loss_ratio": round(avg_gewinn / avg_verlust, 3),
            "n": kennzahlen["n"],
            "n_effektiv": kennzahlen["n_effektiv"],
            "horizont_tage": horizont,
        }

    except Exception as e:
        logger.error("Kelly-Parameter fehlgeschlagen: %s", e, exc_info=True)
        return None


def signal_statistik(db: Session, horizont: int = 30,
                     datenmodus: str | None = None,
                     min_pro_ticker: int = 5) -> dict:
    """Kennzahlen für die Journal-Seite: beste/schlechteste Ticker und Signale.

    Returns:
        Dict mit gesamt, avg_confidence, bester_ticker, schlechtester_ticker,
        top_signale, flop_signale.
    """
    ergebnis: dict = {
        "gesamt": 0,
        "ausgewertet": 0,
        "avg_confidence": None,
        "bester_ticker": None,
        "schlechtester_ticker": None,
        "top_signale": [],
        "flop_signale": [],
        "horizont_tage": horizont,
    }

    try:
        paare = _paare(db, horizont, datenmodus, nur_gerichtete=False)
        ergebnis["ausgewertet"] = len(paare)
        ergebnis["gesamt"] = db.query(AnalyseSnapshot).filter(
            AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION).count()

        if not paare:
            return ergebnis

        confidences = [z[2] for z in paare if z[2] is not None]
        if confidences:
            ergebnis["avg_confidence"] = round(statistics.fmean(confidences), 1)

        # Trefferquote je Ticker (nur gerichtete Signale)
        je_ticker = defaultdict(list)
        for ticker, richtung, _conf, _zeit, _ret, erfolg in paare:
            if richtung in ("KAUF", "VERKAUF") and erfolg is not None:
                je_ticker[ticker].append(erfolg)

        bewertet = [
            {
                "ticker": ticker,
                "trefferquote": round(sum(1 for t in treffer if t) / len(treffer) * 100, 1),
                "anzahl": len(treffer),
            }
            for ticker, treffer in je_ticker.items()
            if len(treffer) >= min_pro_ticker
        ]

        if bewertet:
            sortiert = sorted(bewertet, key=lambda x: x["trefferquote"], reverse=True)
            ergebnis["bester_ticker"] = sortiert[0]
            ergebnis["schlechtester_ticker"] = sortiert[-1]

        # Einzelne Extremwerte (rein illustrativ, keine statistische Aussage)
        def _als_signal(zeile) -> dict:
            ticker, _richtung, confidence, zeitpunkt, outcome_return, _erfolg = zeile
            return {
                "ticker": ticker,
                "return_pct": outcome_return,
                "confidence": confidence,
                "datum": zeitpunkt.strftime("%Y-%m-%d") if zeitpunkt else None,
            }

        nach_return = sorted(paare, key=lambda z: z[4], reverse=True)
        ergebnis["top_signale"] = [_als_signal(z) for z in nach_return[:3]]
        ergebnis["flop_signale"] = [_als_signal(z) for z in nach_return[-3:][::-1]]

    except Exception as e:
        logger.error("Signal-Statistik fehlgeschlagen: %s", e, exc_info=True)

    return ergebnis


def trefferquote(db: Session, horizont: int = 30,
                 datenmodus: str | None = None) -> dict:
    """Kompakte Trefferquote (Ersatz für signal_history.calc_hit_rate)."""
    paare = _paare(db, horizont, datenmodus)
    kennzahlen = kennzahlen_aus_returns(
        [z[4] for z in paare], [z[5] for z in paare], horizont_tage=horizont)

    return {
        "horizont_tage": horizont,
        "trefferquote": kennzahlen.get("trefferquote"),
        "ausgewertet": kennzahlen.get("n", 0),
        "n_effektiv": kennzahlen.get("n_effektiv", 0),
        "status": kennzahlen.get("status"),
    }
