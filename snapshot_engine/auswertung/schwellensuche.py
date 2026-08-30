"""
snapshot_engine/auswertung/schwellensuche.py — Oszillator-Schwelle bestimmen (P1-07).

Die bisherige Schwelle (`services.scoring.OSZILLATOR_GATE_SCHWELLE`) wurde aus
dem Gesamtbestand gewonnen, bevor es eine Train/Holdout-Trennung gab. Sie hat
die Holdout-Zeilen also gesehen; jede Messung darauf ist rückwirkend und belegt
nichts (siehe `holdout.holdout_rueckwirkend`). Dieses Modul bestimmt die
Schwelle neu — ausschließlich auf dem Trainingsteil.

**Der Holdout ist hier unerreichbar.** `_zeilen_laden` ist fest auf `TRAIN`
verdrahtet, und es gibt keinen Parameter, der das ändert. Eine Suche, die über
den Holdout laufen könnte, würde ihn beim ersten Aufruf verbrauchen: wer 15
Schwellen durchprobiert und die beste behält, hat 15-mal aus dem Holdout
gelernt, egal wie das Ergebnis anschließend genannt wird.

Zwei Vorkehrungen gegen Überanpassung an den Trainingsteil selbst:

**1. Korrektur für Mehrfachtests.**
    Wer viele Schwellen prüft, findet mit hoher Wahrscheinlichkeit mindestens
    eine „signifikante" — allein durch Zufall. Die Fehlerspanne wird deshalb
    nach Šidák geweitet: statt 95 % je Einzeltest gilt 95 % über die gesamte
    Suche.

    Gezählt werden dabei die UNTERSCHEIDBAREN Tests, nicht die Kandidaten. Die
    normierten Oszillator-Scores sind grob gestuft, weshalb benachbarte
    Schwellen oft exakt dieselbe Zeilenmenge auswählen — 0,35 bis 0,65 trennen
    im Bestand nichts voneinander. Solche Kandidaten als eigenständige Tests zu
    zählen würde die Korrektur künstlich verschärfen und einen echten Effekt
    verwerfen. Von 13 Kandidaten bleiben so real 3 Tests.

**2. Plateau statt Spitze.**
    Gewählt wird nicht die Schwelle mit dem größten Vorsprung, sondern die
    Mitte des längsten zusammenhängenden Bereichs signifikanter Kandidaten.
    Ein einzelner Ausreißer zwischen unauffälligen Nachbarn ist fast immer
    Rauschen; ein Effekt, der über mehrere benachbarte Schwellen trägt, ist
    robust gegen die genaue Wahl. Der Preis ist ein etwas kleinerer gemessener
    Vorsprung — bezahlt für eine Zahl, die auf neuen Daten Bestand hat.

Bleibt kein Kandidat übrig, ist das Ergebnis `None`. Das ist ein zulässiges
Resultat und keine Fehlfunktion: es heißt, dass der Trainingsteil keine
Schwelle hergibt, die sich von Zufall unterscheiden lässt.
"""

import logging
import statistics
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    MIN_BEWEGUNG_PCT, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, effektive_stichprobe,
)
from snapshot_engine.auswertung.gate import _normierter_oszillator
from snapshot_engine.auswertung.holdout import TRAIN, grenze_lesen, split_filter

logger = logging.getLogger(__name__)


# Geprüfte Schwellen. Bewusst grob gerastert: eine feinere Auflösung erhöht nur
# die Zahl der Tests (und damit die Korrektur), ohne mehr Information zu
# liefern — die Oszillator-Scores sind selbst grob gestuft.
KANDIDATEN: tuple[float, ...] = (
    0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
    0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
)

# Ab dieser Confidence gilt ein Signal als Kaufempfehlung — dieselbe Schwelle,
# die `gate.gate_wirkung` und `snapshot_service.richtung_aus_confidence`
# verwenden.
CONFIDENCE_KAUF = 60.0

ALPHA = 0.05


def _z_korrigiert(anzahl_tests: int, alpha: float = ALPHA) -> float:
    """Kritischer z-Wert, geweitet auf die Zahl der Tests (Šidák).

    Bei einem einzelnen Test entspricht das 1,96. Bei 13 Kandidaten wächst der
    Wert auf rund 2,8 — der Vorsprung muss also deutlich größer ausfallen, um
    noch als Fund zu gelten.
    """
    if anzahl_tests <= 1:
        anzahl_tests = 1
    alpha_einzeln = 1.0 - (1.0 - alpha) ** (1.0 / anzahl_tests)
    return statistics.NormalDist().inv_cdf(1.0 - alpha_einzeln / 2.0)


def _fehlerspanne_korrigiert(trefferquote: float, n_effektiv: int,
                             z: float) -> Optional[float]:
    """Wie `basis.fehlerspanne_pp`, aber mit vorgegebenem z-Wert."""
    if not n_effektiv or n_effektiv <= 0:
        return None
    p = max(0.0, min(1.0, trefferquote / 100.0))
    standardfehler = (p * (1.0 - p) / n_effektiv) ** 0.5
    return round(z * standardfehler * 100.0, 1)


def _zeilen_laden(db: Session, horizont: int, datenmodus: Optional[str]) -> list:
    """Lädt die auswertbaren Zeilen — ausschließlich aus dem Trainingsteil.

    `teil` ist absichtlich kein Parameter: eine Suche über den Holdout würde
    ihn verbrauchen (siehe Modulkopf).
    """
    grenze = grenze_lesen()
    if grenze is None:
        raise ValueError(
            "Keine Train/Holdout-Grenze festgelegt — ohne Trennung wäre die "
            "Suche in-sample. Zuerst holdout.grenze_festlegen() aufrufen.")

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
    return split_filter(query, TRAIN, grenze).all()


