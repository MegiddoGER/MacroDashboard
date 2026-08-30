"""
snapshot_engine/neugewichtung.py — Historische Snapshots neu gewichten.

Wenn sich die Kategorie-Gewichte in services/scoring.py ändern, beziehen sich
bereits gespeicherte Snapshots noch auf die alte Gewichtung. Trefferquoten und
Kalibrierung würden dann zwei verschiedene Bewertungssysteme vermischen —
ausgerechnet in der Auswertung, die die Qualität des aktuellen Systems messen soll.

Dieses Modul rechnet die Confidence aus den gespeicherten Kategorie-Scores neu.
Es sind keine Kursabrufe nötig: cat_scores, cat_max und weights liegen je
Snapshot vor, und _finalize_score ist für diese Werte eine reine Funktion.

Einschränkung — nur HISTORISCH:
    Bei LIVE-Snapshots kann zusätzlich die "Euphorie-Falle" aus
    _finalize_score gegriffen haben (Sentiment hoch UND RSI überkauft → Malus).
    Diese Korrektur beruht auf `signals`, das nicht gespeichert wird, und wäre
    daher nicht exakt reproduzierbar. HISTORISCH-Snapshots enthalten kein
    Sentiment, dort kann die Regel nie ausgelöst haben — die Neuberechnung ist
    dort exakt.

Einschränkung — nur NEUE_POSITION:
    Alle Abfragen filtern zusätzlich auf den Einstiegspfad. Der Positionspfad
    (BESTEHENDE_POSITION) speichert zwölf Teilscores statt fünf
    Kategorie-Scores und leitet sein Richtungssignal aus der Empfehlung ab,
    nicht aus der Confidence — `confidence_berechnen` und
    `richtung_aus_confidence` sind auf ihn schlicht nicht anwendbar.
    Rechnerisch greift dieser Filter heute nie (Positions-Snapshots sind immer
    LIVE), er steht bewusst trotzdem da: `richtung_neu_bewerten` SCHREIBT, und
    ein stillschweigend über den Datenmodus mitgeschützter Schreibpfad ist
    eine Falle für die erste Änderung, die diese Kopplung löst.
"""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from snapshot_engine.models import AnalyseModus, AnalyseSnapshot, Datenmodus

logger = logging.getLogger(__name__)


def confidence_berechnen(cat_scores: dict, cat_max: dict, weights: dict) -> float:
    """Rechnet die Confidence aus Kategorie-Scores — identisch zu _finalize_score."""
    gewichtet = 0.0
    for kategorie, gewicht in weights.items():
        maximum = cat_max.get(kategorie, 0)
        if maximum > 0:
            wert = cat_scores.get(kategorie, 0)
            wert = max(-maximum, min(maximum, wert))
            gewichtet += (wert / maximum) * gewicht
    gewichtet = max(-1.0, min(1.0, gewichtet))
    return round((gewichtet + 1.0) / 2.0 * 100.0, 1)


def _label_fuer(confidence: float) -> str:
    """Confidence-Label wie in _finalize_score."""
    if confidence >= 75:
        return "Hohe Confidence"
    if confidence >= 60:
        return "Gute Confidence"
    if confidence >= 45:
        return "Gemischte Signale"
    if confidence >= 30:
        return "Schwache Confidence"
    return "Sehr Schwache Confidence"


def neugewichtung_pruefen(db: Session, stichprobe: int = 3000) -> dict:
    """Prüft, ob gespeicherte Confidences aus den gespeicherten Werten exakt
    reproduzierbar sind — Voraussetzung dafür, der Neuberechnung zu trauen.

    Returns:
        {"geprueft": n, "exakt": n, "abweichend": n}
    """
    zeilen = (
        db.query(AnalyseSnapshot.confidence, AnalyseSnapshot.indikator_json,
                 AnalyseSnapshot.cat_max_json, AnalyseSnapshot.weights_json)
        .filter(AnalyseSnapshot.datenmodus == Datenmodus.HISTORISCH)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .limit(stichprobe).all()
    )

    exakt = abweichend = 0
    for confidence, cat_scores, cat_max, weights in zeilen:
        if not (cat_scores and cat_max and weights):
            abweichend += 1
            continue
        nachgerechnet = confidence_berechnen(
            json.loads(cat_scores), json.loads(cat_max), json.loads(weights))
        if abs(nachgerechnet - (confidence or 0)) < 0.05:
            exakt += 1
        else:
            abweichend += 1

    return {"geprueft": len(zeilen), "exakt": exakt, "abweichend": abweichend}


