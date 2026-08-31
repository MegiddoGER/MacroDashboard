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
    MIN_STICHPROBE, anteil_steigend, kennzahlen_aus_returns, mit_basis,
    mit_ueberrendite,
)
from snapshot_engine.benchmark import ueberrendite

logger = logging.getLogger(__name__)

# Richtung des Signals für die Ertragsrechnung: bei VERKAUF ist ein fallender
# Kurs ein Gewinn. NEUTRAL ist keine gerichtete Prognose und bleibt None.
RICHTUNG_JE_SIGNAL: dict[str, int | None] = {
    "KAUF": 1, "VERKAUF": -1, "NEUTRAL": None,
}


def _ausgewertete_paare(db: Session, datenmodus: str | None = None,
                        horizont: int | None = None) -> list[tuple]:
    """Lädt die ausgewerteten Beobachtungen als schlanke Tupel.

    Rückgabe je Zeile: (ticker, richtungssignal, outcome_return,
    war_erfolgreich, benchmark_return).

    `benchmark_return` kommt ohne eigenen Filter mit: Zeilen ohne
    Vergleichswert sollen weiterhin in die absolute Trefferquote eingehen.
    Sie fallen erst in `mit_ueberrendite` heraus, das die Abdeckung
    getrennt ausweist.
    Bewusst keine ORM-Objekte — bei sechsstelligen Zeilenzahlen wäre das
    Hydrieren ganzer Entitäten der Flaschenhals der ganzen Seite.
    """
    query = (
        db.query(AnalyseSnapshot.ticker,
                 AnalyseSnapshot.richtungssignal,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.war_erfolgreich,
                 AnalyseSnapshotOutcome.benchmark_return)
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
            zeilen = _ausgewertete_paare(db, datenmodus, horizont)

            # Einmal je Horizont aus denselben Zeilen — kostet keine Extraabfrage.
            anteil = anteil_steigend([r for _, _, r, _, _ in zeilen])
            richtungen = [RICHTUNG_JE_SIGNAL.get(s) for _, s, _, _, _ in zeilen]
            # Titel minus Index je Beobachtung (P1-04). None, wo kein
            # Vergleichswert vorliegt — die Reihenfolge bleibt erhalten,
            # damit Rendite, Richtung und Überrendite ausgerichtet sind.
            ueberrenditen = [ueberrendite(r, b) for _, _, r, _, b in zeilen]

            ergebnis["horizonte"][horizont] = mit_ueberrendite(
                mit_basis(
                    kennzahlen_aus_returns(
                        [r for _, _, r, _, _ in zeilen],
                        [t for _, _, _, t, _ in zeilen],
                        horizont_tage=horizont, minimum=minimum,
                        richtungen=richtungen),
                    anteil, richtungen),
                ueberrenditen, richtungen, horizont_tage=horizont,
                minimum=minimum)

            # Aufschlüsselung je Richtungssignal
            je_signal: dict = {}
            for signal in ("KAUF", "NEUTRAL", "VERKAUF"):
                gefiltert = [z for z in zeilen if z[1] == signal]
                signal_richtungen = [RICHTUNG_JE_SIGNAL.get(signal)] * len(gefiltert)
                je_signal[signal] = mit_ueberrendite(
                    mit_basis(
                        kennzahlen_aus_returns(
                            [r for _, _, r, _, _ in gefiltert],
                            [t for _, _, _, t, _ in gefiltert],
                            horizont_tage=horizont, minimum=minimum,
                            richtungen=signal_richtungen),
                        anteil, signal_richtungen),
                    [ueberrendite(r, b) for _, _, r, _, b in gefiltert],
                    signal_richtungen, horizont_tage=horizont,
                    minimum=minimum)
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
        "zeitraum_von": None,
        "zeitraum_bis": None,
    }

    try:
        # Welchen Zeitraum die Zahlen abdecken, war bisher nirgends ablesbar —
        # ohne diese Angabe ist nicht erkennbar, aus welcher Marktphase eine
        # Trefferquote stammt.
        from sqlalchemy import func
        spanne = db.query(func.min(AnalyseSnapshot.snapshot_zeitpunkt),
                          func.max(AnalyseSnapshot.snapshot_zeitpunkt)).one()
        bestand["zeitraum_von"], bestand["zeitraum_bis"] = spanne
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


