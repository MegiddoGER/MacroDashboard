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

    Beantwortet zwei getrennte Fragen, die vorher zu einer verschmolzen waren:

      1. TRENNSCHÄRFE — steigt das Ergebnis mit der Confidence?
      2. VORSPRUNG    — schlägt das beste Confidence-Band die Basisrate?

    Frage 1 allein genügt nicht. In einem steigenden Markt erzeugt schon die
    allgemeine Aufwärtsdrift eine sauber steigende Kurve: niedrige Confidence
    sind Verkaufssignale (die dann verlieren), hohe sind Kaufsignale (die dann
    gewinnen). Ein Zufallsgenerator mit derselben Signalverteilung sähe
    identisch aus. Erst der Vergleich mit der Basisrate trennt Prognosefähigkeit
    von Marktrichtung — und nur ein Vorsprung jenseits der Fehlerspanne zählt.

    Returns:
        {"status", "aussage", "bereiche_auswertbar", "spannweite",
         "trennschaerfe", "bestes_band", "vorsprung_pp",
         "vorsprung_fehler_pp", "vorsprung_signifikant"}
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
            "trennschaerfe": None,
            "bestes_band": None,
            "vorsprung_pp": None,
            "vorsprung_fehler_pp": None,
            "vorsprung_signifikant": None,
        }

    nach_confidence = sorted(auswertbar, key=lambda z: z["confidence_min"])
    werte = [z["erwartungswert"] for z in nach_confidence]

    steigend = all(b >= a for a, b in zip(werte, werte[1:]))
    spannweite = max(werte) - min(werte)

    if steigend and spannweite > 0.5:
        trennschaerfe = "steigend"
    elif spannweite < 0.5:
        trennschaerfe = "flach"
    else:
        trennschaerfe = "uneinheitlich"

    # ── Frage 2: Vorsprung des höchsten Confidence-Bandes ───────────
    # Das oberste Band trägt die stärkste Behauptung der Engine ("Starkes
    # Kaufsignal"). Hält die dem Zufall nicht stand, ist alles darunter
    # erst recht nicht handelbar.
    mit_vorsprung = [z for z in nach_confidence if z.get("vorsprung_pp") is not None]
    bestes = mit_vorsprung[-1] if mit_vorsprung else None

    vorsprung = bestes.get("vorsprung_pp") if bestes else None
    fehler = bestes.get("vorsprung_fehler_pp") if bestes else None
    signifikant = bestes.get("vorsprung_signifikant") if bestes else None

    # ── Gesamturteil ────────────────────────────────────────────────
    if bestes is None:
        status = "unbekannt"
        aussage = ("Kein Confidence-Band hat eine Basisrate zum Vergleich — "
                   "ohne Bezugspunkt ist keine Aussage möglich.")
    elif trennschaerfe == "uneinheitlich":
        status = "uneinheitlich"
        aussage = ("Kein klarer Zusammenhang zwischen Confidence und Ergebnis — "
                   "die Gewichtung sollte überprüft werden.")
    elif not signifikant:
        status = "kein_vorsprung"
        aussage = (
            f"Das höchste Confidence-Band trifft {_pp(vorsprung)} gegenüber der "
            f"Basisrate — bei einer Fehlerspanne von ±{fehler} pp ist das nicht von "
            "Zufall zu unterscheiden. Die Confidence ordnet die Ergebnisse, "
            "schlägt aber nicht messbar den Markt.")
    elif vorsprung is not None and vorsprung < 0:
        status = "negativ"
        aussage = (
            f"Das höchste Confidence-Band trifft {_pp(vorsprung)} gegenüber der "
            f"Basisrate (±{fehler} pp) — es schneidet messbar SCHLECHTER ab als "
            "Zufallsauswahl aus demselben Universum.")
    elif trennschaerfe == "flach":
        status = "flach"
        aussage = (
            "Die Ergebnisse unterscheiden sich kaum zwischen den Confidence-Bereichen — "
            "die Confidence-Zahl trennt derzeit nicht messbar.")
    else:
        status = "kalibriert"
        aussage = (
            f"Höhere Confidence führt zu besseren Ergebnissen, und das höchste Band "
            f"schlägt die Basisrate um {_pp(vorsprung)} (±{fehler} pp) — "
            "die Zahl trägt Information.")

    return {
        "status": status,
        "aussage": aussage,
        "bereiche_auswertbar": len(auswertbar),
        "spannweite": round(spannweite, 2),
        "trennschaerfe": trennschaerfe,
        "bestes_band": bestes.get("bereich") if bestes else None,
        "vorsprung_pp": vorsprung,
        "vorsprung_fehler_pp": fehler,
        "vorsprung_signifikant": signifikant,
    }


def _pp(wert: float | None) -> str:
    """Formatiert einen Vorsprung mit Vorzeichen."""
    return "—" if wert is None else f"{wert:+.1f} pp"
