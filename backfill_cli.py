"""
backfill_cli.py — Historischen Backfill der Signal-Qualitäts-Engine ausführen.

Eigenständiges Skript für den mehrstündigen Lauf über das gesamte Universum.
Gegenüber dem Weg über die Weboberfläche:

  * läuft mit voller Geschwindigkeit statt in 45-Sekunden-Scheiben alle drei
    Minuten (der Scheduler-Takt kommt auf rund 25 % Auslastung — aus 2 Stunden
    Rechenzeit werden dort knapp 9 Stunden),
  * braucht den laufenden Webserver nicht,
  * zeigt Fortschritt und Restzeit direkt in der Konsole.

Der Fortschritt liegt in der Datenbank: Abbrechen mit Strg-C und späteres
erneutes Starten setzt den Lauf fort, statt von vorn zu beginnen.

WICHTIG: Das Dashboard sollte währenddessen NICHT laufen. SQLite erlaubt im
WAL-Modus nur einen Schreiber; der Drain-Job des Schedulers würde sonst um
Schreibsperren konkurrieren.

Beispiele:
    py backfill_cli.py                          # 5 Jahre, mit SMC (Standard)
    py backfill_cli.py --jahre 3 --ohne-smc     # schneller, ohne SMC
    py backfill_cli.py --ticker AAPL MSFT SAP.DE   # nur einzelne Titel (Test)
    py backfill_cli.py --status                 # nur Fortschritt anzeigen
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta

# Blockgröße je Iteration. Deutlich großzügiger als im Scheduler-Betrieb —
# hier gibt es keinen Webserver, dessen Reaktionszeit geschont werden müsste.
SCHRITT_SEKUNDEN = 600
SCHRITT_TICKER = 20


def _logging_einrichten(ausfuehrlich: bool):
    logging.basicConfig(
        level=logging.DEBUG if ausfuehrlich else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # yfinance/urllib3 sind im Normalbetrieb zu gesprächig
    for name in ("yfinance", "urllib3", "peewee"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _dauer(sekunden: float) -> str:
    """Formatiert eine Zeitspanne kompakt (z.B. '2h 14m')."""
    if sekunden < 60:
        return f"{sekunden:.0f}s"
    if sekunden < 3600:
        return f"{sekunden / 60:.0f}m"
    return f"{sekunden // 3600:.0f}h {(sekunden % 3600) / 60:.0f}m"


def _fortschritt_zeigen(job) -> None:
    daten = job.to_dict()
    print(
        f"  Lauf #{daten['id']}: {daten['fortschritt_pct']:5.1f}%  |  "
        f"{daten['ticker_fertig']}/{daten['ticker_gesamt']} Ticker  |  "
        f"{daten['snapshots_erstellt']:,} Snapshots  |  "
        f"{daten['ticker_fehler']} Fehler"
    )


def _offene_ticker(db) -> int:
    """Zählt noch nicht abgearbeitete Ticker eines aktiven Laufs."""
    from snapshot_engine.backfill_service import aktiver_job
    from snapshot_engine.models import BackfillStatus, SignalBackfillTickerStatus

    job = aktiver_job(db)
    if job is None:
        return 0
    return (
        db.query(SignalBackfillTickerStatus)
        .filter(SignalBackfillTickerStatus.job_id == job.id)
        .filter(SignalBackfillTickerStatus.status == BackfillStatus.AUSSTEHEND)
        .count()
    )


def status_anzeigen(db) -> int:
    from snapshot_engine.auswertung import bestand_ermitteln
    from snapshot_engine.models import SignalBackfillJob

    job = db.query(SignalBackfillJob).order_by(SignalBackfillJob.id.desc()).first()
    if job is None:
        print("Noch kein Backfill-Lauf vorhanden.")
    else:
        print(f"Letzter Lauf: #{job.id} — Status {job.status}")
        _fortschritt_zeigen(job)

    bestand = bestand_ermitteln(db)
    print()
    print("Datenbestand:")
    for schluessel, wert in bestand.items():
        print(f"  {schluessel:24s} {wert:,}")
    return 0


def backfill_ausfuehren(db, jahre: int, mit_smc: bool,
                        ticker: list[str] | None) -> int:
    from snapshot_engine.backfill_service import backfill_schritt, backfill_starten

    # backfill_starten entscheidet selbst, ob ein bestehender Lauf fortgesetzt
    # wird (noch offene Ticker) oder ein neuer beginnt — ein bereits vollständig
    # abgearbeiteter Lauf wird dabei abgeschlossen statt zurückgegeben.
    vorher_offen = _offene_ticker(db)
    job = backfill_starten(db, historie_jahre=jahre,
                           include_smc=mit_smc, tickers=ticker)

    if vorher_offen and (job.ticker_fertig or 0) + (job.ticker_fehler or 0) > 0:
        print(f"Setze Backfill #{job.id} fort "
              f"({job.ticker_gesamt} Ticker, {job.historie_jahre} Jahre, "
              f"SMC={'ja' if job.include_smc else 'nein'}).")
    else:
        print(f"Backfill #{job.id} gestartet: {job.ticker_gesamt} Ticker, "
              f"{job.historie_jahre} Jahre, "
              f"SMC={'ja' if job.include_smc else 'nein'}.")

    gesamt = job.ticker_gesamt or 0
    if not gesamt:
        print("Kein Ticker im Universum — Abbruch. Besteht eine Internetverbindung?")
        return 1

    print(f"Blockgröße: bis zu {SCHRITT_TICKER} Ticker bzw. "
          f"{SCHRITT_SEKUNDEN}s je Durchgang. Abbruch jederzeit mit Strg-C.")
    print()

    beginn = time.perf_counter()
    startwert = (job.ticker_fertig or 0) + (job.ticker_fehler or 0)

    try:
        while True:
            ergebnis = backfill_schritt(db, max_sekunden=SCHRITT_SEKUNDEN,
                                        max_ticker=SCHRITT_TICKER)
            if not ergebnis:
                print("Kein aktiver Lauf mehr — beendet.")
                break

            job = db.get(type(job), ergebnis["job_id"])
            db.refresh(job)
            _fortschritt_zeigen(job)

            # BC-04: die Rohreihen laufen im selben Durchgang mit. Sichtbar,
            # damit ein Lauf, der Snapshots erzeugt aber keine Kurszeilen,
            # sofort auffällt statt erst bei der Auswertung.
            if ergebnis.get("kurszeilen"):
                print(f"    {ergebnis['kurszeilen']:,} Kurszeilen geschrieben")

            if ergebnis.get("fertig"):
                break

            # Restzeit aus dem bisherigen Durchsatz schätzen
            erledigt = (job.ticker_fertig or 0) + (job.ticker_fehler or 0) - startwert
            verstrichen = time.perf_counter() - beginn
            if erledigt > 0:
                je_ticker = verstrichen / erledigt
                verbleibend = gesamt - startwert - erledigt
                if verbleibend > 0:
                    fertig_um = datetime.now() + timedelta(seconds=je_ticker * verbleibend)
                    print(f"    {je_ticker:.1f}s je Ticker  |  noch ~"
                          f"{_dauer(je_ticker * verbleibend)}  |  "
                          f"fertig gegen {fertig_um.strftime('%H:%M')} Uhr")

            if ergebnis["verarbeitet"] == 0:
                print("Keine Fortschritte in diesem Durchgang — Abbruch, "
                      "um eine Endlosschleife zu vermeiden.")
                break

    except KeyboardInterrupt:
        print()
        print("Abgebrochen. Der Fortschritt ist gespeichert — ein erneuter Start "
              "setzt an derselben Stelle fort.")
        return 130

    print()
    print(f"Fertig in {_dauer(time.perf_counter() - beginn)}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Historischen Backfill der Signal-Qualitäts-Engine ausführen.")
    parser.add_argument("--jahre", type=int, default=5,
                        help="Jahre Kurshistorie (Standard: 5)")
    parser.add_argument("--ohne-smc", action="store_true",
                        help="SMC-Analyse überspringen — rund zehnmal schneller, "
                             "aber FVG/EQH/EQL werden historisch nicht bewertet")
    parser.add_argument("--ticker", nargs="+", metavar="SYMBOL",
                        help="Nur diese Ticker verarbeiten (für Tests)")
    parser.add_argument("--status", action="store_true",
                        help="Nur Fortschritt und Datenbestand anzeigen")
    parser.add_argument("--ausfuehrlich", action="store_true",
                        help="Debug-Ausgaben aktivieren")
    argumente = parser.parse_args()

    _logging_einrichten(argumente.ausfuehrlich)

    from database import get_session, init_db
    from snapshot_engine.models import init_snapshot_db

    init_db()
    init_snapshot_db()

    db = get_session()
    try:
        if argumente.status:
            return status_anzeigen(db)
        return backfill_ausfuehren(
            db,
            jahre=max(1, min(argumente.jahre, 20)),
            mit_smc=not argumente.ohne_smc,
            ticker=argumente.ticker,
        )
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
