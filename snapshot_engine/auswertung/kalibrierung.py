"""
snapshot_engine/auswertung/kalibrierung.py — Confidence-Kalibrierung.

Prüft, ob die Confidence-Zahl hält, was sie verspricht: Führen höhere
Confidence-Werte tatsächlich zu besseren Ergebnissen? Eine gut kalibrierte
Engine zeigt eine monoton steigende Kurve — flach oder fallend bedeutet, dass
die Zahl keine Aussagekraft hat.

Löst services/signal_history.calc_calibration_chart() ab, jetzt aber getrennt
nach Datenmodus und Horizont.
"""

import logging

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_steigend, kennzahlen_aus_returns, mit_basis,
)
from snapshot_engine.auswertung.kennzahlen import RICHTUNG_JE_SIGNAL

logger = logging.getLogger(__name__)

# Confidence-Bereiche entsprechend der Labels in services/scoring.py
CONFIDENCE_BEREICHE = [
    {"label": "0–29 (Starkes Verkaufssignal)", "min": 0, "max": 29.99},
    {"label": "30–44 (Verkaufstendenz)", "min": 30, "max": 44.99},
    {"label": "45–59 (Neutral)", "min": 45, "max": 59.99},
    {"label": "60–74 (Kauftendenz)", "min": 60, "max": 74.99},
    {"label": "75–100 (Starkes Kaufsignal)", "min": 75, "max": 100},
]


def kalibrierung_berechnen(db: Session, horizont: int = 7,
                           datenmodus: str | None = None,
                           minimum: int = MIN_STICHPROBE) -> list[dict]:
    """Ermittelt Ergebnis-Kennzahlen je Confidence-Bereich.

    Returns:
        Eine Zeile je Bereich (immer alle Bereiche, auch leere — eine Lücke
        ist selbst eine Aussage über die Datenlage).
    """
    ergebnis = []

    try:
        # Nur die drei benötigten Spalten statt ganzer ORM-Objekte (Performance
        # bei sechsstelligen Zeilenzahlen).
        paare = (
            db.query(AnalyseSnapshot.confidence,
                     AnalyseSnapshotOutcome.outcome_return,
                     AnalyseSnapshotOutcome.war_erfolgreich,
                     AnalyseSnapshot.richtungssignal)
            .join(AnalyseSnapshotOutcome,
                  AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
            .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
            .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
            .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
            .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        )
        if datenmodus:
            paare = paare.filter(AnalyseSnapshot.datenmodus == datenmodus)
        alle = paare.all()

    except Exception as e:
        logger.error("Kalibrierung fehlgeschlagen: %s", e, exc_info=True)
        return []

    # Vergleichsbasis über den gesamten Zeitraum, nicht je Band — sie soll
    # unabhängig von der Confidence sein, gegen die sie verglichen wird.
    anteil = anteil_steigend([r for _, r, _, _ in alle])

    for bereich in CONFIDENCE_BEREICHE:
        gruppe = [z for z in alle
                  if bereich["min"] <= (z[0] or 0) <= bereich["max"]]

        # Die Bänder mischen KAUF und VERKAUF (niedrige Confidence = Verkauf).
        # Ohne Richtung würde ein erfolgreiches Verkaufssignal als Verlust zählen.
        richtungen = [RICHTUNG_JE_SIGNAL.get(s) for _, _, _, s in gruppe]

        kennzahlen = mit_basis(
            kennzahlen_aus_returns(
                [r for _, r, _, _ in gruppe],
                [t for _, _, t, _ in gruppe],
                horizont_tage=horizont,
                minimum=minimum,
                richtungen=richtungen,
            ),
            anteil, richtungen)

        ergebnis.append({
            "bereich": bereich["label"],
            "confidence_min": bereich["min"],
            "confidence_max": bereich["max"],
            "horizont_tage": horizont,
            **kennzahlen,
        })

    return ergebnis


def kalibrierung_bewerten(zeilen: list[dict]) -> dict:
    """Fasst zusammen, ob die Confidence überhaupt Aussagekraft hat.

    Verglichen wird der Erwartungswert der auswertbaren Bereiche: steigt er
    mit der Confidence, ist die Engine kalibriert.

    Returns:
        {"status": ..., "aussage": ..., "bereiche_auswertbar": n}
    """
    from snapshot_engine.auswertung.basis import STATUS_OK

    auswertbar = [z for z in zeilen
                  if z.get("status") == STATUS_OK
                  and z.get("erwartungswert") is not None]

    if len(auswertbar) < 2:
        return {
            "status": "unbekannt",
            "aussage": "Noch zu wenig Daten für eine Kalibrierungs-Aussage.",
            "bereiche_auswertbar": len(auswertbar),
        }

    nach_confidence = sorted(auswertbar, key=lambda z: z["confidence_min"])
    werte = [z["erwartungswert"] for z in nach_confidence]

    steigend = all(b >= a for a, b in zip(werte, werte[1:]))
    spannweite = max(werte) - min(werte)

    if steigend and spannweite > 0.5:
        status, aussage = "kalibriert", (
            "Höhere Confidence führt zu besseren Ergebnissen — die Zahl trägt Information.")
    elif spannweite < 0.5:
        status, aussage = "flach", (
            "Die Ergebnisse unterscheiden sich kaum zwischen den Confidence-Bereichen — "
            "die Confidence-Zahl trennt derzeit nicht messbar.")
    else:
        status, aussage = "uneinheitlich", (
            "Kein klarer Zusammenhang zwischen Confidence und Ergebnis — "
            "die Gewichtung sollte überprüft werden.")

    return {
        "status": status,
        "aussage": aussage,
        "bereiche_auswertbar": len(auswertbar),
        "spannweite": round(spannweite, 2),
    }
