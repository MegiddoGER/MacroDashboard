"""
snapshot_engine/scheduler.py — Hintergrund-Jobs der Signal-Qualitäts-Engine.

Drei Jobs auf einem gemeinsamen AsyncIOScheduler:

  1. Gating (Cron, täglich nach Börsenschluss)
     Ein günstiger Batch-Lauf über das gesamte Universum, der die fälligen
     Ticker in die Warteschlange stellt.

  2. Drain (Intervall)
     Arbeitet die Live-Warteschlange in kleinen Häppchen ab, trägt fällige
     Outcomes nach und schiebt laufende Backfill-Jobs weiter. Bewusst
     intervallgesteuert statt als ein langer Lauf: so bleibt der Fortschritt
     in der DB und übersteht einen Neustart der App.

Alle Zeiten in Europe/Berlin.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import SNAPSHOT_RUN_TIME
from database import get_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

TAEGLICHER_LAUF_UHRZEIT = SNAPSHOT_RUN_TIME   # CET, nach Xetra-Schluss (.env: SNAPSHOT_RUN_TIME)
DRAIN_INTERVALL_MINUTEN = 3         # Takt der Warteschlangen-Abarbeitung
DRAIN_QUEUE_LIMIT = 8               # Ticker je Drain-Tick (Rate-Limit-Schonung)
DRAIN_OUTCOME_LIMIT = 300           # Outcomes je Drain-Tick

_scheduler: AsyncIOScheduler | None = None


# ---------------------------------------------------------------------------
# Job 1 — tägliches Gating
# ---------------------------------------------------------------------------

def _gating_job():
    """Ermittelt einmal täglich, welche Ticker neu bewertet werden müssen."""
    logger.info("═══ Gating-Lauf gestartet ═══")
    session = get_session()
    try:
        from snapshot_engine.snapshot_service import gating_lauf
        ergebnis = gating_lauf(session)
        logger.info("Gating-Lauf beendet: %d von %d Tickern eingereiht.",
                    ergebnis["eingereiht"], ergebnis["geprueft"])
    except Exception as e:
        logger.error("Gating-Lauf fehlgeschlagen: %s", e, exc_info=True)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Job 2 — Drain (Warteschlange, Outcomes, Backfill)
# ---------------------------------------------------------------------------

def _drain_job():
    """Arbeitet offene Arbeit in begrenzten Häppchen ab.

    Reihenfolge ist bewusst gewählt: erst neue Snapshots erzeugen, dann
    Outcomes nachtragen (Outcomes setzen existierende Snapshots voraus),
    zuletzt der historische Backfill als niedrigste Priorität.
    """
    session = get_session()
    try:
        from snapshot_engine.snapshot_service import (
            outcomes_nachtragen, queue_abarbeiten,
        )

        queue = queue_abarbeiten(session, limit=DRAIN_QUEUE_LIMIT)
        if queue["verarbeitet"]:
            logger.info("Drain: %d Ticker verarbeitet (%d ok, %d Fehler, %d offen).",
                        queue["verarbeitet"], queue["erfolgreich"],
                        queue["fehlgeschlagen"], queue["offen"])

        nachgetragen = outcomes_nachtragen(session, limit=DRAIN_OUTCOME_LIMIT)
        if nachgetragen:
            logger.info("Drain: %d Outcomes nachgetragen.", nachgetragen)

    except Exception as e:
        logger.error("Drain-Job fehlgeschlagen: %s", e, exc_info=True)
    finally:
        session.close()

    # Backfill separat, damit ein Fehler dort die Live-Verarbeitung nicht stoppt
    session = get_session()
    try:
        from snapshot_engine.backfill_service import backfill_schritt
        backfill_schritt(session)
    except Exception as e:
        logger.error("Backfill-Schritt fehlgeschlagen: %s", e, exc_info=True)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

def scheduler_starten():
    """Startet alle Hintergrund-Jobs. Wird vom lifespan-Handler aufgerufen."""
    global _scheduler

    if _scheduler is not None:
        logger.info("Scheduler bereits gestartet — übersprungen.")
        return

    _scheduler = AsyncIOScheduler()

    stunde, minute = TAEGLICHER_LAUF_UHRZEIT.split(":")
    _scheduler.add_job(
        _gating_job,
        trigger=CronTrigger(hour=int(stunde), minute=int(minute),
                            timezone="Europe/Berlin"),
        id="signal_gating",
        name="Tägliches Signal-Gating",
        replace_existing=True,
    )

    _scheduler.add_job(
        _drain_job,
        trigger=IntervalTrigger(minutes=DRAIN_INTERVALL_MINUTEN),
        id="signal_drain",
        name="Warteschlange & Outcomes abarbeiten",
        replace_existing=True,
        max_instances=1,          # Überlappende Läufe verhindern
        coalesce=True,            # Verpasste Läufe zusammenfassen, nicht nachholen
    )

    _scheduler.start()
    logger.info("Scheduler gestartet — Gating täglich %s CET, Drain alle %d Minuten.",
                TAEGLICHER_LAUF_UHRZEIT, DRAIN_INTERVALL_MINUTEN)


def scheduler_stoppen():
    """Stoppt den Scheduler sauber."""
    global _scheduler

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler gestoppt.")
