"""
snapshot_engine/auswertung/position.py — Auswertung des Positionspfads (P3-05).

Die Snapshots aus `analyse_modus = BESTEHENDE_POSITION` laufen seit P3-03 auf,
gelesen wurden sie bisher nirgends: `/signals` und jede Abfrage in
`auswertung/` filtern bewusst auf `NEUE_POSITION`. Diese Trennung ist richtig
und bleibt — die beiden Pfade sind zwei Bewertungssysteme in einer Tabelle:

- `confidence` trägt hier den **Positions-Score** (0–100 aus zwölf
  Teilscores), nicht die Einstiegs-Confidence
- `richtungssignal` entsteht aus der **Empfehlung** (halten vs. abbauen),
  nicht aus einer Confidence-Schwelle
- `beitrag_numeric` der Indikator-Zeilen trägt den Teilscore selbst (0–100,
  neutrale Mitte **50**), im Einstiegspfad dagegen ±1/±0,5

**Der entscheidende Unterschied in der Fragestellung.** Beim Einstieg lautet
sie „wäre der Kauf gut gewesen?" — und der Bezugspunkt ist der Markt. Bei einer
bestehenden Position lautet sie „war Halten besser als Verkaufen?", und der
Bezugspunkt hängt davon ab, was mit dem Erlös geschehen wäre:

- **absolut** beantwortet: war Halten besser als Kasse?
- **gegen den Markt** beantwortet: war Halten besser als Umschichten in den
  Index?

Beide Zahlen stehen deshalb nebeneinander, so wie in `kennzahlen.py` die
absolute Trefferquote neben der Marktquote steht. Welche zählt, entscheidet
die Anlagepraxis, nicht die Auswertung.
"""

import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from snapshot_engine.benchmark import ueberrendite
from snapshot_engine.models import (
    HORIZONTE_TAGE, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotIndikator,
    AnalyseSnapshotOutcome, Granularitaet,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, anteil_steigend,
    kennzahlen_aus_returns, mit_basis, mit_ueberrendite,
)
from snapshot_engine.auswertung.kennzahlen import RICHTUNG_JE_SIGNAL

logger = logging.getLogger(__name__)

# Neutrale Mitte eines Teilscores. Anders als im Einstiegspfad, wo ein Beitrag
# um 0 pendelt, laufen die zwölf Teilscores von 0 bis 100.
TEILSCORE_MITTE = 50.0

# Bänder des Positions-Scores. Bewusst andere Grenzen als die
# Confidence-Bänder des Einstiegspfads: dort markiert 60 die Kaufschwelle,
# hier gibt es keine — der Score bewertet eine Position, die bereits läuft.
SCORE_BAENDER = [
    {"label": "0–39 (Abbau angezeigt)", "min": 0, "max": 39.99},
    {"label": "40–59 (uneindeutig)", "min": 40, "max": 59.99},
    {"label": "60–79 (tragfähig)", "min": 60, "max": 79.99},
    {"label": "80–100 (stark)", "min": 80, "max": 100},
]


def richtung_aus_teilscore(wert: Optional[float]) -> Optional[str]:
    """„bullisch" / „bearisch" / None für einen Teilscore.

    Die Mitte ist 50, nicht 0 — ein Teilscore von 20 ist eine bearische
    Aussage, keine schwach bullische. Genau 50 trägt keine Richtung.
    """
    if wert is None:
        return None
    if wert > TEILSCORE_MITTE:
        return "bullisch"
    if wert < TEILSCORE_MITTE:
        return "bearisch"
    return None