def outcomes_neu_bewerten(db: Session, block: int = 10000) -> int:
    """Bewertet war_erfolgreich aller HISTORISCH-Outcomes neu.

    Muss nach jeder Änderung des Richtungssignals laufen: ob ein Outcome als
    Treffer gilt, hängt von der Signalrichtung ab (KAUF trifft bei steigendem,
    VERKAUF bei fallendem Kurs). Bleibt dieser Schritt aus, misst die
    Auswertung Treffer gegen ein Signal, das so nicht mehr existiert.

    Returns:
        Anzahl geänderter Outcome-Zeilen.
    """
    from snapshot_engine.models import AnalyseSnapshotOutcome, erfolg_bewerten

    zeilen = (
        db.query(AnalyseSnapshotOutcome, AnalyseSnapshot.richtungssignal,
                 AnalyseSnapshot.kurs_bei_snapshot)
        .join(AnalyseSnapshot, AnalyseSnapshot.id == AnalyseSnapshotOutcome.snapshot_id)
        .filter(AnalyseSnapshot.datenmodus == Datenmodus.HISTORISCH)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .all()
    )

    geaendert = 0
    for index, (outcome, richtungssignal, kurs_start) in enumerate(zeilen, start=1):
        if outcome.outcome_kurs is None:
            continue
        # Gegen dieselbe Basis bewerten, gegen die outcome_return gerechnet
        # wurde. Sonst könnten Treffer-Flag und Return einander widersprechen,
        # wenn zwischen Snapshot und Fälligkeit ein Split lag.
        basis = outcome.basis_kurs if outcome.basis_kurs else kurs_start
        neu = erfolg_bewerten(richtungssignal, basis, outcome.outcome_kurs)
        if neu != outcome.war_erfolgreich:
            outcome.war_erfolgreich = neu
            geaendert += 1
        if index % block == 0:
            db.commit()

    db.commit()
    logger.info("Neugewichtung: %d von %d Outcomes neu bewertet.", geaendert, len(zeilen))
    return geaendert


def historische_snapshots_neu_gewichten(
    db: Session,
    neue_gewichte: Optional[dict] = None,
    nur_simulieren: bool = False,
    block: int = 5000,
) -> dict:
    """Rechnet Confidence und Richtungssignal aller HISTORISCH-Snapshots neu.

    Args:
        neue_gewichte: Zielgewichte (default: renormalisierte WEIGHTS_FULL,
                       also exakt das, was calc_technical_score verwendet)
        nur_simulieren: True → nichts schreiben, nur die Auswirkung berichten
        block: Commit-Blockgröße

    Returns:
        Kennzahlen zur Auswirkung.
    """
    from services.scoring import (
        TECHNISCHE_KATEGORIEN, WEIGHTS_FULL, _renormalisierte_gewichte,
    )
    from snapshot_engine.snapshot_service import richtung_aus_confidence

    if neue_gewichte is None:
        neue_gewichte = _renormalisierte_gewichte(WEIGHTS_FULL, TECHNISCHE_KATEGORIEN)

    gewichte_json = json.dumps(neue_gewichte)

    snapshots = (
        db.query(AnalyseSnapshot)
        .filter(AnalyseSnapshot.datenmodus == Datenmodus.HISTORISCH)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .all()
    )

    ergebnis = {
        "gesamt": len(snapshots),
        "geaendert": 0,
        "signal_gewechselt": 0,
        "uebersprungen": 0,
        "simuliert": nur_simulieren,
    }
    deltas: list[float] = []

    for index, snapshot in enumerate(snapshots, start=1):
        if not (snapshot.indikator_json and snapshot.cat_max_json):
            ergebnis["uebersprungen"] += 1
            continue

        try:
            cat_scores = json.loads(snapshot.indikator_json)
            cat_max = json.loads(snapshot.cat_max_json)
        except (json.JSONDecodeError, TypeError):
            ergebnis["uebersprungen"] += 1
            continue

        neue_confidence = confidence_berechnen(cat_scores, cat_max, neue_gewichte)
        neues_signal = richtung_aus_confidence(neue_confidence)

        deltas.append(neue_confidence - (snapshot.confidence or 0))
        if abs(neue_confidence - (snapshot.confidence or 0)) >= 0.05:
            ergebnis["geaendert"] += 1
        if neues_signal != snapshot.richtungssignal:
            ergebnis["signal_gewechselt"] += 1

        if not nur_simulieren:
            snapshot.confidence = neue_confidence
            snapshot.confidence_label = _label_fuer(neue_confidence)
            snapshot.richtungssignal = neues_signal
            # Gewichte mitschreiben, damit die Zeile selbsterklärend bleibt
            snapshot.weights_json = gewichte_json

            if index % block == 0:
                db.commit()
                logger.info("Neugewichtung: %d/%d Snapshots verarbeitet.",
                            index, len(snapshots))

    if not nur_simulieren:
        db.commit()
        # Zwingend: war_erfolgreich in den Outcomes leitet sich aus dem
        # Richtungssignal ab. Ohne diesen Schritt bewerten die Outcomes noch
        # gegen das ALTE Signal — die Trefferquoten wären still falsch.
        ergebnis["outcomes_neu_bewertet"] = outcomes_neu_bewerten(db)

    if deltas:
        ergebnis["delta_min"] = round(min(deltas), 1)
        ergebnis["delta_max"] = round(max(deltas), 1)
        ergebnis["delta_schnitt"] = round(sum(deltas) / len(deltas), 2)

    logger.info("Neugewichtung %s: %d Snapshots, %d geändert, %d Signalwechsel.",
                "simuliert" if nur_simulieren else "abgeschlossen",
                ergebnis["gesamt"], ergebnis["geaendert"],
                ergebnis["signal_gewechselt"])
    return ergebnis
