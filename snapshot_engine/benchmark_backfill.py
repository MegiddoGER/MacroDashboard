"""
snapshot_engine/benchmark_backfill.py — Marktrendite für Bestands-Outcomes (P1-04).

Trägt `benchmark_ticker` und `benchmark_return` für bereits ausgewertete
Outcomes nach. Der laufende Betrieb füllt beide Felder seit P1-04 selbst
(`snapshot_service.outcomes_nachtragen`); dieses Modul holt den Bestand nach.

Das ist billig: gebraucht werden vier Indexreihen, nicht 611 Kursreihen. Sie
werden einmal geladen und danach nur noch im Speicher nachgeschlagen — der
gesamte Nachtrag ist Rechenzeit ohne weitere Netzabrufe.

Aufruf:
    py -c "import snapshot_engine.benchmark_backfill as b; b.cli()"
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from snapshot_engine.benchmark import (
    benchmark_fuer, benchmark_reihen_laden, benoetigte_benchmarks, rendite,
)
from snapshot_engine.models import AnalyseSnapshot, AnalyseSnapshotOutcome

logger = logging.getLogger(__name__)

# Zeilen je Commit. Groß genug, dass die Transaktion nicht dominiert; klein
# genug, dass ein Abbruch nur eine überschaubare Scheibe verwirft.
_BLOCK = 5000


def offene_anzahl(db: Session) -> int:
    """Ausgewertete Outcomes ohne Benchmark-Eintrag."""
    return (
        db.query(func.count(AnalyseSnapshotOutcome.id))
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.benchmark_ticker.is_(None))
        .scalar() or 0
    )


def _zeitfenster(db: Session) -> tuple[Optional[datetime], Optional[datetime]]:
    """Spanne über alle offenen Zeilen — als Aggregat, ohne sie zu laden."""
    zeile = (
        db.query(func.min(AnalyseSnapshot.snapshot_zeitpunkt),
                 func.max(AnalyseSnapshotOutcome.faellig_am))
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.benchmark_ticker.is_(None))
        .one()
    )
    return zeile[0], zeile[1]


def _block_laden(db: Session, groesse: int) -> list:
    """Nächster Block offener Zeilen.

    Die Abfrage filtert auf `benchmark_ticker IS NULL`; jeder bearbeitete
    Block fällt damit aus der nächsten Abfrage heraus, und ein OFFSET ist
    unnötig. Zeilen ohne ermittelbaren Benchmark bleiben allerdings offen und
    kämen sonst endlos wieder — deshalb führt die Schleife in
    `benchmarks_nachtragen` eine Sperrliste bereits gesehener IDs.
    """
    return (
        db.query(AnalyseSnapshotOutcome, AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt)
        .join(AnalyseSnapshot,
              AnalyseSnapshot.id == AnalyseSnapshotOutcome.snapshot_id)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.benchmark_ticker.is_(None))
        .order_by(AnalyseSnapshotOutcome.id)
        .limit(groesse)
        .all()
    )


def benchmarks_nachtragen(db: Session, limit: Optional[int] = None,
                          block: int = _BLOCK) -> dict:
    """Trägt die Marktrendite für ausgewertete Outcomes nach.

    Arbeitet blockweise: bei 256.705 Zeilen würde ein einziges `.all()` ebenso
    viele ORM-Objekte im Speicher halten. Die Indexreihen werden trotzdem nur
    EINMAL geladen und über alle Blöcke hinweg wiederverwendet — der Nachtrag
    kostet damit genau vier Netzabrufe.

    Wiederaufnehmbar: bearbeitet werden nur Zeilen ohne `benchmark_ticker`.
    Ein Abbruch kostet höchstens den laufenden Block.

    Args:
        limit: Höchstzahl bearbeiteter Zeilen (None = alle).
        block: Zeilen je Block und Commit.

    Returns:
        {"geprueft", "gesetzt", "ohne_benchmark", "ohne_kurs"}
    """
    ergebnis = {"geprueft": 0, "gesetzt": 0,
                "ohne_benchmark": 0, "ohne_kurs": 0}

    von, bis = _zeitfenster(db)
    if von is None or bis is None:
        logger.info("Benchmark-Nachtrag: nichts offen.")
        return ergebnis

    # Alle im Bestand vorkommenden Indizes laden, nicht nur die des ersten
    # Blocks — sonst fehlte ab Block zwei die Reihe eines anderen Marktes.
    alle_ticker = [t for (t,) in db.query(AnalyseSnapshot.ticker).distinct()]
    reihen = benchmark_reihen_laden(benoetigte_benchmarks(alle_ticker), von, bis)

    logger.info("Benchmark-Nachtrag: %d Indexreihen geladen (%s bis %s).",
                len(reihen), von.date(), bis.date())

    # Zeilen, für die kein Benchmark ermittelbar war. Ohne diese Sperrliste
    # lieferte die Abfrage sie in jedem Block erneut, und die Schleife käme
    # nie voran.
    uebersprungen: set[int] = set()

    while True:
        rest = None if limit is None else limit - ergebnis["geprueft"]
        if rest is not None and rest <= 0:
            break
        zeilen = [z for z in _block_laden(db, block + len(uebersprungen))
                  if z[0].id not in uebersprungen]
        if not zeilen:
            break
        if rest is not None:
            zeilen = zeilen[:rest]

        for outcome, ticker, snapshot_zeitpunkt in zeilen:
            ergebnis["geprueft"] += 1
            benchmark = benchmark_fuer(ticker)
            if not benchmark:
                # Unbekannter Markt. `benchmark_ticker` bleibt None, damit die
                # Zeile nachgezogen wird, sobald BENCHMARK_JE_SUFFIX den Markt
                # kennt — niemand muss daran denken.
                ergebnis["ohne_benchmark"] += 1
                uebersprungen.add(outcome.id)
                continue

            wert = rendite(reihen.get(benchmark), snapshot_zeitpunkt,
                           outcome.faellig_am)
            if wert is None:
                ergebnis["ohne_kurs"] += 1
                uebersprungen.add(outcome.id)
                continue

            outcome.benchmark_ticker = benchmark
            outcome.benchmark_return = round(wert, 2)
            ergebnis["gesetzt"] += 1

        db.commit()
        db.expunge_all()   # ORM-Identity-Map leeren, sonst wächst sie mit
        logger.info("Benchmark-Nachtrag: %d gesetzt, %d geprüft.",
                    ergebnis["gesetzt"], ergebnis["geprueft"])

    logger.info("Benchmark-Nachtrag fertig: %d gesetzt, %d ohne Benchmark, "
                "%d ohne Indexkurs.", ergebnis["gesetzt"],
                ergebnis["ohne_benchmark"], ergebnis["ohne_kurs"])
    return ergebnis


def cli() -> None:
    """Kommandozeilen-Einstieg mit Protokoll auf der Konsole."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from database import get_session
    db = get_session()
    try:
        offen = offene_anzahl(db)
        print(f"Offen: {offen} Outcomes ohne Benchmark.")
        if not offen:
            return
        ergebnis = benchmarks_nachtragen(db)
        print(f"Gesetzt: {ergebnis['gesetzt']} | "
              f"ohne Benchmark: {ergebnis['ohne_benchmark']} | "
              f"ohne Indexkurs: {ergebnis['ohne_kurs']}")
    finally:
        db.close()
