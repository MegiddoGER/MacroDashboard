"""
snapshot_engine/auswertung/risk_adjusted.py — Risikoadjustierte Auswertung.

Stellt die Kennzahlen bereit, die andere Programmteile aus der Signal-Historie
beziehen (Kelly-Positionsgrößen, kompakte Trefferquote) — und löst damit
services/signal_history.py ab.

Bewusst NICHT marktbereinigt (P1-04b). Hier geht es um Positionsgrößen, also um
tatsächlich realisierte Gewinne und Verluste. Kelly
rechnet mit der Trefferquote und dem Gewinn/Verlust-Verhältnis, die das Depot
wirklich erlebt — eine Überrendite lässt sich nicht ausgeben, solange nicht
zugleich der Index geshortet wird. Die Marktbereinigung gehört in die
Bewertung der Signalqualität (kennzahlen, kalibrierung, indikator_stats, gate),
nicht in die Größenbestimmung.
"""

import logging

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import STATUS_OK, kennzahlen_aus_returns

logger = logging.getLogger(__name__)

# Kelly-Berechnung braucht eine belastbare Basis — darunter bleibt es beim
# konservativen Default des Aufrufers (Kelly-Anteil 0).
MIN_STICHPROBE_KELLY = 30

# Standard-Horizont für Positionsgrößen: entspricht einer typischen Swing-Trade-Haltedauer.
KELLY_HORIZONT_TAGE = 30


def _paare(db: Session, horizont: int,
           datenmodus: str | None = None) -> list[tuple]:
    """Lädt ausgewertete, GERICHTETE Beobachtungen als schlanke Tupel.

    Rückgabe je Zeile:
        (ticker, richtungssignal, confidence, zeitpunkt, outcome_return, war_erfolgreich)

    Nur KAUF und VERKAUF: ein NEUTRAL-Snapshot trifft keine Richtungsaussage,
    sein Ergebnis ist damit weder Treffer noch Fehlschlag. Beides hier
    mitzuzählen würde Trefferquote und Kelly-Verhältnis gegen eine Grundmenge
    rechnen, die zum Teil nie eine Prognose abgegeben hat.

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
    query = query.filter(
        AnalyseSnapshot.richtungssignal.in_(["KAUF", "VERKAUF"]))
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
