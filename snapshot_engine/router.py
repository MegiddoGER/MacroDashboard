"""
snapshot_engine/router.py — FastAPI-Router der Signal-Qualitäts-Engine.

Prefix /signals. Liefert die Übersicht, das Indikator-Leaderboard und die
Steuerung des historischen Backfills.
"""

import csv
import io
import logging
from datetime import datetime

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from database import get_session
from snapshot_engine.auswertung import (
    MIN_STICHPROBE, bestand_ermitteln, indikator_leaderboard,
    kalibrierung_berechnen, kalibrierung_bewerten, kategorie_leaderboard,
    kennzahlen_berechnen, vermischung_pruefen,
)
from snapshot_engine.auswertung.gate import gate_wirkung
from snapshot_engine.auswertung.indikator_stats import basisrate
from snapshot_engine.models import (
    HORIZONTE_TAGE, AnalyseSnapshot, AnalyseSnapshotOutcome, BackfillStatus,
    Datenmodus, KonfigModus, SnapshotKonfiguration,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["Signal-Qualität"])


def _basis_kontext(request: Request, pfad: str) -> dict:
    return {
        "current_path": pfad,
        "horizonte": list(HORIZONTE_TAGE),
        "min_stichprobe": MIN_STICHPROBE,
    }


# ---------------------------------------------------------------------------
# Übersicht
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def uebersicht(request: Request,
                     horizont: int = Query(30),
                     # Vorgabe HISTORISCH statt ALLE: LIVE und HISTORISCH haben
                     # deutlich verschiedene Basisraten, und HISTORISCH trägt
                     # praktisch die gesamte statistische Masse. ALLE bleibt
                     # wählbar, wird aber als Vermischung gekennzeichnet.
                     datenmodus: str = Query(Datenmodus.HISTORISCH),
                     seite: int = Query(1, ge=1)):
    """Hauptseite: Kennzahlen, Kalibrierung und jüngste Snapshots."""
    templates = request.app.state.templates
    session = get_session()

    try:
        modus = None if datenmodus == "ALLE" else datenmodus
        if horizont not in HORIZONTE_TAGE:
            horizont = HORIZONTE_TAGE[0]

        kennzahlen = kennzahlen_berechnen(session, datenmodus=modus)
        kalibrierung = kalibrierung_berechnen(session, horizont=horizont, datenmodus=modus)
        fazit = kalibrierung_bewerten(kalibrierung)

        pro_seite = 50
        query = session.query(AnalyseSnapshot)
        if modus:
            query = query.filter(AnalyseSnapshot.datenmodus == modus)
        gesamt = query.count()
        snapshots = (
            query.order_by(AnalyseSnapshot.snapshot_zeitpunkt.desc())
            .offset((seite - 1) * pro_seite).limit(pro_seite).all()
        )

        # Outcomes je Snapshot für die Tabelle vorladen
        snapshot_zeilen = []
        for s in snapshots:
            outcomes = {o.horizont_tage: o for o in (s.outcomes or [])}
            snapshot_zeilen.append({
                "snapshot": s,
                "outcomes": {h: outcomes.get(h) for h in HORIZONTE_TAGE},
            })

        kontext = {
            **_basis_kontext(request, "/signals"),
            "kennzahlen": kennzahlen,
            "kalibrierung": kalibrierung,
            "kalibrierung_fazit": fazit,
            "basis": basisrate(session, horizont, modus),
            "vermischung": vermischung_pruefen(session, modus),
            "gate": gate_wirkung(session, horizont=horizont, datenmodus=modus),
            "snapshot_zeilen": snapshot_zeilen,
            "gesamt_anzahl": gesamt,
            "aktuelle_seite": seite,
            "gesamt_seiten": max(1, (gesamt + pro_seite - 1) // pro_seite),
            "gewaehlter_horizont": horizont,
            "gewaehlter_datenmodus": datenmodus,
            "backfill_job": _aktueller_backfill(session),
        }

        return templates.TemplateResponse(
            request=request, name="pages/signal_quality.html", context=kontext)

    except Exception as e:
        logger.error("Signal-Übersicht fehlgeschlagen: %s", e, exc_info=True)
        return HTMLResponse(f"<p>Fehler beim Laden der Signal-Übersicht: {e}</p>",
                            status_code=500)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Indikator-Leaderboard
# ---------------------------------------------------------------------------

@router.get("/indikatoren", response_class=HTMLResponse)
async def indikatoren(request: Request,
                      horizont: int = Query(30),
                      datenmodus: str = Query(Datenmodus.HISTORISCH)):
    """Bewertung jedes Einzelindikators gegen die unbedingte Basisrate."""
    templates = request.app.state.templates
    session = get_session()

    try:
        modus = None if datenmodus == "ALLE" else datenmodus
        if horizont not in HORIZONTE_TAGE:
            horizont = HORIZONTE_TAGE[0]

        kontext = {
            **_basis_kontext(request, "/signals/indikatoren"),
            "indikatoren": indikator_leaderboard(session, horizont=horizont,
                                                 datenmodus=modus),
            "kategorien": kategorie_leaderboard(session, horizont=horizont,
                                                datenmodus=modus),
            "basis": basisrate(session, horizont, modus),
            "vermischung": vermischung_pruefen(session, modus),
            "gewaehlter_horizont": horizont,
            "gewaehlter_datenmodus": datenmodus,
            "bestand": bestand_ermitteln(session),
        }

        return templates.TemplateResponse(
            request=request, name="pages/signal_indikatoren.html", context=kontext)

    except Exception as e:
        logger.error("Indikator-Seite fehlgeschlagen: %s", e, exc_info=True)
        return HTMLResponse(f"<p>Fehler beim Laden des Leaderboards: {e}</p>",
                            status_code=500)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def _aktueller_backfill(session) -> dict | None:
    from snapshot_engine.models import SignalBackfillJob
    job = (session.query(SignalBackfillJob)
           .order_by(SignalBackfillJob.id.desc()).first())
    return job.to_dict() if job else None


@router.get("/backfill", response_class=HTMLResponse)
async def backfill_seite(request: Request):
    """Steuerung und Fortschritt des historischen Replays."""
    templates = request.app.state.templates
    session = get_session()
    try:
        kontext = {
            **_basis_kontext(request, "/signals/backfill"),
            "job": _aktueller_backfill(session),
            "bestand": bestand_ermitteln(session),
        }
        return templates.TemplateResponse(
            request=request, name="pages/signal_backfill.html", context=kontext)
    except Exception as e:
        logger.error("Backfill-Seite fehlgeschlagen: %s", e, exc_info=True)
        return HTMLResponse(f"<p>Fehler: {e}</p>", status_code=500)
    finally:
        session.close()


@router.post("/backfill/start", response_class=HTMLResponse)
async def backfill_start(request: Request,
                         historie_jahre: int = Form(5),
                         include_smc: str = Form("ja")):
    """Startet einen historischen Backfill (läuft im Hintergrund weiter)."""
    session = get_session()
    try:
        from snapshot_engine.backfill_service import backfill_starten
        job = backfill_starten(session,
                               historie_jahre=max(1, min(historie_jahre, 20)),
                               include_smc=(include_smc == "ja"))
        return HTMLResponse(
            f'<div class="alert alert-success">Backfill #{job.id} gestartet — '
            f'{job.ticker_gesamt} Ticker, {job.historie_jahre} Jahre. '
            f'Der Fortschritt aktualisiert sich automatisch.</div>')
    except Exception as e:
        logger.error("Backfill-Start fehlgeschlagen: %s", e, exc_info=True)
        return HTMLResponse(f'<div class="alert alert-danger">Fehler: {e}</div>')
    finally:
        session.close()


@router.post("/backfill/abbrechen", response_class=HTMLResponse)
async def backfill_abbrechen_route(request: Request):
    """Bricht den laufenden Backfill ab (bereits erzeugte Daten bleiben)."""
    session = get_session()
    try:
        from snapshot_engine.backfill_service import backfill_abbrechen
        erfolg = backfill_abbrechen(session)
        text = ("Backfill abgebrochen." if erfolg else "Kein laufender Backfill.")
        return HTMLResponse(f'<div class="alert">{text}</div>')
    finally:
        session.close()


@router.get("/backfill/status", response_class=HTMLResponse)
async def backfill_status(request: Request):
    """HTMX-Fragment mit dem aktuellen Fortschritt (wird gepollt)."""
    templates = request.app.state.templates
    session = get_session()
    try:
        return templates.TemplateResponse(
            request=request, name="partials/signal_backfill_status.html",
            context={"job": _aktueller_backfill(session)})
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Manueller Lauf
# ---------------------------------------------------------------------------

@router.post("/lauf/manuell", response_class=HTMLResponse)
async def manuell_ausfuehren(request: Request):
    """Führt Gating, einen Teil der Warteschlange und die Outcomes aus."""
    session = get_session()
    try:
        from snapshot_engine.snapshot_service import manueller_lauf
        ergebnis = manueller_lauf(session)
        return HTMLResponse(
            f'<div class="alert alert-success">'
            f'<strong>Lauf abgeschlossen</strong><br>'
            f'{ergebnis["gating"]["eingereiht"]} von {ergebnis["gating"]["geprueft"]} '
            f'Tickern fällig · {ergebnis["queue"]["erfolgreich"]} Snapshots erstellt '
            f'({ergebnis["queue"]["offen"]} noch offen) · '
            f'{ergebnis["outcomes_nachgetragen"]} Outcomes nachgetragen</div>')
    except Exception as e:
        logger.error("Manueller Lauf fehlgeschlagen: %s", e, exc_info=True)
        return HTMLResponse(f'<div class="alert alert-danger">Fehler: {e}</div>')
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Ticker-Overrides
# ---------------------------------------------------------------------------

@router.post("/ticker/hinzufuegen", response_class=HTMLResponse)
async def ticker_hinzufuegen(request: Request, ticker: str = Form(...),
                             modus: str = Form(KonfigModus.EINSCHLIESSEN)):
    """Nimmt einen Ticker zusätzlich auf oder schließt ihn aus."""
    session = get_session()
    try:
        symbol = ticker.strip().upper()
        if not symbol:
            return HTMLResponse(
                "<script>showToast('Bitte einen Ticker eingeben', 'error');</script>")

        vorhanden = session.query(SnapshotKonfiguration).filter(
            SnapshotKonfiguration.ticker == symbol).first()

        if vorhanden:
            vorhanden.aktiv = True
            vorhanden.modus = modus
        else:
            session.add(SnapshotKonfiguration(
                ticker=symbol, aktiv=True, modus=modus,
                hinzugefuegt_am=datetime.utcnow()))
        session.commit()

        return HTMLResponse(
            f"<script>showToast('{symbol} gespeichert');"
            f"setTimeout(()=>location.reload(),500);</script>")

    except Exception as e:
        session.rollback()
        logger.error("Ticker-Override fehlgeschlagen: %s", e, exc_info=True)
        return HTMLResponse(f"<script>showToast('Fehler: {e}', 'error');</script>")
    finally:
        session.close()


@router.post("/ticker/entfernen/{ticker}", response_class=HTMLResponse)
async def ticker_entfernen(request: Request, ticker: str):
    """Entfernt einen manuellen Override."""
    session = get_session()
    try:
        eintrag = session.query(SnapshotKonfiguration).filter(
            SnapshotKonfiguration.ticker == ticker.upper()).first()
        if eintrag:
            eintrag.aktiv = False
            session.commit()
        return HTMLResponse(
            f"<script>showToast('{ticker} entfernt');"
            f"setTimeout(()=>location.reload(),500);</script>")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CSV-Export
# ---------------------------------------------------------------------------

@router.get("/export/csv")
async def export_csv(request: Request):
    """Exportiert alle ausgewerteten Beobachtungen (eine Zeile je Horizont)."""
    session = get_session()
    try:
        zeilen = (
            session.query(AnalyseSnapshot, AnalyseSnapshotOutcome)
            .join(AnalyseSnapshotOutcome,
                  AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
            .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
            .order_by(AnalyseSnapshot.snapshot_zeitpunkt.desc())
            .all()
        )

        puffer = io.StringIO()
        writer = csv.writer(puffer, delimiter=";")
        writer.writerow([
            "Ticker", "Snapshot-Zeitpunkt", "Datenmodus", "Erstellt von",
            "Kurs bei Snapshot", "Confidence", "Signal", "Horizont (Tage)",
            "Outcome-Kurs", "Outcome-Return (%)", "Fällig am",
            "War erfolgreich", "Kategorie-Scores",
        ])

        for s, o in zeilen:
            writer.writerow([
                s.ticker,
                s.snapshot_zeitpunkt.strftime("%Y-%m-%d %H:%M") if s.snapshot_zeitpunkt else "",
                s.datenmodus, s.erstellt_von or "",
                f"{s.kurs_bei_snapshot:.2f}" if s.kurs_bei_snapshot else "",
                f"{s.confidence:.1f}" if s.confidence is not None else "",
                s.richtungssignal, o.horizont_tage,
                f"{o.outcome_kurs:.2f}" if o.outcome_kurs else "",
                f"{o.outcome_return:.2f}" if o.outcome_return is not None else "",
                o.faellig_am.strftime("%Y-%m-%d") if o.faellig_am else "",
                "" if o.war_erfolgreich is None else ("ja" if o.war_erfolgreich else "nein"),
                s.indikator_json or "",
            ])

        puffer.seek(0)
        dateiname = f"signalqualitaet_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        return StreamingResponse(
            iter([puffer.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={dateiname}"})

    except Exception as e:
        logger.error("CSV-Export fehlgeschlagen: %s", e, exc_info=True)
        return HTMLResponse(f"Fehler beim Export: {e}", status_code=500)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Weiterleitung der alten Pfade
# ---------------------------------------------------------------------------

alt_router = APIRouter(prefix="/snapshot", tags=["Signal-Qualität"], include_in_schema=False)


@alt_router.get("/dashboard")
async def alte_dashboard_url():
    """Leitet Lesezeichen der früheren Snapshot-Engine auf /signals um."""
    return RedirectResponse("/signals", status_code=301)