def bestand(db: Session) -> dict:
    """Zählt, was der Positionspfad bisher gesammelt hat.

    Steht vor allem deshalb hier, weil der Bestand am Anfang leer ist: eine
    Auswertungsseite ohne diese Zahlen sähe aus, als sei etwas kaputt, obwohl
    nur noch keine Outcomes fällig geworden sind.
    """
    ergebnis = {"snapshots": 0, "ticker": 0, "outcomes": 0,
                "outcomes_ausgewertet": 0, "erster": None, "letzter": None}
    try:
        zeile = (
            db.query(func.count(AnalyseSnapshot.id),
                     func.count(func.distinct(AnalyseSnapshot.ticker)),
                     func.min(AnalyseSnapshot.snapshot_zeitpunkt),
                     func.max(AnalyseSnapshot.snapshot_zeitpunkt))
            .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.BESTEHENDE_POSITION)
            .one()
        )
        ergebnis.update({"snapshots": zeile[0] or 0, "ticker": zeile[1] or 0,
                         "erster": zeile[2], "letzter": zeile[3]})

        outcomes = (
            db.query(func.count(AnalyseSnapshotOutcome.id),
                     func.sum(func.cast(AnalyseSnapshotOutcome.ausgewertet, Integer)))
            .join(AnalyseSnapshot,
                  AnalyseSnapshot.id == AnalyseSnapshotOutcome.snapshot_id)
            .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.BESTEHENDE_POSITION)
            .one()
        )
        ergebnis["outcomes"] = outcomes[0] or 0
        ergebnis["outcomes_ausgewertet"] = int(outcomes[1] or 0)
    except Exception as e:
        logger.error("Positionsbestand nicht ermittelbar: %s", e, exc_info=True)
    return ergebnis


def _zeilen(db: Session, horizont: Optional[int] = None) -> list[tuple]:
    """(richtungssignal, confidence, outcome_return, war_erfolgreich, benchmark_return)."""
    query = (
        db.query(AnalyseSnapshot.richtungssignal,
                 AnalyseSnapshot.confidence,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.war_erfolgreich,
                 AnalyseSnapshotOutcome.benchmark_return)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.BESTEHENDE_POSITION)
    )
    if horizont:
        query = query.filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
    return query.all()


def kennzahlen(db: Session, minimum: int = MIN_STICHPROBE) -> dict:
    """Kennzahlen des Positionspfads je Horizont und je Empfehlung.

    Aufbau bewusst parallel zu `kennzahlen.kennzahlen_berechnen`, damit die
    beiden Pfade nebeneinander lesbar bleiben — aber mit eigener Abfrage,
    eigener Grundgesamtheit und ohne jede gemeinsame Mittelung.
    """
    ergebnis: dict = {"horizonte": {}, "je_empfehlung": {}}

    try:
        for horizont in HORIZONTE_TAGE:
            zeilen = _zeilen(db, horizont)
            if not zeilen:
                ergebnis["horizonte"][horizont] = {"status": "keine_daten", "n": 0}
                ergebnis["je_empfehlung"][horizont] = {}
                continue

            returns = [r for _, _, r, _, _ in zeilen]
            treffer = [t for _, _, _, t, _ in zeilen]
            richtungen = [RICHTUNG_JE_SIGNAL.get(s) for s, _, _, _, _ in zeilen]
            ueberrenditen = [ueberrendite(r, b) for _, _, r, _, b in zeilen]

            anteil = anteil_steigend(returns)
            anteil_markt = anteil_schlaegt_markt(ueberrenditen)

            ergebnis["horizonte"][horizont] = mit_ueberrendite(
                mit_basis(
                    kennzahlen_aus_returns(returns, treffer,
                                           horizont_tage=horizont,
                                           minimum=minimum,
                                           richtungen=richtungen),
                    anteil, richtungen),
                ueberrenditen, richtungen, anteil_markt,
                horizont_tage=horizont, minimum=minimum)

            je_empfehlung: dict = {}
            for signal in ("KAUF", "NEUTRAL", "VERKAUF"):
                gefiltert = [z for z in zeilen if z[0] == signal]
                r_signal = [RICHTUNG_JE_SIGNAL.get(signal)] * len(gefiltert)
                je_empfehlung[signal] = mit_ueberrendite(
                    mit_basis(
                        kennzahlen_aus_returns(
                            [r for _, _, r, _, _ in gefiltert],
                            [t for _, _, _, t, _ in gefiltert],
                            horizont_tage=horizont, minimum=minimum,
                            richtungen=r_signal),
                        anteil, r_signal),
                    [ueberrendite(r, b) for _, _, r, _, b in gefiltert],
                    r_signal, anteil_markt,
                    horizont_tage=horizont, minimum=minimum)
            ergebnis["je_empfehlung"][horizont] = je_empfehlung

    except Exception as e:
        logger.error("Positions-Kennzahlen fehlgeschlagen: %s", e, exc_info=True)

    return ergebnis


