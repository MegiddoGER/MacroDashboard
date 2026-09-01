"""
snapshot_engine/auswertung/analyst_revisions.py — Tragen Analystenrevisionen? (P2-06)

Zweiter Kandidat aus §5, der nicht aus Kursen stammt. PEAD (§2e) hat gezeigt,
dass die fundamentale Herkunft allein nichts garantiert: die Kaufseite war dort
genauso still wie bei jeder Kursformel, nur die Miss-Seite trug. Diese Messung
prüft, ob die Revisionen es besser machen.

**Zwei Signale aus denselben Zeilen, mit verschiedener Bauweise.**

`ziel_revision` — mittlere prozentuale Kurszieländerung im Rückschaufenster.
Stetig, deshalb Perzentilrang je Kalenderwoche und Handelsplatz, dann
Quintile. Genau wie bei `momentum.raenge_berechnen`, und aus demselben Grund:
die Snapshots liegen nicht auf gemeinsamen Stichtagen, weil der Backfill je
Ticker über dessen eigene Bars gelaufen ist.

`netto_rating` — Heraufstufungen minus Herabstufungen im Fenster. Eine kleine
ganze Zahl, die meistens null ist. **Ränge sind dafür das falsche Werkzeug:**
`perzentil_raenge` gibt Bindungsgruppen den Durchschnittsrang, und eine
Mehrheit von Nullen bekäme damit einen einzigen Rang in der Mitte — die
Quintilgrenzen lägen anschließend willkürlich innerhalb dieser Gruppe. Gruppiert
wird deshalb direkt nach Wert, mit der Null als eigener, benannter Gruppe.

**Warum das Fenster und nicht das einzelne Ereignis.** Anders als Quartalszahlen
kommen Analystenhandlungen unregelmäßig und in Trauben: ein Titel bekommt zehn
in einer Woche und dann monatelang keine. Ein einzelnes Ereignis wäre deshalb
keine vergleichbare Beobachtung. Verdichtet wird über
`analyst_revisions.FENSTER_TAGE`.

**Look-ahead** wie bei PEAD über `MIN_ABSTAND_TAGE`; **der Holdout** bleibt
unberührt, `teil` ist mit TRAIN vorbelegt.
"""

import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from services.analyst_revisions import (
    FENSTER_TAGE, MIN_ABSTAND_TAGE, fenster_verdichten, handlungen_je_ticker,
)
from services.cross_sectional_momentum import raenge_je_gruppe
from snapshot_engine.benchmark import benchmark_fuer, ueberrendite
from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, zelle_gegen_markt, z_korrigiert,
)
from snapshot_engine.auswertung.holdout import TRAIN, grenze_lesen, split_filter

logger = logging.getLogger(__name__)


QUANTILE = 5

# Mindestbesetzung eines Wochenquerschnitts. Wie bei Momentum: darunter bildet
# ein Quintil eine Handvoll Titel ab und ist keine Rangaussage mehr.
MIN_QUERSCHNITT = 20

# Wertegruppen für `netto_rating`. Die Null steht bewusst allein: sie ist die
# Mehrheit und bedeutet etwas anderes als "leicht positiv" — nämlich, dass sich
# im Fenster kein Haus bewegt hat oder Auf- und Abstufungen sich aufhoben.
NETTO_GRUPPEN: tuple[tuple[str, int, int], ...] = (
    ("<= -2", -10**6, -2),
    ("-1", -1, -1),
    ("0", 0, 0),
    ("+1", 1, 1),
    (">= +2", 2, 10**6),
)


def netto_gruppe(wert: Optional[int]) -> Optional[str]:
    """Wertegruppe eines Netto-Ratings, oder None."""
    if wert is None:
        return None
    for name, von, bis in NETTO_GRUPPEN:
        if von <= wert <= bis:
            return name
    return None


