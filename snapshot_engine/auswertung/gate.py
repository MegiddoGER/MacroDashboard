"""
snapshot_engine/auswertung/gate.py — Wirkung des Oszillator-Gates.

Das Gate (services/scoring.OSZILLATOR_GATE_SCHWELLE) unterdrückt Kauf-
empfehlungen, die allein von Trend und Volumen getragen werden. Diese
Auswertung prüft an der Historie nach, ob es hält, was es verspricht:
Schneiden die durchgelassenen Signale besser ab als die geblockten?

Möglich ist das ohne Schema-Änderung, weil jeder Snapshot seine
Kategorie-Scores und deren Maxima mitführt — der Gate-Zustand lässt sich für
jede je erzeugte Beobachtung nachträglich exakt rekonstruieren. Damit ist die
Änderung an denselben 83.606 Beobachtungen überprüfbar, aus denen sie
abgeleitet wurde, und an jeder späteren dazu.

Warnung zur Interpretation: die Schwelle wurde AUS diesen Daten gewonnen. Die
Zahlen hier sind daher in-sample und bestätigen nur die Konsistenz der
Umsetzung, nicht die Gültigkeit des Effekts. Belastbar wird das erst mit
Beobachtungen, die nach der Einführung entstanden sind — dafür trennt
`score_version` die Bestände.
"""

import json
import logging

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    MIN_BEWEGUNG_PCT, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, effektive_stichprobe, fehlerspanne_pp,
)

logger = logging.getLogger(__name__)


def _normierter_oszillator(indikator_json: str | None,
                           cat_max_json: str | None) -> float | None:
    """Rekonstruiert den normierten Oszillator-Score eines Snapshots."""
    try:
        cat_scores = json.loads(indikator_json or "{}")
        cat_max = json.loads(cat_max_json or "{}")
    except (TypeError, ValueError):
        return None

    maximum = cat_max.get("oscillator", 0)
    if not maximum:
        return None
    return cat_scores.get("oscillator", 0) / maximum


def gate_wirkung(db: Session, horizont: int = 30,
                 datenmodus: str | None = None,
                 schwelle: float | None = None,
                 minimum: int = MIN_STICHPROBE) -> dict:
    """Wirkung der oszillatorgesteuerten Empfehlungslogik, in drei Gruppen.

        durchgelassen — Confidence >= 60 UND Oszillator trägt  (Kaufempfehlung)
        geblockt      — Confidence >= 60, Oszillator trägt nicht (gesperrt)
        befoerdert    — Confidence <  60, Oszillator trägt      (Mean-Reversion)

    Rekonstruiert aus den je Snapshot gespeicherten Kategorie-Scores, nicht aus
    `richtungssignal`. Das ist Absicht: `richtungssignal` bleibt die Lesart des
    Composites, wodurch sich auch die KONTRAFAKTISCHE Frage beantworten lässt —
    wie wären die gesperrten Signale gelaufen, hätte man sie befolgt? Ohne
    diesen Bezug ließe sich nie belegen, dass das Sperren etwas bringt.
    """
    if schwelle is None:
        from services.scoring import OSZILLATOR_GATE_SCHWELLE
        schwelle = OSZILLATOR_GATE_SCHWELLE

    ergebnis: dict = {
        "schwelle": schwelle,
        "horizont_tage": horizont,
        "basisrate": None,
        "durchgelassen": None,
        "geblockt": None,
        "befoerdert": None,
    }

    try:
        query = (
            db.query(AnalyseSnapshot.indikator_json,
                     AnalyseSnapshot.cat_max_json,
                     AnalyseSnapshot.confidence,
                     AnalyseSnapshotOutcome.outcome_return)
            .join(AnalyseSnapshotOutcome,
                  AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
            .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
            .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
            .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
            .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        )
        if datenmodus:
            query = query.filter(AnalyseSnapshot.datenmodus == datenmodus)
        zeilen = query.all()
    except Exception as e:
        logger.error("Gate-Auswertung fehlgeschlagen: %s", e, exc_info=True)
        return ergebnis

    # Basisrate über dieselbe Mindestbewegung, die auch die Treffer bewertet.
    bewegt = [r for _, _, _, r in zeilen if abs(r) >= MIN_BEWEGUNG_PCT]
    if not bewegt:
        return ergebnis
    basisrate = sum(1 for r in bewegt if r > 0) / len(bewegt) * 100
    ergebnis["basisrate"] = round(basisrate, 1)

    gruppen: dict[str, list[float]] = {
        "durchgelassen": [], "geblockt": [], "befoerdert": [],
    }

    for indikator_json, cat_max_json, confidence, ret in zeilen:
        if abs(ret) < MIN_BEWEGUNG_PCT:
            continue
        osz = _normierter_oszillator(indikator_json, cat_max_json)
        # Fehlender Oszillator trägt nie — weder sperrend noch befördernd.
        traegt = osz is not None and osz >= schwelle
        hohe_confidence = (confidence or 0) >= 60

        if hohe_confidence and traegt:
            gruppen["durchgelassen"].append(ret)
        elif hohe_confidence:
            gruppen["geblockt"].append(ret)
        elif traegt:
            gruppen["befoerdert"].append(ret)
        # Rest: weder empfohlen noch gesperrt — nicht Teil des Vergleichs.

    for schluessel, werte in gruppen.items():
        ergebnis[schluessel] = _gruppe_bewerten(werte, basisrate, horizont, minimum)

    return ergebnis


def _gruppe_bewerten(returns: list[float], basisrate: float,
                     horizont: int, minimum: int) -> dict:
    """Kennzahlen einer Gate-Gruppe gegen die Basisrate."""
    n = len(returns)
    if n == 0:
        return {"n": 0, "n_effektiv": 0, "trefferquote": None,
                "vorsprung_pp": None, "fehlerspanne_pp": None,
                "signifikant": None, "ausreichend": False}

    quote = sum(1 for r in returns if r > 0) / n * 100
    n_eff = effektive_stichprobe(n, horizont)
    spanne = fehlerspanne_pp(quote, n_eff)
    vorsprung = quote - basisrate

    return {
        "n": n,
        "n_effektiv": n_eff,
        "trefferquote": round(quote, 1),
        "vorsprung_pp": round(vorsprung, 1),
        "fehlerspanne_pp": spanne,
        "signifikant": (abs(vorsprung) > spanne) if spanne is not None else None,
        "ausreichend": n_eff >= minimum,
    }
