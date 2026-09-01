"""
snapshot_engine/auswertung/accruals.py — Tragen Periodenabgrenzungen? (P2-06)

Dritter Kandidat aus §5 und der erste, der den Kurs von seiner Konstruktion her
nicht berühren kann: Accruals entstehen aus Jahresabschluss und
Kapitalflussrechnung.

**Das Vorzeichen ist umgekehrt.** Bei PEAD (§2e) und den Analystenrevisionen
(§2f) war oben gut. Hier erwartet die Literatur (Sloan 1996) das Gegenteil:
**hohe Abgrenzungen bedeuten schlechtere Folgerenditen**, weil ein Gewinn, der
nicht als Zahlung ankommt, weniger dauerhaft ist. Trägt das Signal, muss
Quintil 1 (niedrigste Accruals) über und Quintil 5 unter der Marktquote liegen
— und `spread_pp` ist entsprechend als Q1 minus Q5 gerechnet, damit ein
positiver Wert wie bei den anderen Messungen „Hypothese bestätigt" heißt.

**Punkt-in-Zeit ohne pauschalen Aufschlag.** Jede Kennzahl trägt ihr eigenes
`bekannt_ab` — das späteste Einreichungsdatum ihrer drei Bestandteile. Das ist
der Grund, aus dem `services/accruals.py` die teure `companyconcept`-
Schnittstelle nimmt statt der billigen `frames`: Letztere liefert überwiegend
die Vergleichszahl des Folgejahres (gemessen: 84 %), und ein fester Aufschlag
darauf wäre Look-ahead um Monate.

**Der Querschnitt ist US-only.** Accruals gibt es nur für SEC-Filer; von 611
Tickern tragen 502 eine CIK. Wie bei den Analystenrevisionen fällt der
Xetra-Querschnitt damit unter `MIN_QUERSCHNITT` und ganz heraus.

**Kursnähe** wird mitgemessen (`auswertung/kursnaehe`), wie es §2f zur Regel
gemacht hat. Hier ist die Erwartung niedrig — aber genau deshalb ist es die
Gelegenheit, die Prüfung an einem Fall zu eichen, bei dem sie klein ausfallen
sollte.
"""