def schwelle_suchen(db: Session, horizont: int = 30,
                    datenmodus: Optional[str] = None,
                    kandidaten: Sequence[float] = KANDIDATEN,
                    minimum: int = MIN_STICHPROBE) -> dict:
    """Bestimmt die Oszillator-Schwelle auf dem Trainingsteil.

    Returns:
        {
          "kandidaten": [ {schwelle, n, n_effektiv, trefferquote,
                           vorsprung_pp, fehlerspanne_pp, signifikant}, ... ],
          "basisrate": float,
          "z_korrigiert": float,   # geweitet auf `tests`, nicht auf len(kandidaten)
          "tests": int,            # unterscheidbare Zeilenmengen
          "plateau": [schwellen] | [],
          "empfehlung": float | None,   # None = keine Schwelle belegbar
          "begruendung": str,
        }
    """
    zeilen = _zeilen_laden(db, horizont, datenmodus)

    # Nur bewertbare Bewegungen — dieselbe Schwelle wie `erfolg_bewerten`.
    bewegt = [(i, c, conf, r) for i, c, conf, r in zeilen
              if r is not None and abs(r) >= MIN_BEWEGUNG_PCT]
    if not bewegt:
        return {"kandidaten": [], "basisrate": None, "z_korrigiert": None,
                "tests": 0, "plateau": [], "empfehlung": None,
                "begruendung": "Keine bewertbaren Beobachtungen im Trainingsteil."}

    basisrate = sum(1 for *_, r in bewegt if r > 0) / len(bewegt) * 100

    # Oszillator einmal je Zeile rekonstruieren, nicht je Kandidat.
    vorbereitet = [
        (_normierter_oszillator(i, c), conf or 0.0, r)
        for i, c, conf, r in bewegt
    ]

    # Erst alle Gruppen bilden, dann zählen, wie viele davon überhaupt
    # unterscheidbar sind — davon hängt die Stärke der Korrektur ab.
    gruppen = {
        schwelle: [r for osz, conf, r in vorbereitet
                   if conf >= CONFIDENCE_KAUF
                   and osz is not None and osz >= schwelle]
        for schwelle in kandidaten
    }
    unterscheidbar = len({tuple(werte) for werte in gruppen.values()})
    z = _z_korrigiert(unterscheidbar)
    ergebnisse = []

    for schwelle in kandidaten:
        returns = gruppen[schwelle]
        n = len(returns)
        if n == 0:
            ergebnisse.append({
                "schwelle": schwelle, "n": 0, "n_effektiv": 0,
                "trefferquote": None, "vorsprung_pp": None,
                "fehlerspanne_pp": None, "signifikant": False,
                "ausreichend": False,
            })
            continue

        quote = sum(1 for r in returns if r > 0) / n * 100
        n_eff = effektive_stichprobe(n, horizont)
        spanne = _fehlerspanne_korrigiert(quote, n_eff, z)
        vorsprung = quote - basisrate
        ausreichend = n_eff >= minimum

        ergebnisse.append({
            "schwelle": schwelle,
            "n": n,
            "n_effektiv": n_eff,
            "trefferquote": round(quote, 1),
            "vorsprung_pp": round(vorsprung, 1),
            "fehlerspanne_pp": spanne,
            # Nur ein POSITIVER Vorsprung taugt als Gate-Begründung. Ein
            # signifikant negativer wäre ein Befund, aber kein Argument für
            # genau diese Schwelle.
            "signifikant": bool(ausreichend and spanne is not None
                                and vorsprung > spanne),
            "ausreichend": ausreichend,
        })

    plateau = _laengstes_plateau(ergebnisse)
    if not plateau:
        return {
            "kandidaten": ergebnisse, "basisrate": round(basisrate, 1),
            "z_korrigiert": round(z, 2), "tests": unterscheidbar,
            "plateau": [], "empfehlung": None,
            "begruendung": (
                "Keine Schwelle übersteht die Korrektur für Mehrfachtests. "
                "Der Trainingsteil trägt kein Gate."),
        }

    empfehlung = plateau[len(plateau) // 2]
    return {
        "kandidaten": ergebnisse,
        "basisrate": round(basisrate, 1),
        "z_korrigiert": round(z, 2),
        "tests": unterscheidbar,
        "plateau": plateau,
        "empfehlung": empfehlung,
        "begruendung": (
            f"Längster zusammenhängender Bereich: {plateau[0]:.2f}–"
            f"{plateau[-1]:.2f} ({len(plateau)} Kandidaten). Gewählt wurde "
            f"dessen Mitte, nicht der größte Vorsprung."),
    }


def _laengstes_plateau(ergebnisse: list[dict]) -> list[float]:
    """Längster zusammenhängender Bereich signifikanter Kandidaten.

    Bei Gleichstand gewinnt der Bereich mit den NIEDRIGEREN Schwellen: eine
    niedrigere Schwelle lässt mehr Signale durch und stützt sich damit auf mehr
    Beobachtungen — bei gleicher Belegbarkeit die robustere Wahl.
    """
    bester: list[float] = []
    laufend: list[float] = []
    for e in ergebnisse:
        if e["signifikant"]:
            laufend.append(e["schwelle"])
            if len(laufend) > len(bester):
                bester = list(laufend)
        else:
            laufend = []
    return bester
