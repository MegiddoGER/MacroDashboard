"""
snapshot_engine/auswertung/regime.py — Gilt ein Signal nur unter Bedingungen? (P2-03)

Die Frage, auf die §2h zeigt. Dort trug die stetige Fassung von Trend und
SMA-Cross auf sieben Tagen einen monotonen Vorsprung von 2,0 bzw. 2,9 pp — und
fiel trotzdem durch die Regime-Prüfung (5 bzw. 6 von 8 Jahren). Entscheidend war
**wie**: drei unabhängig konstruierte Signale zeigen dasselbe Jahresmuster.
Nicht ein viertes Signal fehlt, sondern die Bedingung.

Dieses Modul misst dieselben Größen wie `auswertung/kodierung`, aber getrennt
nach Marktregime. Die Ränge werden dabei **global** gebildet, nicht je Regime:
ein Rang ist ein Eingang, die Bedingung wird danach angelegt. Innerhalb des
Regimes zu rangen würde die Frage verändern — dann hieße sie „welche Titel sind
in ruhigen Phasen die stärksten", statt „gilt dieselbe Rangliste in ruhigen
Phasen anders".

**Was ein Fund wäre und was nicht.** Ein Vorsprung, der in einem Regime steht
und im anderen fehlt, ist ein Gate. Ein Vorsprung, der in beiden Regimen
gleich groß ist, ist keiner — dann wäre das Regime nur eine Aufteilung der
Stichprobe. Und ein Vorsprung, der in **einer** von zehn Zellen auftaucht,
ohne dass die vier Nachbarquintile mitziehen, ist Mehrfachtest. Deshalb wird
über alle ausgewiesenen Zellen korrigiert und der Verlauf mit ausgegeben.

**Die Schwelle ist nicht gesucht, sondern gesetzt** (siehe
`services/marktregime`): das Regime folgt aus dem nachlaufenden Median der
Größe selbst. Es gibt keinen Kandidatensatz wie in `schwellensuche.py` und
damit auch keine Suche, die zu korrigieren wäre.
"""

import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from services.marktregime import regime_am, regime_reihen_laden
from snapshot_engine.benchmark import benchmark_fuer, ueberrendite
from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, zelle_gegen_markt, z_korrigiert,
)
from snapshot_engine.auswertung.holdout import TRAIN, grenze_lesen, split_filter
from snapshot_engine.auswertung.kodierung import GROESSEN, _raenge, _werte, quintil

logger = logging.getLogger(__name__)


# Welche Regimegröße geprüft wird. Beide stammen aus derselben Indexreihe.
REGIME_ARTEN = ("vola_regime", "richtungs_regime")


def regime_je_snapshot(db: Session, zuordnung: dict[int, tuple],
                       datenmodus: str = "HISTORISCH") -> dict[int, dict]:
    """Marktregime zum Zeitpunkt jedes Snapshots, je Handelsplatz.

    Das Regime richtet sich nach dem Index des Handelsplatzes, nicht nach einem
    Weltmarkt: ein Xetra-Titel steht in der Volatilität des DAX, nicht des
    S&P 500. Dieselbe Entscheidung wie bei `benchmark.benchmark_fuer`.
    """
    if not zuordnung:
        return {}

    zeitpunkte = [z for _, z in zuordnung.values()]
    benchmarks = sorted({b for b in (benchmark_fuer(t) for t, _ in zuordnung.values())
                         if b})
    reihen = regime_reihen_laden(benchmarks, min(zeitpunkte), max(zeitpunkte))

    ergebnis: dict[int, dict] = {}
    ohne = 0
    for snapshot_id, (ticker, zeitpunkt) in zuordnung.items():
        reihe = reihen.get(benchmark_fuer(ticker) or "")
        zustand = regime_am(reihe, zeitpunkt)
        if zustand is None:
            ohne += 1
            continue
        ergebnis[snapshot_id] = zustand

    logger.info("Regime: %d Snapshots zugeordnet, %d ohne (Index fehlt oder "
                "Fenster unvollständig).", len(ergebnis), ohne)
    return ergebnis


