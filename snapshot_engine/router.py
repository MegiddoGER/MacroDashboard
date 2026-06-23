"""
snapshot_engine/router.py — FastAPI-Router für die Snapshot Engine.

Prefix /snapshot, Tag "Snapshot Engine".
Bietet Dashboard, Ticker-Verwaltung, manuelle Ausführung und CSV-Export.
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, StreamingResponse

from database import get_session
from snapshot_engine.models import AnalyseSnapshot, SnapshotKonfiguration
from snapshot_engine.auswertung import kennzahlen_berechnen

router = APIRouter(prefix="/snapshot", tags=["Snapshot Engine"])


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _get_header_metrics():
    from main import get_header_metrics
    return get_header_metrics()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def snapshot_dashboard(request: Request, seite: int = Query(1, ge=1)):
    """Rendert das Snapshot-Dashboard mit Kennzahlen und paginierter Snapshot-Liste."""
    templates = request.app.state.templates
    session = get_session()

    try:
        # Kennzahlen berechnen
        kennzahlen = kennzahlen_berechnen(session)

        # Paginierte Snapshot-Liste (50 pro Seite, neueste zuerst)
        pro_seite = 50
        offset = (seite - 1) * pro_seite

        gesamt_anzahl = session.query(AnalyseSnapshot).count()
        snapshots_raw = (
            session.query(AnalyseSnapshot)
            .order_by(AnalyseSnapshot.snapshot_zeitpunkt.desc())
            .offset(offset)
            .limit(pro_seite)
            .all()
        )
        snapshots = [s.to_dict() for s in snapshots_raw]

        gesamt_seiten = max(1, (gesamt_anzahl + pro_seite - 1) // pro_seite)

        # Aktive Ticker laden
        aktive_ticker = (
            session.query(SnapshotKonfiguration)
            .filter(SnapshotKonfiguration.aktiv == True)
            .order_by(SnapshotKonfiguration.ticker)
            .all()
        )
        ticker_liste = [t.to_dict() for t in aktive_ticker]

        ctx = {
            "current_path": "/snapshot/dashboard",
            "header_metrics": _get_header_metrics(),
            "kennzahlen": kennzahlen,
            "snapshots": snapshots,
            "aktuelle_seite": seite,
            "gesamt_seiten": gesamt_seiten,
            "gesamt_anzahl": gesamt_anzahl,
            "ticker_liste": ticker_liste,
        }

        return templates.TemplateResponse(
            request=request,
            name="pages/snapshot_dashboard.html",
            context=ctx,
        )

    except Exception as e:
        print(f"[Snapshot-Router] Dashboard-Fehler: {e}")
        return HTMLResponse(f"<p>Fehler beim Laden des Snapshot-Dashboards: {e}</p>", status_code=500)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Ticker-Verwaltung
# ---------------------------------------------------------------------------

@router.post("/ticker/hinzufuegen", response_class=HTMLResponse)
async def ticker_hinzufuegen(request: Request, ticker: str = Form(...)):
    """Fügt einen Ticker zur Snapshot-Konfiguration hinzu."""
    session = get_session()
    try:
        ticker = ticker.strip().upper()
        if not ticker:
            return HTMLResponse(
                "<script>showToast('Bitte einen Ticker eingeben', 'error');</script>"
            )

        # Prüfe ob bereits vorhanden
        vorhandene = session.query(SnapshotKonfiguration).filter(
            SnapshotKonfiguration.ticker == ticker
        ).first()

        if vorhandene:
            if not vorhandene.aktiv:
                # Reaktivieren
                vorhandene.aktiv = True
                session.commit()
                return HTMLResponse(
                    f"<script>showToast('{ticker} reaktiviert!');setTimeout(()=>location.reload(),500);</script>"
                )
            return HTMLResponse(
                f"<script>showToast('{ticker} ist bereits aktiv', 'error');</script>"
            )

        konfig = SnapshotKonfiguration(
            ticker=ticker,
            aktiv=True,
            zeitfenster_tage=7,
            hinzugefuegt_am=datetime.utcnow(),
        )
        session.add(konfig)
        session.commit()

        return HTMLResponse(
            f"<script>showToast('{ticker} hinzugefügt!');setTimeout(()=>location.reload(),500);</script>"
        )

    except Exception as e:
        session.rollback()
        print(f"[Snapshot-Router] Fehler beim Hinzufügen von {ticker}: {e}")
        return HTMLResponse(
            f"<script>showToast('Fehler: {e}', 'error');</script>"
        )
    finally:
        session.close()


@router.post("/ticker/deaktivieren/{ticker}", response_class=HTMLResponse)
async def ticker_deaktivieren(request: Request, ticker: str):
    """Deaktiviert einen Ticker in der Snapshot-Konfiguration."""
    session = get_session()
    try:
        konfig = session.query(SnapshotKonfiguration).filter(
            SnapshotKonfiguration.ticker == ticker
        ).first()

        if not konfig:
            return HTMLResponse(
                f"<script>showToast('{ticker} nicht gefunden', 'error');</script>"
            )

        konfig.aktiv = False
        session.commit()

        return HTMLResponse(
            f"<script>showToast('{ticker} deaktiviert');setTimeout(()=>location.reload(),500);</script>"
        )

    except Exception as e:
        session.rollback()
        print(f"[Snapshot-Router] Fehler beim Deaktivieren von {ticker}: {e}")
        return HTMLResponse(
            f"<script>showToast('Fehler: {e}', 'error');</script>"
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Manueller Run
# ---------------------------------------------------------------------------

@router.post("/manuell-ausfuehren", response_class=HTMLResponse)
async def manuell_ausfuehren(request: Request):
    """Führt einen vollständigen Snapshot-Run manuell aus (Snapshot + Outcome)."""
    session = get_session()
    try:
        from snapshot_engine.snapshot_service import alle_snapshots_ausfuehren, outcomes_nachtragen

        # Schritt 1: Snapshots
        ergebnis = alle_snapshots_ausfuehren(session)

        # Schritt 2: Outcomes
        nachgetragen = outcomes_nachtragen(session)

        # Ergebnis als HTML-Fragment
        html = f"""
        <div class="alert alert-success" style="margin-top: 12px;">
            <strong>Snapshot-Run abgeschlossen</strong><br>
            ✓ {ergebnis['erfolgreich']} Snapshots erfolgreich erstellt<br>
            {"✗ " + str(ergebnis['fehlgeschlagen']) + " fehlgeschlagen (" + ", ".join(ergebnis['ticker_fehler']) + ")<br>" if ergebnis['fehlgeschlagen'] > 0 else ""}
            ↻ {nachgetragen} Outcomes nachgetragen
        </div>
        """
        return HTMLResponse(html)

    except Exception as e:
        print(f"[Snapshot-Router] Manueller Run fehlgeschlagen: {e}")
        return HTMLResponse(
            f'<div class="alert alert-danger" style="margin-top: 12px;">'
            f'<strong>Fehler:</strong> {e}</div>'
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CSV-Export
# ---------------------------------------------------------------------------

@router.get("/export/csv")
async def export_csv(request: Request):
    """Exportiert alle ausgewerteten Snapshots als CSV-Datei."""
    session = get_session()
    try:
        snapshots = (
            session.query(AnalyseSnapshot)
            .filter(AnalyseSnapshot.ausgewertet == True)
            .order_by(AnalyseSnapshot.snapshot_zeitpunkt.desc())
            .all()
        )

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")

        # Header
        writer.writerow([
            "Ticker", "Snapshot-Zeitpunkt", "Kurs bei Snapshot",
            "Confidence (%)", "Confidence-Label", "Signal",
            "Zeitfenster (Tage)", "Outcome-Kurs", "Outcome-Return (%)",
            "Outcome-Zeitpunkt", "Indikatoren (JSON)",
        ])

        # Daten
        for s in snapshots:
            writer.writerow([
                s.ticker,
                s.snapshot_zeitpunkt.strftime("%Y-%m-%d %H:%M") if s.snapshot_zeitpunkt else "",
                f"{s.kurs_bei_snapshot:.2f}" if s.kurs_bei_snapshot else "",
                f"{s.confidence:.1f}" if s.confidence else "",
                s.confidence_label or "",
                s.richtungssignal or "",
                s.zeitfenster_tage,
                f"{s.outcome_kurs:.2f}" if s.outcome_kurs else "",
                f"{s.outcome_return:.2f}" if s.outcome_return is not None else "",
                s.outcome_zeitpunkt.strftime("%Y-%m-%d %H:%M") if s.outcome_zeitpunkt else "",
                s.indikator_json or "",
            ])

        output.seek(0)
        dateiname = f"snapshots_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={dateiname}"},
        )

    except Exception as e:
        print(f"[Snapshot-Router] CSV-Export fehlgeschlagen: {e}")
        return HTMLResponse(f"Fehler beim Export: {e}", status_code=500)
    finally:
        session.close()
