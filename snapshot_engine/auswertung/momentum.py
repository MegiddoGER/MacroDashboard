"""
snapshot_engine/auswertung/momentum.py — Trägt Querschnitts-Momentum? (P2-02)

Misst den Kandidaten aus §5, bevor er den Score anfassen darf: rangt alle Titel
eines Handelsplatzes wöchentlich nach ihrer 12-1-Monats-Rendite und fragt, ob
die oberen Ränge ihren Index häufiger schlagen als die unteren.

**Warum das aus den Snapshot-Kursen gerechnet wird und nicht aus neuen Downloads.**
Der Backfill hat je Ticker EINE Kursreihe abgespielt; alle HISTORISCH-Snapshots
eines Tickers stammen damit aus derselben Anpassungsbasis, und ein Verhältnis
zwischen zwei von ihnen ist split-sicher. Nachgeprüft: von 86.333 aufeinander
folgenden Kurspaaren liegen 16 außerhalb von [0,6 · 1,6], und die sind
sämtlich echte Ereignisse (CVNA 2022/23, SMCI nach dem Prüfer-Rücktritt,
HelloFresh, Fiserv) — keine Split-Brüche. 593 Reihen neu zu laden hätte nichts
verbessert und Stunden gekostet.

**Look-ahead:** das Rückschaufenster endet `SKIP_TAGE` VOR dem Snapshot. Es
geht ausschließlich Kursinformation ein, die zum Snapshot-Zeitpunkt vorlag.

**Ränge werden immer über das ganze Universum gebildet**, auch wenn nur der
Trainingsteil ausgewertet wird. Ein Rang ist ein Eingang, kein Label — ihn auf
den Trainingsteil zu beschränken würde den Querschnitt verstümmeln, ohne
irgendetwas vor Overfitting zu schützen.
"""

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from services.cross_sectional_momentum import (
    LOOKBACK_TAGE, MIN_QUERSCHNITT, SKIP_TAGE, dezil, momentum_roh,
    naechster_kurs, raenge_je_gruppe,
)
from snapshot_engine.benchmark import benchmark_fuer, ueberrendite
from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, kennzahlen_aus_returns,
    mit_ueberrendite,
)
from services.index_membership import war_mitglied
from snapshot_engine.auswertung.holdout import grenze_lesen, split_filter

logger = logging.getLogger(__name__)


def _kursreihen(db: Session, datenmodus: str) -> dict[str, list[tuple]]:
    """Je Ticker eine nach Datum sortierte Reihe (Zeitpunkt, Kurs)."""
    reihen: dict[str, list[tuple]] = defaultdict(list)
    zeilen = (
        db.query(AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt,
                 AnalyseSnapshot.kurs_bei_snapshot)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .order_by(AnalyseSnapshot.ticker, AnalyseSnapshot.snapshot_zeitpunkt)
        .all()
    )
    for ticker, zeitpunkt, kurs in zeilen:
        if kurs and kurs > 0:
            reihen[ticker].append((zeitpunkt, kurs))
    return reihen