def signal_nach_regime(db: Session, groesse: str = "SMA-Cross (20/50)",
                       horizont: int = 7,
                       regime_art: str = "vola_regime",
                       datenmodus: str = "HISTORISCH",
                       teil: Optional[str] = TRAIN,
                       minimum: int = MIN_STICHPROBE) -> dict:
    """Quintile der stetigen Größe, getrennt nach Marktregime.

    Returns:
        {"groesse", "regime_art", "regime": {zustand: {...}}, "zaehlwerk", ...}

    Je Regimezustand steht dort dieselbe Struktur wie in
    `kodierung.kodierung_vergleichen`: Quintilzeilen und ein Spread Q5 − Q1.
    Die Marktbasis wird **je Regime** neu gerechnet — in einer
    Hochvolatilitätsphase schlagen andere Anteile der Titel ihren Index als in
    einer ruhigen, und gegen eine gemeinsame Basis gerechnet bekäme das eine
    Regime einen Vorsprung geschenkt, an dem kein Signal beteiligt ist. Das ist
    dieselbe Falle wie bei den Sektor-Basisquoten in §2d.
    """
    if regime_art not in REGIME_ARTEN:
        raise ValueError(f"Unbekannte Regimegröße {regime_art!r} — erlaubt: "
                         f"{REGIME_ARTEN}")
    if groesse not in GROESSEN:
        raise ValueError(f"Unbekannte Größe {groesse!r} — erlaubt: "
                         f"{sorted(GROESSEN)}")

    werte, zuordnung = _werte(db, groesse, datenmodus)
    raenge = _raenge(werte, zuordnung)
    regime = regime_je_snapshot(db, zuordnung, datenmodus)

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

    zaehlwerk = {"zeilen": 0, "ohne_rang": 0, "ohne_regime": 0, "verwertet": 0}
    # {regimezustand: {quintil: [(rendite, überrendite)]}}
    gruppen: dict[str, dict[int, list[tuple]]] = defaultdict(lambda: defaultdict(list))
    alle: dict[str, list[Optional[float]]] = defaultdict(list)

    for snapshot_id, ret, benchmark in query.all():
        zaehlwerk["zeilen"] += 1
        q = quintil(raenge.get(snapshot_id))
        if q is None:
            zaehlwerk["ohne_rang"] += 1
            continue
        zustand = regime.get(snapshot_id, {}).get(regime_art)
        if zustand is None:
            zaehlwerk["ohne_regime"] += 1
            continue
        zaehlwerk["verwertet"] += 1
        u = ueberrendite(ret, benchmark)
        alle[zustand].append(u)
        gruppen[zustand][q].append((ret, u))

    logger.info("Regime/%s/%s: %d Zeilen, %d verwertet.",
                groesse, regime_art, zaehlwerk["zeilen"], zaehlwerk["verwertet"])

    # Korrigiert wird über ALLE Zellen beider Regime zusammen: sie stammen aus
    # einem Lauf und einer Grundgesamtheit. Je Regime getrennt zu korrigieren
    # hieße, zweimal zum halben Preis zu testen.
    zellen = sum(len(q) for q in gruppen.values())
    z = z_korrigiert(zellen) if zellen else None

    ergebnis: dict = {"groesse": groesse, "regime_art": regime_art,
                      "horizont_tage": horizont, "teil": teil,
                      "z_korrigiert": None if z is None else round(z, 2),
                      "zaehlwerk": zaehlwerk, "regime": {}}

    for zustand in sorted(gruppen):
        basis = anteil_schlaegt_markt(alle[zustand])
        zeilen = [
            {"quintil": q,
             **zelle_gegen_markt([r for r, _ in gruppen[zustand][q]],
                                 [u for _, u in gruppen[zustand][q]],
                                 basis, horizont, minimum=minimum, z=z)}
            for q in sorted(gruppen[zustand])
        ]
        je_quintil = {x["quintil"]: x.get("markt_trefferquote") for x in zeilen}
        oben, unten = je_quintil.get(5), je_quintil.get(1)
        ergebnis["regime"][zustand] = {
            "basis_markt": round(basis, 1) if basis is not None else None,
            "n": sum(len(v) for v in gruppen[zustand].values()),
            "quintile": zeilen,
            "spread_pp": (None if oben is None or unten is None
                          else round(oben - unten, 1)),
        }

    return ergebnis
