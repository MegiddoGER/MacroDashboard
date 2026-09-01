"""
snapshot_engine/auswertung/kodierung.py — Liegt es am Konzept oder an der Kodierung?

Die Frage, die in §2b nie gestellt wurde. Dort blieben sechzehn
Indikatorrichtungen ohne Vorsprung — gemessen wurde aber jedes Mal ein Flag mit
**zwei** möglichen Werten. „Trend (SMA 200)" trägt über 274.839 Zeilen bei
62 Prozent +1 und bei 38 Prozent −1; ein Kurs ein halbes Prozent über der Linie
und einer fünfundvierzig Prozent darüber sind derselbe Eingang.

Ein Flag, das bei 62 Prozent aller Beobachtungen gesetzt ist, ist kein Flag.
Die Nullbefunde belegen deshalb, dass **diese Kodierung** nichts trägt — nicht,
dass das Konzept nichts trägt. Dieses Modul trennt das.

**Der Kontrollversuch ist der ganze Punkt.** Gemessen werden beide Fassungen
auf **exakt denselben Zeilen**: die stetige Größe in Quintilen, und ihr eigenes
Vorzeichen als zwei Gruppen. Gleicher Zeitraum, gleiche Titel, gleiche
Grundgesamtheit, gleiche Marktbasis. Der einzige Unterschied ist die
weggeworfene Stärke. Ohne diese Kopplung wäre jeder Unterschied womöglich nur
eine andere Stichprobe — genau der Fehler, der aus §2b eine Aussage über
Indikatoren statt über ihre Darstellung gemacht hat.

**Zwei Lesarten des Ergebnisses:**

- Trägt die stetige Fassung dort, wo die binäre nichts zeigt, ist die Diagnose
  gestellt: die Engine wirft Information weg, und der Umbau des Composites
  (§4B, bisher ausgesetzt) wäre begründet statt spekulativ.
- Trägt auch die stetige Fassung nichts, ist die Kodierung als Erklärung
  ausgeschieden und der Nullbefund von §2b wird stärker, nicht schwächer.

**Grenze der Aussage.** Die gleitenden Mittel stammen aus Snapshot-Kursen mit
acht Tagen Kadenz, das lange Fenster hat rund 35 statt 200 Stützstellen (siehe
`services/stetige_indikatoren`). Ein positiver Befund rechtfertigt eine exakte
Nachrechnung; ein negativer ist entsprechend schwächer als einer auf exakten
Reihen und sollte nicht als endgültig zitiert werden.
"""

import logging
from collections import defaultdict
from typing import Callable, Optional

from sqlalchemy.orm import Session

from services.cross_sectional_momentum import raenge_je_gruppe
from services.stetige_indikatoren import ma_spreizung, sma_abstand, vorzeichen
from snapshot_engine.benchmark import benchmark_fuer, ueberrendite
from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, zelle_gegen_markt, z_korrigiert,
)
from snapshot_engine.auswertung.holdout import TRAIN, grenze_lesen, split_filter
from snapshot_engine.auswertung.kursnaehe import kursnaehe_pruefen, kursreihen

logger = logging.getLogger(__name__)


QUANTILE = 5
MIN_QUERSCHNITT = 20

# Die geprüften Größen. Der Name ist der des Engine-Indikators, dessen stetige
# Fassung hier steht — damit ein Befund ohne Umweg auf `services/scoring.py`
# zeigt.
GROESSEN: dict[str, Callable] = {
    "Trend (SMA 200)": sma_abstand,
    "SMA-Cross (20/50)": ma_spreizung,
}