def raenge_berechnen(db: Session, datenmodus: str = "HISTORISCH",
                     minimum_querschnitt: int = MIN_QUERSCHNITT) -> dict[int, float]:
    """Perzentilrang je Snapshot, gerangt je Handelsplatz und Kalenderwoche.

    Die Woche ist nötig, weil die Snapshots nicht auf gemeinsamen Stichtagen
    liegen: der Backfill ist je Ticker über dessen eigene Bars gelaufen. Eine
    Woche ist gegenüber einem Rückschaufenster von zwölf Monaten unscharf
    genug, um zu bündeln, und scharf genug, um nichts zu vermischen.

    Returns:
        {snapshot_id: Perzentilrang 0–100}
    """
    reihen = _kursreihen(db, datenmodus)
    logger.info("Momentum: %d Kursreihen geladen.", len(reihen))

    snapshots = (
        db.query(AnalyseSnapshot.id, AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .all()
    )

    # Rohes Momentum je Snapshot, gebündelt nach Kalenderwoche. Die Trennung
    # nach Handelsplatz übernimmt `raenge_je_gruppe` — Titel ohne bekannten
    # Platz fallen dort heraus.
    eimer: dict[tuple, dict[str, Optional[float]]] = defaultdict(dict)
    zuordnung: dict[tuple, list[tuple]] = defaultdict(list)
    ohne_fenster = 0

    for snapshot_id, ticker, zeitpunkt in snapshots:
        reihe = reihen.get(ticker)
        beginn = naechster_kurs(reihe, zeitpunkt - timedelta(days=LOOKBACK_TAGE))
        ende = naechster_kurs(reihe, zeitpunkt - timedelta(days=SKIP_TAGE))
        wert = momentum_roh(beginn, ende)
        if wert is None:
            ohne_fenster += 1
            continue

        jahr, woche, _ = zeitpunkt.isocalendar()
        schluessel = (jahr, woche)
        eimer[schluessel][ticker] = wert
        zuordnung[schluessel].append((snapshot_id, ticker))

    raenge: dict[int, float] = {}
    for schluessel, werte in eimer.items():
        gerangt = raenge_je_gruppe(werte, benchmark_fuer, minimum_querschnitt)
        for snapshot_id, ticker in zuordnung[schluessel]:
            if ticker in gerangt:
                raenge[snapshot_id] = gerangt[ticker]

    logger.info("Momentum: %d Snapshots gerangt, %d ohne vollständiges "
                "Rückschaufenster.", len(raenge), ohne_fenster)
    return raenge


def momentum_auswerten(db: Session, horizont: int = 30,
                       datenmodus: str = "HISTORISCH",
                       teil: Optional[str] = None,
                       minimum: int = MIN_STICHPROBE,
                       nur_mitglieder: bool = False) -> dict:
    """Wertet die Ränge je Dezil gegen den Markt aus.

    Args:
        nur_mitglieder: Survivorship-Prüfung (P4-07). Zählt nur Beobachtungen,
            bei denen der Titel zum Snapshot-Zeitpunkt bereits im Index war.
            Titel, für die sich das nicht entscheiden lässt — jeder
            Xetra-Wert, und jedes frühere Mitglied — fallen dabei heraus; die
            Stichprobe schrumpft also aus zwei verschiedenen Gründen. Das
            Ergebnis trägt `mitglieder_geprueft`, damit die beiden Läufe
            nicht verwechselt werden.

    Jedes Dezil wird als LONG bewertet: gefragt ist, wie oft ein Titel dieses
    Rangs seinen Index schlägt. Trägt Momentum, muss Dezil 10 über und Dezil 1
    unter der unbedingten Marktquote liegen — und der Verlauf dazwischen
    einigermaßen monoton sein. Eine einzelne herausragende Zelle ohne Verlauf
    wäre Mehrfachtest, kein Signal.

    Returns:
        {"basis_markt", "n_gesamt", "dezile": [...], "spread_pp"}
    """
    raenge = raenge_berechnen(db, datenmodus)
    if not raenge:
        return {"basis_markt": None, "n_gesamt": 0, "dezile": [], "spread_pp": None}

    query = (
        db.query(AnalyseSnapshot.id,
                 AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt,
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

    # Aufnahmedaten nur laden, wenn sie gebraucht werden — der Abruf geht
    # ins Netz, und der Normalfall dieser Auswertung braucht ihn nicht.
    aufnahmedaten = None
    if nur_mitglieder:
        from services.cache_core import cached_sp500_aufnahmedaten
        aufnahmedaten = cached_sp500_aufnahmedaten()
        if not aufnahmedaten:
            logger.warning("Survivorship-Prüfung angefordert, aber keine "
                           "Aufnahmedaten verfügbar — Lauf wird abgebrochen.")
            return {"basis_markt": None, "n_gesamt": 0, "dezile": [],
                    "spread_pp": None, "mitglieder_geprueft": False,
                    "verworfen_unbekannt": 0, "verworfen_kein_mitglied": 0}

    gruppen: dict[int, list[tuple]] = defaultdict(list)
    alle_ueberrenditen: list[Optional[float]] = []
    verworfen_unbekannt = 0
    verworfen_kein_mitglied = 0

    for snapshot_id, ticker, zeitpunkt, ret, benchmark in query.all():
        if nur_mitglieder:
            mitglied = war_mitglied(ticker, zeitpunkt, aufnahmedaten)
            if mitglied is None:
                verworfen_unbekannt += 1
                continue
            if not mitglied:
                verworfen_kein_mitglied += 1
                continue

        d = dezil(raenge.get(snapshot_id))
        if d is None:
            continue
        u = ueberrendite(ret, benchmark)
        alle_ueberrenditen.append(u)
        gruppen[d].append((ret, u))

    # Unbedingte Marktquote über GENAU die Zeilen, die auch in die Dezile
    # eingehen — nicht über den Gesamtbestand. Sonst verglichen sich Dezile
    # gegen eine Grundgesamtheit, der sie gar nicht angehören.
    basis_markt = anteil_schlaegt_markt(alle_ueberrenditen)

    zeilen = []
    for d in sorted(gruppen):
        paare = gruppen[d]
        returns = [r for r, _ in paare]
        kennzahlen = mit_ueberrendite(
            kennzahlen_aus_returns(returns, horizont_tage=horizont,
                                   minimum=minimum, richtungen=[1] * len(returns)),
            [u for _, u in paare], [1] * len(paare), basis_markt,
            horizont_tage=horizont, minimum=minimum)
        zeilen.append({"dezil": d, "horizont_tage": horizont,
                       "teil": teil, **kennzahlen})

    return {
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "n_gesamt": sum(len(v) for v in gruppen.values()),
        "dezile": zeilen,
        "spread_pp": _spread(zeilen),
        "mitglieder_geprueft": nur_mitglieder,
        "verworfen_unbekannt": verworfen_unbekannt,
        "verworfen_kein_mitglied": verworfen_kein_mitglied,
    }


def _spread(zeilen: list[dict]) -> Optional[float]:
    """Abstand zwischen oberstem und unterstem Dezil, in Prozentpunkten.

    Die eine Zahl, an der Momentum hängt: ein Long-Short-Portfolio kauft das
    oberste und verkauft das unterste Dezil. Ist der Abstand null, gibt es
    nichts zu handeln — gleichgültig, wie die einzelnen Dezile zur Marktquote
    stehen.
    """
    je_dezil = {z["dezil"]: z.get("markt_trefferquote") for z in zeilen}
    oben, unten = je_dezil.get(10), je_dezil.get(1)
    if oben is None or unten is None:
        return None
    return round(oben - unten, 1)