import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from services.accruals import (
    MAX_ALTER_TAGE, MIN_ABSTAND_TAGE, accruals_je_ticker, letzter_accrual_vor,
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
from snapshot_engine.auswertung.kursnaehe import kursnaehe_pruefen

logger = logging.getLogger(__name__)


QUANTILE = 5
MIN_QUERSCHNITT = 20


def quintil(rang: Optional[float]) -> Optional[int]:
    """Quintil 1–5 zu einem Perzentilrang.

    1 sind die NIEDRIGSTEN Abgrenzungen und damit nach Sloan die besseren
    Titel. Anders als bei den übrigen Messungen ist hier unten gut.
    """
    if rang is None:
        return None
    return min(QUANTILE, int(rang // (100.0 / QUANTILE)) + 1)


# ---------------------------------------------------------------------------
# Zuordnung und Ränge
# ---------------------------------------------------------------------------

def _werte_je_snapshot(db: Session, datenmodus: str
                       ) -> tuple[dict[int, float], dict[int, tuple]]:
    """Je Snapshot der zuletzt öffentlich gewesene Accrual.

    Returns:
        ({snapshot_id: accrual}, {snapshot_id: (ticker, zeitpunkt)})
    """
    reihen = accruals_je_ticker(db)
    logger.info("Accruals: Kennzahlen für %d Ticker geladen.", len(reihen))

    snapshots = (
        db.query(AnalyseSnapshot.id, AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .all()
    )

    werte: dict[int, float] = {}
    zuordnung: dict[int, tuple] = {}
    ohne = 0
    for snapshot_id, ticker, zeitpunkt in snapshots:
        treffer = letzter_accrual_vor(reihen.get(ticker), zeitpunkt)
        if treffer is None:
            ohne += 1
            continue
        werte[snapshot_id] = treffer[1]
        zuordnung[snapshot_id] = (ticker, zeitpunkt)

    logger.info("Accruals: %d Snapshots mit gültiger Kennzahl (max. %d Tage "
                "alt), %d ohne.", len(werte), MAX_ALTER_TAGE, ohne)
    return werte, zuordnung


def accrual_raenge(db: Session, werte: dict[int, float],
                   zuordnung: dict[int, tuple],
                   minimum_querschnitt: int = MIN_QUERSCHNITT
                   ) -> dict[int, float]:
    """Perzentilrang des Accruals je Snapshot, je Kalenderwoche und Platz.

    Die Kalenderwoche ist nötig, weil die Snapshots nicht auf gemeinsamen
    Stichtagen liegen — dieselbe Begründung wie in `momentum.py`. Gegenüber
    einer Kennzahl, die sich nur jährlich ändert, ist eine Woche fein genug.
    """
    eimer: dict[tuple, dict[str, Optional[float]]] = defaultdict(dict)
    verweise: dict[tuple, list[tuple]] = defaultdict(list)

    for snapshot_id, wert in werte.items():
        ticker, zeitpunkt = zuordnung[snapshot_id]
        jahr, woche, _ = zeitpunkt.isocalendar()
        schluessel = (jahr, woche)
        eimer[schluessel][ticker] = wert
        verweise[schluessel].append((snapshot_id, ticker))

    raenge: dict[int, float] = {}
    for schluessel, gruppe in eimer.items():
        gerangt = raenge_je_gruppe(gruppe, benchmark_fuer, minimum_querschnitt)
        for snapshot_id, ticker in verweise[schluessel]:
            if ticker in gerangt:
                raenge[snapshot_id] = gerangt[ticker]

    logger.info("Accruals: %d Snapshots gerangt.", len(raenge))
    return raenge


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

def accruals_auswerten(db: Session, horizont: int = 30,
                       datenmodus: str = "HISTORISCH",
                       teil: Optional[str] = TRAIN,
                       minimum: int = MIN_STICHPROBE,
                       mit_kursnaehe: bool = True) -> dict:
    """Quintile der Periodenabgrenzungen gegen den Markt.

    Returns:
        {"basis_markt", "n_gesamt", "quintile", "spread_pp", "z_korrigiert",
         "kursnaehe", "zaehlwerk", "teil", "horizont_tage"}

    `spread_pp` ist **Q1 minus Q5** — niedrige minus hohe Abgrenzungen. Positiv
    heißt: die Hypothese von Sloan bestätigt sich.
    """
    werte, zuordnung = _werte_je_snapshot(db, datenmodus)
    raenge = accrual_raenge(db, werte, zuordnung)

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

    zaehlwerk = {"zeilen": 0, "ohne_kennzahl": 0, "ohne_rang": 0, "verwertet": 0}
    gruppen: dict[int, list[tuple]] = defaultdict(list)
    alle: list[Optional[float]] = []

    for snapshot_id, ret, benchmark in query.all():
        zaehlwerk["zeilen"] += 1
        if snapshot_id not in werte:
            zaehlwerk["ohne_kennzahl"] += 1
            continue
        q = quintil(raenge.get(snapshot_id))
        if q is None:
            zaehlwerk["ohne_rang"] += 1
            continue
        zaehlwerk["verwertet"] += 1
        u = ueberrendite(ret, benchmark)
        alle.append(u)
        gruppen[q].append((ret, u))

    logger.info("Accruals: %d Zeilen, %d verwertet.",
                zaehlwerk["zeilen"], zaehlwerk["verwertet"])

    ergebnis: dict = {"basis_markt": None, "n_gesamt": 0, "quintile": [],
                      "spread_pp": None, "z_korrigiert": None,
                      "kursnaehe": None, "zaehlwerk": zaehlwerk, "teil": teil,
                      "horizont_tage": horizont}
    if not gruppen:
        return ergebnis

    basis_markt = anteil_schlaegt_markt(alle)
    z = z_korrigiert(len(gruppen))
    zeilen = [
        {"quintil": q, "horizont_tage": horizont, "teil": teil,
         **zelle_gegen_markt([r for r, _ in gruppen[q]],
                             [u for _, u in gruppen[q]],
                             basis_markt, horizont, minimum=minimum, z=z)}
        for q in sorted(gruppen)
    ]

    ergebnis.update({
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "n_gesamt": sum(len(v) for v in gruppen.values()),
        "quintile": zeilen,
        "spread_pp": _spread(zeilen),
        "z_korrigiert": round(z, 2),
    })

    if mit_kursnaehe:
        # Auf den Rängen und nicht auf den Rohwerten, weil auch die Auswertung
        # auf Rängen läuft — gefragt ist die Nähe dessen, was tatsächlich
        # gemessen wurde.
        ergebnis["kursnaehe"] = kursnaehe_pruefen(
            db, raenge, zuordnung, datenmodus=datenmodus)

    return ergebnis


def _spread(zeilen: list[dict]) -> Optional[float]:
    """Q1 minus Q5 — niedrige minus hohe Abgrenzungen, in Prozentpunkten.

    **Umgekehrt zu den übrigen Messungen**, und zwar absichtlich: so bedeutet
    ein positiver Wert auch hier „die Hypothese bestätigt sich". Die
    Alternative wäre ein Spread, dessen Vorzeichen je Modul etwas anderes
    heißt — genau die Sorte Fußangel, die einen Befund später falsch
    zitiert werden lässt.
    """
    je_quintil = {z["quintil"]: z.get("markt_trefferquote") for z in zeilen}
    niedrig, hoch = je_quintil.get(1), je_quintil.get(QUANTILE)
    if niedrig is None or hoch is None:
        return None
    return round(niedrig - hoch, 1)