def quintil(rang: Optional[float]) -> Optional[int]:
    if rang is None:
        return None
    return min(QUANTILE, int(rang // (100.0 / QUANTILE)) + 1)


# ---------------------------------------------------------------------------
# Werte je Snapshot
# ---------------------------------------------------------------------------

def _werte(db: Session, groesse: str, datenmodus: str
           ) -> tuple[dict[int, float], dict[int, tuple]]:
    """Stetiger Wert je Snapshot, plus (ticker, zeitpunkt) zur Zuordnung."""
    if groesse not in GROESSEN:
        raise ValueError(f"Unbekannte Größe {groesse!r} — erlaubt: "
                         f"{sorted(GROESSEN)}")
    rechnen = GROESSEN[groesse]
    reihen = kursreihen(db, datenmodus)

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
        wert = rechnen(reihen.get(ticker), zeitpunkt)
        if wert is None:
            ohne += 1
            continue
        werte[snapshot_id] = wert
        zuordnung[snapshot_id] = (ticker, zeitpunkt)

    logger.info("Kodierung/%s: %d Snapshots mit Wert, %d ohne (Fenster zu dünn).",
                groesse, len(werte), ohne)
    return werte, zuordnung


def _raenge(werte: dict[int, float], zuordnung: dict[int, tuple],
            minimum_querschnitt: int = MIN_QUERSCHNITT) -> dict[int, float]:
    """Perzentilrang je Snapshot, je Kalenderwoche und Handelsplatz."""
    eimer: dict[tuple, dict[str, Optional[float]]] = defaultdict(dict)
    verweise: dict[tuple, list[tuple]] = defaultdict(list)

    for snapshot_id, wert in werte.items():
        ticker, zeitpunkt = zuordnung[snapshot_id]
        jahr, woche, _ = zeitpunkt.isocalendar()
        eimer[(jahr, woche)][ticker] = wert
        verweise[(jahr, woche)].append((snapshot_id, ticker))

    raenge: dict[int, float] = {}
    for schluessel, gruppe in eimer.items():
        gerangt = raenge_je_gruppe(gruppe, benchmark_fuer, minimum_querschnitt)
        for snapshot_id, ticker in verweise[schluessel]:
            if ticker in gerangt:
                raenge[snapshot_id] = gerangt[ticker]
    return raenge


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

def kodierung_vergleichen(db: Session, groesse: str = "Trend (SMA 200)",
                          horizont: int = 30,
                          datenmodus: str = "HISTORISCH",
                          teil: Optional[str] = TRAIN,
                          minimum: int = MIN_STICHPROBE,
                          mit_kursnaehe: bool = True) -> dict:
    """Stetige Quintile gegen binäres Vorzeichen, auf identischen Zeilen.

    Returns:
        {"groesse", "basis_markt", "n_gesamt", "stetig", "binaer",
         "spread_stetig_pp", "spread_binaer_pp", "z_korrigiert", "kursnaehe",
         "zaehlwerk", "teil", "horizont_tage"}

    `spread_stetig_pp` ist Q5 minus Q1, `spread_binaer_pp` ist die
    Plus-Gruppe minus die Minus-Gruppe — beide also „oben minus unten", damit
    sie unmittelbar vergleichbar sind.
    """
    werte, zuordnung = _werte(db, groesse, datenmodus)
    raenge = _raenge(werte, zuordnung)

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

    zaehlwerk = {"zeilen": 0, "ohne_wert": 0, "ohne_rang": 0, "verwertet": 0}
    stetig: dict[int, list[tuple]] = defaultdict(list)
    binaer: dict[int, list[tuple]] = defaultdict(list)
    alle: list[Optional[float]] = []

    for snapshot_id, ret, benchmark in query.all():
        zaehlwerk["zeilen"] += 1
        wert = werte.get(snapshot_id)
        if wert is None:
            zaehlwerk["ohne_wert"] += 1
            continue
        q = quintil(raenge.get(snapshot_id))
        vz = vorzeichen(wert)
        if q is None or vz is None:
            # Ohne Rang fällt die Zeile aus BEIDEN Fassungen, damit die
            # Grundgesamtheiten identisch bleiben. Das ist der Kern des
            # Kontrollversuchs und keine Nachlässigkeit — deshalb steht die
            # Prüfung beider Fassungen auch in einer einzigen Bedingung.
            zaehlwerk["ohne_rang"] += 1
            continue

        zaehlwerk["verwertet"] += 1
        u = ueberrendite(ret, benchmark)
        alle.append(u)
        stetig[q].append((ret, u))
        binaer[vz].append((ret, u))

    ergebnis: dict = {"groesse": groesse, "basis_markt": None, "n_gesamt": 0,
                      "stetig": [], "binaer": [], "spread_stetig_pp": None,
                      "spread_binaer_pp": None, "z_korrigiert": None,
                      "kursnaehe": None, "zaehlwerk": zaehlwerk, "teil": teil,
                      "horizont_tage": horizont}
    if not stetig:
        return ergebnis

    basis_markt = anteil_schlaegt_markt(alle)
    # Korrigiert wird über ALLE ausgewiesenen Zellen beider Fassungen: sie
    # stammen aus demselben Lauf und derselben Grundgesamtheit, und wer nur
    # innerhalb einer Fassung korrigiert, testet zweimal zum halben Preis.
    z = z_korrigiert(len(stetig) + len(binaer))

    def _zeilen(gruppen: dict, schluessel: str) -> list[dict]:
        return [
            {schluessel: k, "horizont_tage": horizont, "teil": teil,
             **zelle_gegen_markt([r for r, _ in gruppen[k]],
                                 [u for _, u in gruppen[k]],
                                 basis_markt, horizont, minimum=minimum, z=z)}
            for k in sorted(gruppen)
        ]

    zeilen_stetig = _zeilen(stetig, "quintil")
    zeilen_binaer = _zeilen(binaer, "vorzeichen")

    ergebnis.update({
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "n_gesamt": sum(len(v) for v in stetig.values()),
        "stetig": zeilen_stetig,
        "binaer": zeilen_binaer,
        "spread_stetig_pp": _spread(zeilen_stetig, "quintil", QUANTILE, 1),
        "spread_binaer_pp": _spread(zeilen_binaer, "vorzeichen", 1, -1),
        "z_korrigiert": round(z, 2),
    })

    if mit_kursnaehe:
        ergebnis["kursnaehe"] = kursnaehe_pruefen(
            db, raenge, zuordnung, datenmodus=datenmodus)

    return ergebnis


def _spread(zeilen: list[dict], schluessel: str, oben, unten) -> Optional[float]:
    """Oben minus unten, in Prozentpunkten — für beide Fassungen gleich gebaut."""
    je_gruppe = {z[schluessel]: z.get("markt_trefferquote") for z in zeilen}
    o, u = je_gruppe.get(oben), je_gruppe.get(unten)
    if o is None or u is None:
        return None
    return round(o - u, 1)
