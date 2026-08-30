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

Warnung zur Interpretation: die Schwelle wurde AUS diesen Daten gewonnen. Ohne
`teil` gerechnet sind die Zahlen daher in-sample und bestätigen nur die
Konsistenz der Umsetzung, nicht die Gültigkeit des Effekts.

Über `teil=HOLDOUT` (siehe `auswertung/holdout.py`) lässt sich auf der
zurückgehaltenen Menge rechnen. **Für die aktuelle Schwelle ist das noch kein
Beleg:** sie wurde bestimmt, bevor die Grenze gezogen wurde, hat die
Holdout-Zeilen also bereits gesehen. Das Ergebnis weist das als
`holdout_rueckwirkend: True` aus, und `out_of_sample` bleibt in diesem Fall
False. Sauber wird es erst, wenn die Schwelle allein auf `teil=TRAIN` neu
bestimmt und danach einmal auf dem Holdout geprüft wird — siehe
SCHWELLE_BESTIMMT_AM unten.
"""

import json
import logging
from datetime import datetime  # noqa: F401  (Typangabe SCHWELLE_BESTIMMT_AM)

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    MIN_BEWEGUNG_PCT, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, effektive_stichprobe, fehlerspanne_pp,
)
from snapshot_engine.auswertung.holdout import (
    HOLDOUT, grenze_lesen, holdout_rueckwirkend, holdout_zugriff_vermerken,
    split_filter,
)

logger = logging.getLogger(__name__)


# Wann OSZILLATOR_GATE_SCHWELLE festgelegt wurde. None heißt: vor dem Ziehen
# der Holdout-Grenze, aus dem Gesamtbestand — der Holdout ist für sie also
# rückwirkend und belegt nichts.
#
# Sobald die Schwelle allein auf `teil=TRAIN` neu bestimmt wird, gehört hier
# der Zeitpunkt dieser Neubestimmung hinein; erst dann liefert
# `gate_wirkung(teil=HOLDOUT)` einen echten Out-of-Sample-Beleg.
SCHWELLE_BESTIMMT_AM: "datetime | None" = None


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
                 minimum: int = MIN_STICHPROBE,
                 teil: str | None = None) -> dict:
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

    grenze = grenze_lesen()
    ergebnis: dict = {
        "schwelle": schwelle,
        "horizont_tage": horizont,
        "teil": teil,
        # Zwei getrennte Aussagen, die nicht zusammenfallen:
        #   rueckwirkend — die Schwelle hat diese Zeilen schon gesehen
        #   out_of_sample — das Ergebnis taugt als Beleg
        # Nur wenn auf dem Holdout gerechnet wird UND die Schwelle jünger ist
        # als die Grenze, ist beides gleichzeitig erfüllt. Ein einzelnes
        # `in_sample`-Flag hätte den rückwirkenden Fall als sauber ausgewiesen.
        # Unabhängig von `teil` beantwortet: wäre eine Holdout-Messung DIESER
        # Schwelle rückwirkend? Die Frage hat auch dann eine Antwort, wenn
        # gerade auf dem Gesamtbestand gerechnet wird — und die Anzeige soll
        # sie aus dem Ergebnis lesen, statt sie als Fließtext zu behaupten,
        # der beim Neubestimmen der Schwelle still falsch wird.
        "holdout_rueckwirkend": holdout_rueckwirkend(SCHWELLE_BESTIMMT_AM),
        "out_of_sample": (teil == HOLDOUT
                          and not holdout_rueckwirkend(SCHWELLE_BESTIMMT_AM)),
        "holdout_zugriffe": None,
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
        query = split_filter(query, teil, grenze)
        zeilen = query.all()
    except ValueError:
        # Unbekannter Teil oder fehlende Grenze — ein Aufruferfehler, der
        # nicht als leeres Ergebnis durchgehen darf.
        raise
    except Exception as e:
        logger.error("Gate-Auswertung fehlgeschlagen: %s", e, exc_info=True)
        return ergebnis

    if teil == HOLDOUT:
        ergebnis["holdout_zugriffe"] = holdout_zugriff_vermerken(
            f"gate_wirkung(horizont={horizont}, datenmodus={datenmodus})")

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
