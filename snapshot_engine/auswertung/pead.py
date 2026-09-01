"""
snapshot_engine/auswertung/pead.py — Trägt der Post-Earnings-Drift? (P2-06)

Misst den ersten Kandidaten aus §5, der **nicht** aus Kursen stammt. Alles
bisher Geprüfte war kursbasiert und hat gegen den Markt nichts getragen:
sechzehn Indikator-Richtungen, fünf Kategorien, das Oszillator-Gate in beiden
Zweigen, Querschnitts-Momentum, die Sektortrennung. Die Ergebnisüberraschung
ist die erste Größe in dieser Reihe, die eine andere Quelle hat.

Die Hypothese: nach einer positiven Überraschung läuft der Kurs noch Wochen
weiter, weil die Nachricht nicht sofort vollständig eingepreist wird. Trägt
sie, muss das oberste Überraschungsquintil seinen Index häufiger schlagen als
das unterste — und der Abstand muss mit wachsendem Abstand zur
Veröffentlichung abklingen. **Beides zusammen**, denn der Verlauf ist es, der
einen Effekt von einer Zufallszelle unterscheidet.

Vier Vorkehrungen, jede gegen einen Fehler, der in diesem Projekt schon
einmal aufgetreten ist:

**1. Rang statt Rohwert.** Eine Abweichung von +50 % auf eine Schätzung von
0,02 ist keine größere Überraschung als +2 % auf 3,00 — sie ist ein kleinerer
Nenner. Gerangt wird deshalb im Querschnitt, und zwar je Meldequartal und je
Handelsplatz: die Schätzkonventionen unterscheiden sich zwischen Xetra und
den USA, und sie haben sich über zehn Jahre verschoben. Dieselbe Bauweise wie
bei `momentum.raenge_berechnen`, dort je Kalenderwoche.

**2. Ränge über das ganze Universum, ausgewertet nur der Trainingsteil.**
Ein Rang ist ein Eingang, kein Label. Ihn auf den Trainingsteil zu beschränken
verstümmelte den Querschnitt, ohne vor Überanpassung zu schützen.

**3. Look-ahead an der empfindlichsten Stelle.** Yahoo sagt nicht, ob vor
Handelsbeginn oder nach Handelsschluss berichtet wurde. Ein Snapshot desselben
Tages könnte die Zahl also noch nicht gekannt haben — und genau dort, in der
ersten Reaktion, sitzt der größte Teil der Bewegung. `pead.MIN_ABSTAND_TAGE`
hält Abstand, statt der Uhrzeit zu vertrauen.

**4. Korrektur für Mehrfachtests.** Quintile mal Altersbänder ergeben zwanzig
Zellen; unkorrigiert wäre etwa eine davon zufällig „signifikant". Šidák wie
in `schwellensuche.py`, gerechnet über die Zahl der tatsächlich ausgewiesenen
Zellen.

**Der Holdout wird hier nicht angefasst.** `teil` ist mit TRAIN vorbelegt, und
eine Bestätigung auf dem Holdout ist erst fällig, wenn auf dem Trainingsteil
etwas steht, das bestätigt werden könnte.
"""

import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from database import EarningsEvent
from services.cross_sectional_momentum import raenge_je_gruppe
from services.pead import (
    MAX_ALTER_TAGE, MIN_ABSTAND_TAGE, ereignisse_je_ticker, letztes_ereignis_vor,
)
from snapshot_engine.benchmark import benchmark_fuer, ueberrendite
from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, fehlerspanne_korrigiert,
    kennzahlen_aus_returns, mit_ueberrendite, z_korrigiert,
)
from snapshot_engine.auswertung.holdout import TRAIN, grenze_lesen, split_filter

logger = logging.getLogger(__name__)


# Fünf statt zehn Gruppen wie beim Momentum: die Zahl der Ereignisse je
# Meldequartal ist kleiner als die Zahl der Titel je Kalenderwoche, und
# Dezile wären hier dünner besetzt, ohne feiner aufzulösen.
QUANTILE = 5

# Mindestbesetzung eines Querschnitts, damit überhaupt gerangt wird. Unter 20
# Ereignissen bildet ein Quintil vier Titel ab — das ist kein Querschnitt,
# sondern eine Auswahl.
MIN_QUERSCHNITT = 20

