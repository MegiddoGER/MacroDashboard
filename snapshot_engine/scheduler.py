"""
snapshot_engine/scheduler.py — Täglicher Scheduler für Snapshot-Erstellung & Outcome-Nachtragung.

Nutzt APScheduler (AsyncIOScheduler) mit einem täglichen CronJob.
Die Uhrzeit ist leicht anpassbar über TAEGLICHER_LAUF_UHRZEIT.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import get_session


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

TAEGLICHER_LAUF_UHRZEIT = "18:30"  # CET, nach Börsenschluss — leicht anpassbar

# Scheduler-Instanz (Modul-Singleton)
_scheduler: AsyncIOScheduler | None = None


# ---------------------------------------------------------------------------
# Job-Funktion
# ---------------------------------------------------------------------------

def _taeglicher_snapshot_job():
    """Führt sequentiell aus: 1) alle Snapshots erstellen, 2) Outcomes nachtragen.

    Die Reihenfolge ist invariant: Erst Snapshot, dann Outcome.
    Wird synchron in einem Thread ausgeführt (APScheduler default).
    """
    print("[Scheduler] ═══ Täglicher Snapshot-Job gestartet ═══")

    session = get_session()
    try:
        # Schritt 1: Snapshots erstellen
        from snapshot_engine.snapshot_service import alle_snapshots_ausfuehren
        ergebnis = alle_snapshots_ausfuehren(session)
        print(f"[Scheduler] Snapshots: {ergebnis['erfolgreich']} OK, "
              f"{ergebnis['fehlgeschlagen']} Fehler")

        # Schritt 2: Outcomes nachtragen (nach vollständigem Abschluss von Schritt 1)
        from snapshot_engine.snapshot_service import outcomes_nachtragen
        nachgetragen = outcomes_nachtragen(session)
        print(f"[Scheduler] Outcomes nachgetragen: {nachgetragen}")

    except Exception as e:
        print(f"[Scheduler] Fehler im täglichen Job: {e}")
    finally:
        session.close()

    print("[Scheduler] ═══ Täglicher Snapshot-Job beendet ═══")


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

def scheduler_starten():
    """Startet den AsyncIO-Scheduler mit dem täglichen Snapshot-Job.

    Wird vom lifespan-Handler in main.py aufgerufen.
    """
    global _scheduler

    if _scheduler is not None:
        print("[Scheduler] Bereits gestartet — überspringe.")
        return

    _scheduler = AsyncIOScheduler()

    # Uhrzeit parsen
    stunde, minute = TAEGLICHER_LAUF_UHRZEIT.split(":")
    trigger = CronTrigger(
        hour=int(stunde),
        minute=int(minute),
        timezone="Europe/Berlin",  # CET/CEST
    )

    _scheduler.add_job(
        _taeglicher_snapshot_job,
        trigger=trigger,
        id="taeglicher_snapshot",
        name="Täglicher Snapshot-Run",
        replace_existing=True,
    )

    _scheduler.start()
    print(f"[Scheduler] Gestartet — täglicher Snapshot-Run um {TAEGLICHER_LAUF_UHRZEIT} CET.")


def scheduler_stoppen():
    """Stoppt den Scheduler sauber.

    Wird vom lifespan-Handler in main.py aufgerufen.
    """
    global _scheduler

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        print("[Scheduler] Gestoppt.")