def quintil(rang: Optional[float]) -> Optional[int]:
    """Quintil 1–5 zu einem Perzentilrang; 5 ist die stärkste Anhebung."""
    if rang is None:
        return None
    return min(QUANTILE, int(rang // (100.0 / QUANTILE)) + 1)


# ---------------------------------------------------------------------------
# Verdichtung je Snapshot
# ---------------------------------------------------------------------------

def _verdichtungen(db: Session, datenmodus: str) -> dict[int, dict]:
    """Je Snapshot die verdichteten Analystenhandlungen des Rückschaufensters.

    Läuft über ALLE Snapshots des Datenmodus, nicht nur über den
    Trainingsteil: ein Rang ist ein Eingang, kein Label, und ein auf den
    Trainingsteil verkürzter Querschnitt wäre verstümmelt, ohne vor
    Überanpassung zu schützen (dieselbe Entscheidung wie in `momentum.py`).
    """
    reihen = handlungen_je_ticker(db)
    logger.info("Revisionen: Protokolle für %d Ticker geladen.", len(reihen))

    snapshots = (
        db.query(AnalyseSnapshot.id, AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .all()
    )

    ergebnis: dict[int, dict] = {}
    ohne = 0
    for snapshot_id, ticker, zeitpunkt in snapshots:
        verdichtet = fenster_verdichten(reihen.get(ticker), zeitpunkt)
        if verdichtet is None:
            ohne += 1
            continue
        verdichtet["ticker"] = ticker
        verdichtet["zeitpunkt"] = zeitpunkt
        ergebnis[snapshot_id] = verdichtet

    logger.info("Revisionen: %d Snapshots mit Handlungen im Fenster (%d Tage), "
                "%d ohne.", len(ergebnis), FENSTER_TAGE, ohne)
    return ergebnis


def zielrevision_raenge(db: Session, verdichtungen: dict[int, dict],
                        minimum_querschnitt: int = MIN_QUERSCHNITT
                        ) -> dict[int, float]:
    """Perzentilrang der Zielrevision je Snapshot, je Kalenderwoche und Platz."""
    eimer: dict[tuple, dict[str, Optional[float]]] = defaultdict(dict)
    zuordnung: dict[tuple, list[tuple]] = defaultdict(list)

    for snapshot_id, daten in verdichtungen.items():
        wert = daten.get("ziel_revision")
        if wert is None:
            continue
        jahr, woche, _ = daten["zeitpunkt"].isocalendar()
        schluessel = (jahr, woche)
        # Mehrere Snapshots desselben Tickers in einer Woche sind möglich; der
        # spätere gewinnt, sonst stünde derselbe Titel zweimal im Querschnitt.
        eimer[schluessel][daten["ticker"]] = wert
        zuordnung[schluessel].append((snapshot_id, daten["ticker"]))

    raenge: dict[int, float] = {}
    for schluessel, werte in eimer.items():
        gerangt = raenge_je_gruppe(werte, benchmark_fuer, minimum_querschnitt)
        for snapshot_id, ticker in zuordnung[schluessel]:
            if ticker in gerangt:
                raenge[snapshot_id] = gerangt[ticker]

    logger.info("Revisionen: %d Snapshots nach Zielrevision gerangt.", len(raenge))
    return raenge


# ---------------------------------------------------------------------------
# Beobachtungen
# ---------------------------------------------------------------------------

def _outcome_zeilen(db: Session, horizont: int, datenmodus: str,
                    teil: Optional[str]) -> list:
    """(snapshot_id, outcome_return, benchmark_return) je auswertbarer Zeile."""
    query = (
        db.query(AnalyseSnapshot.id,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.benchmark_return)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
    )
    if teil:
        query = split_filter(query, teil, grenze_lesen())
    return query.all()


def _auswerten(gruppen: dict, alle_ueberrenditen: list, horizont: int,
               minimum: int, schluesselname: str, zaehlwerk: dict) -> dict:
    """Gemeinsamer Abschluss beider Signale: Basis, Korrektur, Zeilen."""
    if not gruppen:
        return {"basis_markt": None, "n_gesamt": 0, "gruppen": [],
                "z_korrigiert": None, "zaehlwerk": zaehlwerk,
                "horizont_tage": horizont}

    # Marktquote über GENAU die Zeilen, die auch in die Gruppen eingehen.
    basis_markt = anteil_schlaegt_markt(alle_ueberrenditen)
    z = z_korrigiert(len(gruppen))

    zeilen = []
    for schluessel in sorted(gruppen):
        paare = gruppen[schluessel]
        zeilen.append({
            schluesselname: schluessel,
            "horizont_tage": horizont,
            **zelle_gegen_markt([r for r, _ in paare], [u for _, u in paare],
                                basis_markt, horizont, minimum=minimum, z=z),
        })

    return {
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "n_gesamt": sum(len(v) for v in gruppen.values()),
        "gruppen": zeilen,
        "z_korrigiert": round(z, 2),
        "zaehlwerk": zaehlwerk,
        "horizont_tage": horizont,
    }


def zielrevision_auswerten(db: Session, horizont: int = 30,
                           datenmodus: str = "HISTORISCH",
                           teil: Optional[str] = TRAIN,
                           minimum: int = MIN_STICHPROBE) -> dict:
    """Quintile der mittleren Kurszielrevision gegen den Markt.

    Trägt das Signal, muss Quintil 5 (stärkste Anhebungen) über und Quintil 1
    (stärkste Senkungen) unter der Marktquote liegen, mit einigermaßen
    monotonem Verlauf. Eine einzelne herausragende Zelle ohne Verlauf wäre
    Mehrfachtest, kein Signal.
    """
    verdichtungen = _verdichtungen(db, datenmodus)
    raenge = zielrevision_raenge(db, verdichtungen)

    zaehlwerk = {"zeilen": 0, "ohne_verdichtung": 0, "ohne_rang": 0,
                 "verwertet": 0}
    gruppen: dict[int, list[tuple]] = defaultdict(list)
    alle: list[Optional[float]] = []

    for snapshot_id, ret, benchmark in _outcome_zeilen(db, horizont,
                                                       datenmodus, teil):
        zaehlwerk["zeilen"] += 1
        if snapshot_id not in verdichtungen:
            zaehlwerk["ohne_verdichtung"] += 1
            continue
        q = quintil(raenge.get(snapshot_id))
        if q is None:
            zaehlwerk["ohne_rang"] += 1
            continue
        zaehlwerk["verwertet"] += 1
        u = ueberrendite(ret, benchmark)
        alle.append(u)
        gruppen[q].append((ret, u))

    logger.info("Zielrevision: %d Zeilen, %d verwertet.",
                zaehlwerk["zeilen"], zaehlwerk["verwertet"])
    ergebnis = _auswerten(gruppen, alle, horizont, minimum, "quintil", zaehlwerk)
    ergebnis["teil"] = teil
    ergebnis["spread_pp"] = _spread(ergebnis["gruppen"], "quintil",
                                    QUANTILE, 1)
    return ergebnis


def netto_rating_auswerten(db: Session, horizont: int = 30,
                           datenmodus: str = "HISTORISCH",
                           teil: Optional[str] = TRAIN,
                           minimum: int = MIN_STICHPROBE) -> dict:
    """Wertegruppen des Netto-Ratings (Herauf minus Herab) gegen den Markt."""
    verdichtungen = _verdichtungen(db, datenmodus)

    zaehlwerk = {"zeilen": 0, "ohne_verdichtung": 0, "ohne_gruppe": 0,
                 "verwertet": 0}
    gruppen: dict[str, list[tuple]] = defaultdict(list)
    alle: list[Optional[float]] = []

    for snapshot_id, ret, benchmark in _outcome_zeilen(db, horizont,
                                                       datenmodus, teil):
        zaehlwerk["zeilen"] += 1
        daten = verdichtungen.get(snapshot_id)
        if daten is None:
            zaehlwerk["ohne_verdichtung"] += 1
            continue
        gruppe = netto_gruppe(daten.get("netto_rating"))
        if gruppe is None:
            zaehlwerk["ohne_gruppe"] += 1
            continue
        zaehlwerk["verwertet"] += 1
        u = ueberrendite(ret, benchmark)
        alle.append(u)
        gruppen[gruppe].append((ret, u))

    logger.info("Netto-Rating: %d Zeilen, %d verwertet.",
                zaehlwerk["zeilen"], zaehlwerk["verwertet"])
    ergebnis = _auswerten(gruppen, alle, horizont, minimum, "gruppe", zaehlwerk)
    ergebnis["teil"] = teil
    ergebnis["spread_pp"] = _spread(ergebnis["gruppen"], "gruppe",
                                    NETTO_GRUPPEN[-1][0], NETTO_GRUPPEN[0][0])
    return ergebnis


def _spread(zeilen: list[dict], schluesselname: str,
            oben, unten) -> Optional[float]:
    """Abstand zwischen oberster und unterster Gruppe, in Prozentpunkten.

    Die eine Zahl, an der ein Querschnittssignal hängt: gekauft würde das obere
    Ende, gemieden das untere. Ist der Abstand null, gibt es nichts zu handeln
    — gleichgültig, wie die einzelnen Gruppen zur Marktquote stehen.
    """
    je_gruppe = {z[schluesselname]: z.get("markt_trefferquote") for z in zeilen}
    o, u = je_gruppe.get(oben), je_gruppe.get(unten)
    if o is None or u is None:
        return None
    return round(o - u, 1)