# Abstand zur Veröffentlichung, in Kalendertagen. Die Literatur verortet den
# Drift bei rund 60 Handelstagen; die Bänder sind so geschnitten, dass ein
# Abklingen sichtbar würde, statt in einem einzigen Mittelwert zu verschwinden.
ALTERSBAENDER: tuple[tuple[int, int], ...] = (
    (MIN_ABSTAND_TAGE, 5),
    (6, 20),
    (21, 60),
    (61, MAX_ALTER_TAGE),
)


def _bandname(von: int, bis: int) -> str:
    return f"{von}-{bis} Tage"


def _band_fuer(alter_tage: int) -> Optional[str]:
    for von, bis in ALTERSBAENDER:
        if von <= alter_tage <= bis:
            return _bandname(von, bis)
    return None


def quintil(rang: Optional[float]) -> Optional[int]:
    """Quintil 1–5 zu einem Perzentilrang; 5 ist die größte Überraschung."""
    if rang is None:
        return None
    return min(QUANTILE, int(rang // (100.0 / QUANTILE)) + 1)


# ---------------------------------------------------------------------------
# Ränge der Ereignisse
# ---------------------------------------------------------------------------

def ereignis_raenge(db: Session,
                    minimum_querschnitt: int = MIN_QUERSCHNITT
                    ) -> dict[tuple[str, object], float]:
    """Perzentilrang je Ereignis, gerangt je Meldequartal und Handelsplatz.

    Returns:
        {(ticker, datum): Perzentilrang 0–100}

    Das Quartal ist die Bündelung, weil Quartalszahlen in Wellen kommen
    (Januar, April, Juli, Oktober). Innerhalb einer Welle sind die
    Überraschungen vergleichbar; über Jahre hinweg sind sie es nicht, weil
    sich die Schätzkonventionen verschoben haben — der Anteil der Titel, die
    ihre Schätzung übertreffen, ist über den Messzeitraum nicht konstant.
    """
    zeilen = (
        db.query(EarningsEvent.ticker, EarningsEvent.datum,
                 EarningsEvent.surprise_pct)
        .filter(EarningsEvent.surprise_pct.isnot(None))
        .all()
    )

    # Werttyp bewusst Optional: `raenge_je_gruppe` nimmt fehlende Werte
    # entgegen, und dict ist im Werttyp invariant.
    eimer: dict[tuple[int, int], dict[str, Optional[float]]] = defaultdict(dict)
    zuordnung: dict[tuple[int, int], dict[str, object]] = defaultdict(dict)

    for ticker, datum, surprise in zeilen:
        if datum is None or surprise is None:
            continue
        schluessel = (datum.year, (datum.month - 1) // 3)
        # Meldet ein Titel zweimal im selben Quartal (Nachmeldung, Korrektur),
        # zählt die spätere Zahl. Zwei Ränge für denselben Titel im selben
        # Querschnitt wären eine Doppelgewichtung.
        eimer[schluessel][ticker] = float(surprise)
        zuordnung[schluessel][ticker] = datum

    raenge: dict[tuple[str, object], float] = {}
    zu_duenn = 0
    for schluessel, werte in eimer.items():
        gerangt = raenge_je_gruppe(werte, benchmark_fuer, minimum_querschnitt)
        if not gerangt:
            zu_duenn += 1
            continue
        for ticker, rang in gerangt.items():
            raenge[(ticker, zuordnung[schluessel][ticker])] = rang

    logger.info("PEAD: %d Ereignisse gerangt, %d Quartalsquerschnitte zu dünn.",
                len(raenge), zu_duenn)
    return raenge


# ---------------------------------------------------------------------------
# Beobachtungen
# ---------------------------------------------------------------------------

def _beobachtungen(db: Session, horizont: int, datenmodus: str,
                   teil: Optional[str]) -> tuple[list[dict], dict]:
    """Je auswertbarer Snapshot-Zeile Quintil, Alter, Rendite und Überrendite.

    Returns:
        (Beobachtungen, Zählwerk). Das Zählwerk hält fest, warum Zeilen
        herausgefallen sind — ohne diese Zahlen ließe sich später nicht
        unterscheiden, ob ein leeres Ergebnis an fehlenden Earnings-Daten
        oder an fehlenden Outcomes liegt.
    """
    raenge = ereignis_raenge(db)
    reihen = ereignisse_je_ticker(db)

    query = (
        db.query(AnalyseSnapshot.ticker,
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

    zaehlwerk = {"zeilen": 0, "ohne_ereignis": 0, "ohne_rang": 0,
                 "ohne_band": 0, "verwertet": 0}
    beobachtungen: list[dict] = []

    for ticker, zeitpunkt, ret, benchmark in query.all():
        zaehlwerk["zeilen"] += 1

        treffer = letztes_ereignis_vor(reihen.get(ticker), zeitpunkt)
        if treffer is None:
            zaehlwerk["ohne_ereignis"] += 1
            continue
        datum, _surprise, alter = treffer

        rang = raenge.get((ticker, datum))
        if rang is None:
            zaehlwerk["ohne_rang"] += 1
            continue

        band = _band_fuer(alter)
        if band is None:
            zaehlwerk["ohne_band"] += 1
            continue

        zaehlwerk["verwertet"] += 1
        beobachtungen.append({
            "quintil": quintil(rang),
            "alter_tage": alter,
            "band": band,
            "outcome_return": ret,
            "ueberrendite": ueberrendite(ret, benchmark),
        })

    logger.info("PEAD: %d Zeilen, %d verwertet (%d ohne Ereignis im Fenster, "
                "%d ohne Rang, %d außerhalb der Bänder).",
                zaehlwerk["zeilen"], zaehlwerk["verwertet"],
                zaehlwerk["ohne_ereignis"], zaehlwerk["ohne_rang"],
                zaehlwerk["ohne_band"])
    return beobachtungen, zaehlwerk


def _zelle(gruppe: list[dict], basis_markt: Optional[float], horizont: int,
           minimum: int, z: float) -> dict:
    """Kennzahlen einer Gruppe, bewertet als LONG gegen den Markt.

    Jede Gruppe wird als LONG gerechnet — gefragt ist, wie oft ein Titel mit
    dieser Überraschung seinen Index schlägt. Eine Short-Lesart wäre eine
    zweite Hypothese und damit ein weiterer Test.
    """
    returns = [b["outcome_return"] for b in gruppe]
    ueberrenditen = [b["ueberrendite"] for b in gruppe]
    richtungen = [1] * len(gruppe)

    kennzahlen = mit_ueberrendite(
        kennzahlen_aus_returns(returns, horizont_tage=horizont,
                               minimum=minimum, richtungen=richtungen),
        ueberrenditen, richtungen, basis_markt,
        horizont_tage=horizont, minimum=minimum)

    # Die korrigierte Fehlerspanne tritt NEBEN die unkorrigierte aus
    # `mit_ueberrendite`, sie ersetzt sie nicht: die unkorrigierte bleibt mit
    # allen bisher belegten Zahlen vergleichbar, die korrigierte ist die,
    # gegen die ein Fund bestehen muss.
    spanne = fehlerspanne_korrigiert(
        kennzahlen.get("markt_trefferquote"), kennzahlen.get("n_effektiv"), z)
    vorsprung = kennzahlen.get("markt_vorsprung_pp")
    kennzahlen["fehlerspanne_korrigiert_pp"] = spanne
    kennzahlen["signifikant_korrigiert"] = (
        None if (spanne is None or vorsprung is None)
        else abs(vorsprung) > spanne)
    return kennzahlen


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

def pead_auswerten(db: Session, horizont: int = 30,
                   datenmodus: str = "HISTORISCH",
                   teil: Optional[str] = TRAIN,
                   minimum: int = MIN_STICHPROBE) -> dict:
    """Quintile der Ergebnisüberraschung gegen den Markt.

    Trägt PEAD, muss Quintil 5 über und Quintil 1 unter der unbedingten
    Marktquote liegen, mit einigermaßen monotonem Verlauf dazwischen. Eine
    einzelne herausragende Zelle ohne Verlauf wäre Mehrfachtest, kein Signal —
    dieselbe Lesart wie bei den Momentum-Dezilen.

    Returns:
        {"basis_markt", "n_gesamt", "quintile", "spread_pp", "z_korrigiert",
         "zaehlwerk", "teil", "horizont_tage"}
    """
    beobachtungen, zaehlwerk = _beobachtungen(db, horizont, datenmodus, teil)
    leer: dict = {"basis_markt": None, "n_gesamt": 0, "quintile": [],
            "spread_pp": None, "z_korrigiert": None, "zaehlwerk": zaehlwerk,
            "teil": teil, "horizont_tage": horizont}
    if not beobachtungen:
        return leer

    gruppen: dict[int, list[dict]] = defaultdict(list)
    for b in beobachtungen:
        if b["quintil"] is not None:
            gruppen[b["quintil"]].append(b)
    if not gruppen:
        return leer

    # Unbedingte Marktquote über GENAU die Zeilen, die auch in die Quintile
    # eingehen. Gegen den Gesamtbestand gerechnet vergliche sich hier eine
    # Teilmenge mit Earnings-Abdeckung gegen eine Grundgesamtheit ohne — und
    # der Unterschied wäre Abdeckung, nicht Signal.
    basis_markt = anteil_schlaegt_markt([b["ueberrendite"] for b in beobachtungen])

    z = z_korrigiert(len(gruppen))
    zeilen = [
        {"quintil": q, "horizont_tage": horizont, "teil": teil,
         **_zelle(gruppen[q], basis_markt, horizont, minimum, z)}
        for q in sorted(gruppen)
    ]

    return {
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "n_gesamt": sum(len(v) for v in gruppen.values()),
        "quintile": zeilen,
        "spread_pp": _spread(zeilen),
        "z_korrigiert": round(z, 2),
        "zaehlwerk": zaehlwerk,
        "teil": teil,
        "horizont_tage": horizont,
    }


def drift_verlauf(db: Session, horizont: int = 30,
                  datenmodus: str = "HISTORISCH",
                  teil: Optional[str] = TRAIN,
                  minimum: int = MIN_STICHPROBE) -> dict:
    """Quintil × Abstand zur Veröffentlichung — klingt der Drift ab?

    Das ist die eigentliche PEAD-Aussage und nicht nur eine Verfeinerung. Ein
    Vorsprung des obersten Quintils, der über alle Altersbänder gleich groß
    ist, wäre kein Drift, sondern eine dauerhafte Eigenschaft der Titel mit
    hohen Überraschungen — also näher an Qualität oder Momentum als an einer
    verzögerten Einpreisung.
    """
    beobachtungen, zaehlwerk = _beobachtungen(db, horizont, datenmodus, teil)
    if not beobachtungen:
        return {"basis_markt": None, "n_gesamt": 0, "zellen": [],
                "z_korrigiert": None, "zaehlwerk": zaehlwerk, "teil": teil,
                "horizont_tage": horizont}

    basis_markt = anteil_schlaegt_markt([b["ueberrendite"] for b in beobachtungen])

    gruppen: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for b in beobachtungen:
        if b["quintil"] is not None:
            gruppen[(b["quintil"], b["band"])].append(b)

    z = z_korrigiert(len(gruppen))
    zellen = [
        {"quintil": q, "band": band, "horizont_tage": horizont, "teil": teil,
         **_zelle(gruppen[(q, band)], basis_markt, horizont, minimum, z)}
        for q, band in sorted(gruppen, key=lambda k: (k[0], k[1]))
    ]

    return {
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "n_gesamt": len(beobachtungen),
        "zellen": zellen,
        "z_korrigiert": round(z, 2),
        "zaehlwerk": zaehlwerk,
        "teil": teil,
        "horizont_tage": horizont,
    }


def _spread(zeilen: list[dict]) -> Optional[float]:
    """Abstand zwischen oberstem und unterstem Quintil, in Prozentpunkten.

    Die eine Zahl, an der PEAD hängt: gekauft würde das oberste Quintil,
    gemieden das unterste. Ist der Abstand null, gibt es nichts zu handeln —
    gleichgültig, wie die einzelnen Quintile zur Marktquote stehen.
    """
    je_quintil = {z["quintil"]: z.get("markt_trefferquote") for z in zeilen}
    oben, unten = je_quintil.get(QUANTILE), je_quintil.get(1)
    if oben is None or unten is None:
        return None
    return round(oben - unten, 1)
