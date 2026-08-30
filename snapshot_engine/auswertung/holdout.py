"""
snapshot_engine/auswertung/holdout.py — Train/Holdout-Trennung (P1-05).

Jede bisher gemessene Zahl ist in-sample: die Oszillator-Schwelle wurde aus
denselben 83.606 Beobachtungen gewonnen, an denen `gate.py` sie anschließend
prüft. Solange das so bleibt, bestätigt jede Gewichtsanpassung nur sich selbst.
Dieses Modul stellt die Trennung bereit, ohne die jede weitere Optimierung
wertlos wäre.

Drei Entscheidungen tragen das Modul:

**1. Zeitlich getrennt, nicht zufällig.**
    Ein zufälliger Zeilen-Split leckt auf zwei Wegen: derselbe Ticker taucht
    mit überlappenden Horizonten in beiden Mengen auf, und beide Mengen teilen
    dieselben Marktphasen. Ein Zeit-Split bildet außerdem ab, was real
    passiert — man schätzt an der Vergangenheit und handelt die Zukunft.
    Ein Ticker-Split (disjunkte Titel) beantwortet andere, querschnittliche
    Fragen; er ist eine Ergänzung, kein Ersatz, und hier bewusst nicht gebaut.

**2. Eine Sperrzone zwischen beiden Mengen (Embargo).**
    Ein Trainings-Snapshot vom Tag X trägt ein Ergebnis, das erst an X+90
    feststeht. Grenzte Holdout unmittelbar an, wäre dieses Label teilweise aus
    Kursbewegungen INNERHALB des Holdout-Zeitraums bestimmt — Leckage durch die
    Hintertür. Die Spanne [grenze, grenze + EMBARGO_TAGE) gehört daher zu
    keiner der beiden Mengen und fällt ersatzlos weg.

**3. Die Grenze steht fest und wird gespeichert.**
    Der eigentliche Fallstrick. Würde die Grenze als Perzentil über die
    vorhandenen Daten berechnet, verschöbe sie sich mit jedem neuen Snapshot:
    was gestern Holdout war, wäre morgen Training. Die Trennung sähe intakt aus
    und wäre wertlos. Die Grenze wird deshalb EINMAL aus dem Bestand bestimmt,
    in der `Setting`-Tabelle abgelegt und danach nur noch gelesen. Ein
    Zurücksetzen ist möglich, aber ein ausdrücklicher Vorgang mit Protokoll.

**Zur Benutzung:** ein Holdout, den man nach jeder Änderung erneut befragt, ist
nur ein langsameres Trainingsset. `holdout_zugriff_vermerken()` zählt die
Abrufe mit, damit sichtbar bleibt, wie oft er schon verbraucht wurde.

**Rückwirkend gilt nicht.** Die Trennung schützt nur, was nach ihr entstanden
ist. Alles, was vorher aus dem Gesamtbestand gewonnen wurde — die
Oszillator-Schwelle etwa —, hat die Holdout-Zeilen bereits gesehen; eine
Messung darauf sieht out-of-sample aus und ist es nicht. `holdout_rueckwirkend()`
benennt diesen Fall, statt ihn hinter einem Gütesiegel zu verstecken.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_setting, set_setting
from snapshot_engine.models import (
    HORIZONTE_TAGE, AnalyseModus, AnalyseSnapshot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

TRAIN = "train"
EMBARGO = "embargo"
HOLDOUT = "holdout"

TEILE: tuple[str, ...] = (TRAIN, EMBARGO, HOLDOUT)

# Anteil der Zeitspanne, der als Holdout zurückgehalten wird. Bemessen auf der
# ZEITACHSE, nicht auf der Zeilenzahl: die Snapshot-Dichte schwankt (der
# Backfill erzeugt gleichmäßig, der Live-Lauf nur an Handelstagen), ein
# Zeilen-Perzentil ergäbe daher eine schiefe Grenze.
HOLDOUT_ANTEIL = 0.25

# Sperrzone zwischen Training und Holdout — mindestens der längste Horizont,
# sonst reicht ein Trainings-Label in den Holdout-Zeitraum hinein.
EMBARGO_TAGE = max(HORIZONTE_TAGE)

_GRENZE_KEY = "auswertung_holdout_grenze"
_ZUGRIFFE_KEY = "auswertung_holdout_zugriffe"
# Wann die Grenze gezogen wurde — nicht wo sie liegt. Der Unterschied ist der
# Kern von `holdout_rueckwirkend()`.
_FESTGELEGT_KEY = "auswertung_holdout_festgelegt_am"

# Unterhalb dieser Spanne lohnt keine Trennung: das Embargo fräse den Bestand
# auf, und beide Mengen blieben zu klein für eine Aussage.
_MIN_SPANNE_TAGE = 3 * EMBARGO_TAGE


# ---------------------------------------------------------------------------
# Grenze bestimmen und lesen
# ---------------------------------------------------------------------------

def grenze_lesen() -> Optional[datetime]:
    """Die gespeicherte Grenze, oder None wenn noch keine festgelegt wurde."""
    roh = get_setting(_GRENZE_KEY)
    if not roh:
        return None
    try:
        return datetime.fromisoformat(roh)
    except ValueError:
        logger.error("Holdout-Grenze %r ist unlesbar — wird ignoriert.", roh)
        return None


def grenze_festlegen(db: Session, anteil: float = HOLDOUT_ANTEIL,
                     neu: bool = False) -> Optional[datetime]:
    """Bestimmt die Grenze aus dem Bestand und speichert sie dauerhaft.

    Beim zweiten Aufruf wird die gespeicherte Grenze zurückgegeben, ohne neu
    zu rechnen — genau das ist der Zweck: eine Grenze, die sich mit dem
    Datenbestand mitbewegt, trennt nichts.

    Args:
        anteil: Anteil der Zeitspanne, der Holdout wird (0 < anteil < 1).
        neu:    True verwirft eine bestehende Grenze. Ausdrücklicher Vorgang —
                alle bis dahin auf dem Holdout erhobenen Zahlen verlieren damit
                ihre Aussagekraft, weil deren Beobachtungen anschließend im
                Training liegen können.

    Returns:
        Die Grenze, oder None wenn der Bestand die Spanne nicht hergibt.
    """
    if not 0 < anteil < 1:
        raise ValueError(f"anteil muss zwischen 0 und 1 liegen, war {anteil}")

    vorhanden = grenze_lesen()
    if vorhanden and not neu:
        return vorhanden

    frueheste, spaeteste = _spanne(db)
    if frueheste is None or spaeteste is None:
        logger.warning("Holdout: kein Bestand — keine Grenze festgelegt.")
        return None

    spanne = (spaeteste - frueheste).days
    if spanne < _MIN_SPANNE_TAGE:
        logger.warning(
            "Holdout: Spanne von %d Tagen zu kurz (mindestens %d) — "
            "keine Grenze festgelegt.", spanne, _MIN_SPANNE_TAGE)
        return None

    # Der Holdout ist das JÜNGSTE Stück der Zeitachse. Die Sperrzone wird ihm
    # vorgelagert, geht also vom Training ab — nicht vom Holdout, der sonst
    # bei jeder Embargo-Änderung eine andere Menge wäre.
    holdout_start = spaeteste - timedelta(days=int(spanne * anteil))
    grenze = holdout_start - timedelta(days=EMBARGO_TAGE)

    if grenze <= frueheste:
        logger.warning("Holdout: Grenze läge vor dem ersten Snapshot — "
                       "keine Grenze festgelegt.")
        return None

    set_setting(_GRENZE_KEY, grenze.isoformat())
    set_setting(_FESTGELEGT_KEY, datetime.utcnow().isoformat())
    if neu:
        set_setting(_ZUGRIFFE_KEY, "0")
    logger.info(
        "Holdout-Grenze festgelegt: %s (Training bis dahin, Sperrzone %d Tage, "
        "Holdout ab %s).", grenze.date(), EMBARGO_TAGE, holdout_start.date())
    return grenze


def _spanne(db: Session) -> tuple[Optional[datetime], Optional[datetime]]:
    """Frühester und spätester Snapshot-Zeitpunkt des Einstiegspfads."""
    zeile = db.query(
        func.min(AnalyseSnapshot.snapshot_zeitpunkt),
        func.max(AnalyseSnapshot.snapshot_zeitpunkt),
    ).filter(
        AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION
    ).one()
    return zeile[0], zeile[1]


# ---------------------------------------------------------------------------
# Zuordnung und Filterung
# ---------------------------------------------------------------------------

def split_zuordnen(zeitpunkt: datetime,
                   grenze: Optional[datetime]) -> Optional[str]:
    """Ordnet einen Snapshot-Zeitpunkt einer der drei Mengen zu.

    Returns:
        TRAIN, EMBARGO, HOLDOUT — oder None, wenn keine Grenze existiert.
    """
    if grenze is None or zeitpunkt is None:
        return None
    if zeitpunkt < grenze:
        return TRAIN
    if zeitpunkt < grenze + timedelta(days=EMBARGO_TAGE):
        return EMBARGO
    return HOLDOUT


def split_filter(query, teil: Optional[str], grenze: Optional[datetime]):
    """Schränkt eine Query auf eine der Mengen ein.

    `teil=None` lässt die Query unverändert — das ist der Gesamtbestand und
    damit ausdrücklich in-sample. Aufrufer sollen diesen Fall als solchen
    ausweisen, statt ihn als Ergebnis zu verkaufen.

    Raises:
        ValueError: bei unbekanntem `teil`. Ein Tippfehler darf nicht
            stillschweigend zum ungefilterten Gesamtbestand führen — das wäre
            genau die Vermischung, die dieses Modul verhindern soll.
    """
    if teil is None:
        return query
    if teil not in TEILE:
        raise ValueError(f"Unbekannter Teil {teil!r} — erlaubt: {TEILE}")
    if grenze is None:
        raise ValueError(
            f"Teil {teil!r} verlangt eine festgelegte Grenze "
            f"(grenze_festlegen() wurde nie erfolgreich aufgerufen).")

    spalte = AnalyseSnapshot.snapshot_zeitpunkt
    embargo_ende = grenze + timedelta(days=EMBARGO_TAGE)

    if teil == TRAIN:
        return query.filter(spalte < grenze)
    if teil == EMBARGO:
        return query.filter(spalte >= grenze, spalte < embargo_ende)
    return query.filter(spalte >= embargo_ende)


# ---------------------------------------------------------------------------
# Verbrauch des Holdouts
# ---------------------------------------------------------------------------

def holdout_zugriff_vermerken(zweck: str) -> int:
    """Zählt einen Holdout-Abruf mit und protokolliert ihn.

    Ein Holdout verliert seine Aussagekraft nicht schlagartig, sondern
    allmählich: wer nach jeder Änderung erneut auf ihm misst und nur die beste
    Variante behält, hat ihn zum Trainingsset gemacht — nur langsamer. Die
    Zahl steht deshalb neben jedem Holdout-Ergebnis.

    Returns:
        Der neue Zählerstand.
    """
    try:
        stand = int(get_setting(_ZUGRIFFE_KEY) or "0")
    except ValueError:
        stand = 0
    stand += 1
    set_setting(_ZUGRIFFE_KEY, str(stand))
    logger.info("Holdout-Zugriff Nr. %d: %s", stand, zweck)
    return stand


def holdout_zugriffe() -> int:
    """Bisherige Anzahl Holdout-Abrufe (ohne selbst einen zu zählen)."""
    try:
        return int(get_setting(_ZUGRIFFE_KEY) or "0")
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Rückwirkende Holdouts
# ---------------------------------------------------------------------------

def grenze_festgelegt_am() -> Optional[datetime]:
    """Zeitpunkt, zu dem die Grenze gezogen wurde (nicht: wo sie liegt)."""
    roh = get_setting(_FESTGELEGT_KEY)
    if not roh:
        return None
    try:
        return datetime.fromisoformat(roh)
    except ValueError:
        return None


def holdout_rueckwirkend(parameter_bestimmt_am: Optional[datetime]) -> bool:
    """Ob der Holdout für einen Parameter nur SCHEINBAR out-of-sample ist.

    Die Trennung schützt nur, was nach ihr entstanden ist. Ein Parameter, der
    VOR dem Ziehen der Grenze aus dem Gesamtbestand gewonnen wurde — wie die
    Oszillator-Schwelle —, hat die Holdout-Zeilen bereits gesehen. Die Zeilen
    danach als Holdout zu befragen liefert eine Zahl, die out-of-sample
    aussieht und es nicht ist. Genau diese Selbsttäuschung soll P1-05
    verhindern; sie unbenannt zu lassen wäre schlimmer als gar keine Trennung,
    weil sie sich hinter einem Gütesiegel versteckte.

    Args:
        parameter_bestimmt_am: Wann der geprüfte Parameter festgelegt wurde.
            None heißt "unbekannt" — dann gilt er als rückwirkend, weil die
            Unschuldsvermutung hier in die falsche Richtung schützen würde.

    Returns:
        True, wenn das Ergebnis NICHT als Beleg taugt.
    """
    gezogen = grenze_festgelegt_am()
    if gezogen is None:
        return True
    if parameter_bestimmt_am is None:
        return True
    return parameter_bestimmt_am < gezogen


# ---------------------------------------------------------------------------
# Status für Anzeige und Diagnose
# ---------------------------------------------------------------------------

def split_status(db: Session, datenmodus: Optional[str] = None) -> dict:
    """Belegung der drei Mengen — Grundlage jeder Anzeige.

    Legt KEINE Grenze an. Ob getrennt wird, ist eine bewusste Entscheidung und
    soll nicht als Nebenwirkung eines Seitenaufrufs passieren.
    """
    grenze = grenze_lesen()
    status: dict = {
        "grenze": grenze,
        "embargo_tage": EMBARGO_TAGE,
        "holdout_start": (grenze + timedelta(days=EMBARGO_TAGE)
                          if grenze else None),
        "zugriffe": holdout_zugriffe(),
        "festgelegt_am": grenze_festgelegt_am(),
        "anzahl": {teil: 0 for teil in TEILE},
        "aktiv": grenze is not None,
    }
    if grenze is None:
        return status

    for teil in TEILE:
        query = db.query(func.count(AnalyseSnapshot.id)).filter(
            AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        if datenmodus:
            query = query.filter(AnalyseSnapshot.datenmodus == datenmodus)
        status["anzahl"][teil] = split_filter(query, teil, grenze).scalar() or 0

    return status
