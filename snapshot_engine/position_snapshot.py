"""
snapshot_engine/position_snapshot.py — Snapshots des Positionspfads (P3-03).

Der Einstiegspfad (`services/scoring.py` → `snapshot_service.signal_erfassen`)
misst seit Beginn, ob seine Prognosen eintreffen. Der Positionspfad
(`services/scoring_engine_v2.py` → `services/recommendation_engine.py`) tat das
nicht: er erzeugte keine Snapshots, und damit war keines seiner zwölf Gewichte
gegen ein Ergebnis prüfbar. Jeder Tag ohne Erfassung ist ein Tag ohne Evidenz —
für bereits getroffene Entscheidungen lässt sich die Messung nicht nachholen.

Dieses Modul schließt die Lücke, ohne ein zweites Datenmodell aufzumachen:
geschrieben wird in dieselben Tabellen wie beim Einstiegspfad, unterschieden
durch `analyse_modus = BESTEHENDE_POSITION`. Damit trägt der Nachtrag der
Outcomes (`snapshot_service.outcomes_nachtragen`, im 18:30-Lauf) den
Positionspfad ohne eine einzige Änderung mit — er filtert bewusst nicht nach
Modus, sondern arbeitet jede fällige Outcome-Zeile ab.

Feldbelegung, abweichend vom Einstiegspfad (siehe AnalyseModus-Docstring):

  confidence        Overall-Score der zwölf Teilscores (0–100). NICHT die
                    `RecommendationResult.confidence` — die liegt in [0,1] und
                    ist eine andere Größe.
  richtungssignal   aus der Empfehlung, nicht aus der Confidence.
  indikator_json    die zwölf Teilscores (Gegenstück zu den fünf cat_scores)
  cat_max_json      welche Teilscores überhaupt berechenbar waren
  weights_json      POSITION_GEWICHTE — ohne sie wäre später nicht
                    rekonstruierbar, welche Gewichtung den Overall erzeugt hat
  checklist_json    Zustand, Modus und Validierungslage als Kontext
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from services.position_types import PositionSide, RecommendationType
from services.scoring_engine_v2 import POSITION_GEWICHTE, POSITION_SCORE_VERSION
from snapshot_engine.models import (
    HORIZONTE_TAGE, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotIndikator,
    Datenmodus, ErstelltVon, Granularitaet, outcomes_anlegen,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Richtungssignal aus der Empfehlung
# ---------------------------------------------------------------------------

# Maßstab ist die EXPOSITION, die eine Empfehlung hinterlässt — nicht ihre
# Stimmung. Wer long bleibt, verdient an steigenden Kursen; die Empfehlung
# "halten" ist damit eine Wette auf genau das und wird als KAUF gemessen.
# Eine defensiv formulierte Halte-Empfehlung (Stop nachziehen, Risiko
# reduzieren) lässt die Position offen und ist deshalb ebenfalls KAUF: sie als
# VERKAUF zu führen hieße, einen Kursrückgang als Erfolg zu verbuchen, während
# der Besitzer noch investiert ist.
#
# NEUTRAL ist keine Verlegenheitskategorie, sondern die ehrliche Angabe, dass
# keine Richtungsaussage getroffen wurde: ein *_REVIEW fordert erneutes
# Hinsehen, und ein *_NOT_ALLOWED verweigert das AUFSTOCKEN, behauptet aber
# nicht, dass der Kurs fällt. `erfolg_bewerten` lässt NEUTRAL unbewertet — so
# wird der Engine weder Erfolg noch Misserfolg für eine Aussage zugerechnet,
# die sie nie gemacht hat.
_EMPFEHLUNG_HAELT_EXPOSITION: frozenset = frozenset({
    RecommendationType.NEW_ENTRY_ALLOWED,
    RecommendationType.HOLD,
    RecommendationType.NORMAL_HOLD,
    RecommendationType.HOLD_WITH_TRAILING_STOP,
    RecommendationType.HOLD_BUT_REDUCE_RISK,
    RecommendationType.PROFIT_PROTECTION_MODE,
    RecommendationType.STOP_THREATENED,
    RecommendationType.ADD_ALLOWED,
})

# Empfehlungen, die Exposition abbauen. Ein Teilverkauf wird über den Anteil
# gemessen, den er tatsächlich schließt — der verbleibende Rest ist keine
# eigene Prognose, sondern dieselbe Position in kleinerer Größe.
_EMPFEHLUNG_BAUT_AB: frozenset = frozenset({
    RecommendationType.EXIT,
    RecommendationType.PARTIAL_TAKE_PROFIT,
})


def richtung_aus_empfehlung(
    empfehlung, side: str = PositionSide.LONG) -> str:
    """Leitet KAUF/NEUTRAL/VERKAUF aus einer Empfehlung ab.

    Args:
        empfehlung: RecommendationType (oder dessen String-Wert).
        side: Richtung der Position. Bei SHORT dreht sich die Zuordnung um —
              wer short bleibt, verdient an fallenden Kursen. P3-02 hält den
              SHORT-Pfad noch geschlossen; die Umkehr steht hier trotzdem,
              damit die Messung beim Öffnen nicht still das Vorzeichen
              verliert.

    Returns:
        "KAUF", "VERKAUF" oder "NEUTRAL" (keine Richtungsaussage).
    """
    if empfehlung is None:
        return "NEUTRAL"

    try:
        typ = RecommendationType(empfehlung)
    except (ValueError, TypeError):
        logger.warning("Unbekannter Empfehlungstyp %r — als NEUTRAL gewertet.",
                       empfehlung)
        return "NEUTRAL"

    if typ in _EMPFEHLUNG_HAELT_EXPOSITION:
        haelt = True
    elif typ in _EMPFEHLUNG_BAUT_AB:
        haelt = False
    else:
        return "NEUTRAL"

    if side == PositionSide.SHORT:
        haelt = not haelt

    return "KAUF" if haelt else "VERKAUF"


# ---------------------------------------------------------------------------
# Teilscores als Indikator-Zeilen
# ---------------------------------------------------------------------------

def teilscores_schreiben(db: Session, snapshot: AnalyseSnapshot,
                         scores: dict) -> int:
    """Legt je Teilscore eine Indikator-Zeile an.

    Gegenstück zu `snapshot_service.indikatoren_schreiben`: es macht die Frage
    "trägt dieser Teilscore überhaupt etwas bei?" auswertbar, statt nur den
    Overall-Score zu speichern.

    ACHTUNG — Einheit. `beitrag_numeric` trägt hier den Teilscore selbst
    (0–100), beim Einstiegspfad dagegen einen Beitrag in ±1/±0.5. Die beiden
    Einheiten dürfen nie in derselben Statistik landen; alle drei Abfragen in
    `auswertung/indikator_stats.py` filtern deshalb auf NEUE_POSITION.

    `data_quality` wird mitgeschrieben, aber auf `Granularitaet.INFO` — es
    trägt kein Gewicht im Overall-Score (siehe POSITION_GEWICHTE). Dieselbe
    Begründung wie bei MACD im Einstiegspfad: ein Vorsprung ohne Score-Wirkung
    lässt sich nicht in eine Gewichtung übersetzen und gehört daher aus
    Leaderboards heraus, die eine Gewichtungsentscheidung stützen sollen.

    Returns:
        Anzahl geschriebener Zeilen.
    """
    geschrieben = 0

    for name, wert in scores.items():
        if name in ("overall", "has_critical_warning", "has_data_warning"):
            continue  # Kein Teilscore
        if wert is None:
            continue  # Nicht berechenbar — Fehlen steht in cat_max_json

        gewicht = POSITION_GEWICHTE.get(name)
        db.add(AnalyseSnapshotIndikator(
            snapshot=snapshot,
            indikator_name=name,
            kategorie="position",
            wert=f"{float(wert):.1f}",
            # 50 ist die neutrale Mitte jedes Teilscores, nicht 0.
            signal_text=("bullisch" if wert > 50 else
                         "bearisch" if wert < 50 else "neutral"),
            beitrag_raw=f"{float(wert):.1f}",
            beitrag_numeric=float(wert),
            granularitaet=(Granularitaet.INDIKATOR if gewicht
                           else Granularitaet.INFO),
        ))
        geschrieben += 1

    return geschrieben


# ---------------------------------------------------------------------------
# Erfassung
# ---------------------------------------------------------------------------

def position_snapshot_erfassen(
    db: Session,
    ticker: str,
    analysis,
    kurs: float,
    erstellt_von: str = ErstelltVon.POSITIONS_SEITE,
    zeitpunkt: Optional[datetime] = None,
    commit: bool = True,
) -> Optional[AnalyseSnapshot]:
    """Schreibt eine PositionAnalysis als Snapshot inkl. Teilscores und Outcomes.

    Args:
        analysis: PositionAnalysis aus `calc_position_analysis_v2`.
        kurs: Kurs zum Snapshot-Zeitpunkt (Bezugspunkt der Outcome-Rendite).
        commit: False, wenn der Aufrufer die Transaktion selbst steuert.

    Returns:
        Der erzeugte Snapshot, oder None wenn nichts Messbares vorliegt.
    """
    if analysis is None:
        return None
    if not kurs or kurs <= 0:
        logger.warning("position_snapshot_erfassen(%s): ungültiger Kurs %s — "
                       "verworfen.", ticker, kurs)
        return None

    scores = analysis.scores.to_dict() if analysis.scores else {}
    overall = scores.get("overall")
    if overall is None:
        # Ohne Overall-Score gibt es keine Prognosestärke, die sich gegen ein
        # Ergebnis halten ließe. Eine Zeile mit confidence=0 wäre schlimmer
        # als keine: sie zöge jede Kalibrierung in das unterste Band.
        logger.info("position_snapshot_erfassen(%s): kein Overall-Score — "
                    "nicht erfasst.", ticker)
        return None

    zeitpunkt = zeitpunkt or datetime.utcnow()

    empfehlung = getattr(analysis.recommendation, "primary", None)
    richtung = richtung_aus_empfehlung(empfehlung, side=analysis.side)

    # Gegenstück zu cat_max: trennt "als neutral bewertet" von "keine Daten".
    # Ein fehlender Teilscore ist kein Wert 0, sondern eine Lücke — ohne diese
    # Karte wäre beides im Nachhinein nicht mehr auseinanderzuhalten.
    verfuegbar = {
        name: (scores.get(name) is not None)
        for name in POSITION_GEWICHTE
    }
    verfuegbar["data_quality"] = scores.get("data_quality") is not None

    kontext = {
        "modus": _wert(analysis.mode),
        "empfehlung": _wert(empfehlung),
        "empfehlung_alternativ": _wert(
            getattr(analysis.recommendation, "alternative", None)),
        "side": _wert(analysis.side),
        "target_status": _wert(analysis.validation.target_status),
        "stop_status": _wert(analysis.validation.stop_status),
        "has_critical_warning": bool(scores.get("has_critical_warning")),
        "has_data_warning": bool(scores.get("has_data_warning")),
        "data_quality_score": getattr(analysis.data_quality, "score", None),
        # 0–1, nicht 0–100 — bewusst getrennt vom Feld `confidence`.
        "empfehlung_confidence": getattr(
            analysis.recommendation, "confidence", None),
    }

    snapshot = AnalyseSnapshot(
        ticker=ticker.upper(),
        snapshot_zeitpunkt=zeitpunkt,
        kurs_bei_snapshot=float(kurs),
        confidence=float(overall),
        confidence_label=_wert(
            getattr(analysis.recommendation, "status", None)) or None,
        richtungssignal=richtung,
        indikator_json=json.dumps(
            {name: scores.get(name) for name in POSITION_GEWICHTE}),
        cat_max_json=json.dumps(verfuegbar),
        weights_json=json.dumps(POSITION_GEWICHTE),
        checklist_json=json.dumps(kontext, ensure_ascii=False),
        score_version=POSITION_SCORE_VERSION,
        analyse_modus=AnalyseModus.BESTEHENDE_POSITION,
        # Der Positionspfad läuft ausschließlich auf Live-Daten. Ein
        # historischer Replay existiert für ihn nicht — er bräuchte auch die
        # Positionsdaten (Einstand, Stop, Haltedauer) von damals.
        datenmodus=Datenmodus.LIVE,
        erstellt_von=erstellt_von,
    )
    db.add(snapshot)

    teilscores_schreiben(db, snapshot, scores)

    for outcome in outcomes_anlegen(snapshot):
        db.add(outcome)

    if commit:
        db.commit()

    return snapshot


def _wert(feld) -> Optional[str]:
    """Enum → String-Wert, alles andere unverändert als String."""
    if feld is None:
        return None
    return getattr(feld, "value", None) or str(feld)


# ---------------------------------------------------------------------------
# Kadenz-Regel
# ---------------------------------------------------------------------------

_MIN_HORIZONT = min(HORIZONTE_TAGE)


def ist_position_snapshot_faellig(
    db: Session,
    ticker: str,
    richtung_neu: Optional[str] = None,
    zeitpunkt: Optional[datetime] = None,
) -> bool:
    """Prüft, ob für eine Position ein neuer Snapshot angelegt werden soll.

    Gleiche Begründung wie `snapshot_service.ist_snapshot_faellig`, und hier
    sogar dringender: die Positionsseite wird beim Prüfen einer Position
    mehrfach am Tag aufgerufen, teils mit unverändertem Formularinhalt. Ohne
    Kadenz sähe die Statistik nach hunderten unabhängigen Beobachtungen aus,
    wäre real aber eine einzige — und jede Trefferquote damit scheinbar
    signifikant.

    Fällig ist eine Position, wenn noch kein Snapshot existiert, der kürzeste
    Horizont abgelaufen ist, oder sich das Richtungssignal geändert hat.
    """
    zeitpunkt = zeitpunkt or datetime.utcnow()

    letzter = (
        db.query(AnalyseSnapshot)
        .filter(AnalyseSnapshot.ticker == ticker.upper())
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.BESTEHENDE_POSITION)
        .order_by(AnalyseSnapshot.snapshot_zeitpunkt.desc())
        .first()
    )

    if letzter is None:
        return True

    if letzter.snapshot_zeitpunkt + timedelta(days=_MIN_HORIZONT) <= zeitpunkt:
        return True

    if richtung_neu and richtung_neu != letzter.richtungssignal:
        return True

    return False