def score_baender(db: Session, horizont: int = 30,
                  minimum: int = MIN_STICHPROBE) -> list[dict]:
    """Trennt der Positions-Score? Ergebnis je Score-Band.

    Das Gegenstück zur Confidence-Kalibrierung des Einstiegspfads — und mit
    derselben Vorsicht zu lesen: eine sauber steigende Kurve entsteht in einem
    steigenden Markt schon dadurch, dass niedrige Scores Abbau-Empfehlungen
    sind. Erst die Marktspalte trennt das.
    """
    zeilen = _zeilen(db, horizont)
    if not zeilen:
        return [{"band": b["label"], "n": 0, "status": "keine_daten"}
                for b in SCORE_BAENDER]

    anteil = anteil_steigend([r for _, _, r, _, _ in zeilen])
    anteil_markt = anteil_schlaegt_markt(
        [ueberrendite(r, b) for _, _, r, _, b in zeilen])

    ergebnis = []
    for band in SCORE_BAENDER:
        gruppe = [z for z in zeilen
                  if band["min"] <= (z[1] or 0) <= band["max"]]
        richtungen = [RICHTUNG_JE_SIGNAL.get(z[0]) for z in gruppe]
        kz = mit_ueberrendite(
            mit_basis(
                kennzahlen_aus_returns(
                    [r for _, _, r, _, _ in gruppe],
                    [t for _, _, _, t, _ in gruppe],
                    horizont_tage=horizont, minimum=minimum,
                    richtungen=richtungen),
                anteil, richtungen),
            [ueberrendite(r, b) for _, _, r, _, b in gruppe],
            richtungen, anteil_markt,
            horizont_tage=horizont, minimum=minimum)
        ergebnis.append({"band": band["label"], "horizont_tage": horizont, **kz})
    return ergebnis


def teilscore_leaderboard(db: Session, horizont: int = 30,
                          minimum: int = MIN_STICHPROBE) -> list[dict]:
    """Welcher der zwölf Teilscores trennt die Ergebnisse?

    Nur Zeilen auf `Granularitaet.INDIKATOR` — `data_quality` läuft auf INFO,
    weil es kein Gewicht im Overall-Score trägt. Ein Vorsprung ohne
    Score-Wirkung ließe sich in keine Gewichtungsentscheidung übersetzen und
    gehört deshalb nicht in ein Leaderboard, das genau dafür da ist.
    """
    zeilen = (
        db.query(AnalyseSnapshotIndikator.indikator_name,
                 AnalyseSnapshotIndikator.beitrag_numeric,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.benchmark_return)
        .join(AnalyseSnapshot,
              AnalyseSnapshot.id == AnalyseSnapshotIndikator.snapshot_id)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshotIndikator.beitrag_numeric.isnot(None))
        .filter(AnalyseSnapshotIndikator.granularitaet == Granularitaet.INDIKATOR)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.BESTEHENDE_POSITION)
        .all()
    )
    if not zeilen:
        return []

    anteil_markt = anteil_schlaegt_markt(
        [ueberrendite(r, b) for _, _, r, b in zeilen])

    gruppen: dict[tuple, list] = defaultdict(list)
    for name, wert, ret, benchmark in zeilen:
        richtung = richtung_aus_teilscore(wert)
        if richtung is None:
            continue
        gruppen[(name, richtung)].append((ret, ueberrendite(ret, benchmark)))

    ergebnis = []
    for (name, richtung), paare in gruppen.items():
        richtungen = [1 if richtung == "bullisch" else -1] * len(paare)
        kz = mit_ueberrendite(
            kennzahlen_aus_returns([r for r, _ in paare],
                                   horizont_tage=horizont, minimum=minimum,
                                   richtungen=richtungen),
            [u for _, u in paare], richtungen, anteil_markt,
            horizont_tage=horizont, minimum=minimum)
        ergebnis.append({"teilscore": name, "richtung": richtung,
                         "horizont_tage": horizont, **kz})

    ergebnis.sort(key=lambda z: (z.get("markt_vorsprung_pp") is not None,
                                 z.get("markt_vorsprung_pp") or 0), reverse=True)
    return ergebnis