def vermischung_pruefen(db: Session, datenmodus: str | None = None) -> dict:
    """Meldet, ob die gewählte Auswahl unvergleichbare Grundgesamtheiten mischt.

    Zwei Arten der Vermischung machen jede Kennzahl darüber bedeutungslos:

      * DATENMODUS — LIVE und HISTORISCH stammen aus verschiedenen
        Marktphasen und Datenlagen (historische Snapshots kennen kein
        Sentiment). Ihre Basisraten unterscheiden sich deutlich.
      * SCORE_VERSION — Snapshots vor und nach einer Formeländerung tragen
        nicht dieselbe Bedeutung. Eine gemeinsame Trefferquote mittelt über
        zwei verschiedene Bewertungssysteme.

    Der Modul-Grundsatz "LIVE und HISTORISCH werden nie vermischt" galt bisher
    nur für explizit gesetzte Filter — die Vorgabe ALLE hebelte ihn aus, ohne
    dass es an der Oberfläche sichtbar war.
    """
    ergebnis: dict = {
        "datenmodi": [],
        "score_versionen": [],
        "vermischt": False,
        "warnung": None,
    }

    try:
        query = db.query(AnalyseSnapshot.datenmodus,
                         AnalyseSnapshot.score_version).distinct()
        if datenmodus:
            query = query.filter(AnalyseSnapshot.datenmodus == datenmodus)

        paare = query.all()
        modi = sorted({m for m, _ in paare if m})
        versionen = sorted({v for _, v in paare if v})
        # None-Versionen (Altzeilen vor der Migration) als solche ausweisen
        if any(v is None for _, v in paare):
            versionen.append("unbekannt")

        ergebnis["datenmodi"] = modi
        ergebnis["score_versionen"] = versionen

        gruende = []
        if len(modi) > 1:
            gruende.append(
                "LIVE und HISTORISCH werden gemeinsam ausgewertet — sie haben "
                "unterschiedliche Basisraten und Datenlagen")
        if len(versionen) > 1:
            gruende.append(
                "mehrere Score-Versionen (%s) werden gemeinsam ausgewertet — "
                "die Confidence bedeutet je Version etwas anderes"
                % ", ".join(versionen))

        if gruende:
            ergebnis["vermischt"] = True
            ergebnis["warnung"] = (
                "Die Zahlen mischen unvergleichbare Grundgesamtheiten: "
                + "; ".join(gruende) + ".")

    except Exception as e:
        logger.error("Vermischungsprüfung fehlgeschlagen: %s", e, exc_info=True)

    return ergebnis


def _top_flop_ticker(db: Session, datenmodus: str | None, horizont: int,
                     minimum: int = MIN_STICHPROBE,
                     min_pro_ticker: int = MIN_STICHPROBE) -> tuple[list, list]:
    """Ermittelt die besten und schlechtesten Ticker (nur KAUF-Signale).

    `min_pro_ticker` folgt bewusst der allgemeinen Mindeststichprobe: hier
    werden die Ränder einer Verteilung gezeigt, und genau dort produziert eine
    zu kleine Stichprobe zuverlässig Rauschen, das nach Erkenntnis aussieht.
    """
    zeilen = _ausgewertete_paare(db, datenmodus, horizont)

    je_ticker = defaultdict(list)
    for ticker, richtungssignal, outcome_return, _, _ in zeilen:
        if richtungssignal == "KAUF":
            je_ticker[ticker].append(outcome_return)

    bewertet = []
    for ticker, returns in je_ticker.items():
        if len(returns) < min_pro_ticker:
            continue
        kennzahlen = kennzahlen_aus_returns(
            returns, horizont_tage=horizont, minimum=min_pro_ticker,
            richtungen=[1] * len(returns))
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
