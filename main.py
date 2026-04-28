"""
main.py — FastAPI Entry Point (ersetzt app.py).

Starte mit:
  py -m uvicorn main:app --reload --port 8501
  oder:
  py launcher.py (natives Fenster)
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from database import init_db


# ---------------------------------------------------------------------------
# App Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: DB initialisieren, Templates konfigurieren."""
    init_db()
    print("[OK] Datenbank initialisiert.")
    yield
    print("[STOP] Server wird beendet.")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Macro Dashboard",
    description="Trading Macro Dashboard -- FastAPI + Jinja2 + HTMX",
    version="2.0.0",
    lifespan=lifespan,
)

# Static files (CSS, JS, Images)
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(_PROJECT_ROOT, "static")), name="static")

# Jinja2 Templates
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "templates"))
app.state.templates = templates


# ---------------------------------------------------------------------------
# Helper: Header-Metriken (fuer Jinja2 globals und API)
# ---------------------------------------------------------------------------

def get_header_metrics() -> list[dict]:
    """Berechnet die Top-3-Header-Metriken (S&P 500 Futures, Gold, DXY)."""
    from services.cache_core import cached_quote
    metrics = []
    for label, ticker in [
        ("S&P 500 Futures", "ES=F"),
        ("Gold", "GC=F"),
        ("US Dollar Index", "DX-Y.NYB"),
    ]:
        try:
            q = cached_quote(ticker)
            if q:
                metrics.append({
                    "label": label,
                    "value": f"{q['price']:,.2f}",
                    "change_pct": q.get("change_pct"),
                })
            else:
                metrics.append({"label": label, "value": "---", "change_pct": None})
        except Exception:
            metrics.append({"label": label, "value": "---", "change_pct": None})
    return metrics


# ---------------------------------------------------------------------------
# Jinja2 Globals — verfuegbar in JEDEM Template automatisch
# ---------------------------------------------------------------------------

templates.env.globals["header_metrics_fn"] = get_header_metrics


# ---------------------------------------------------------------------------
# Middleware: Inject request-spezifischen Context
# ---------------------------------------------------------------------------

@app.middleware("http")
async def inject_common_context(request: Request, call_next):
    """Speichert current_path fuer Sidebar-Highlighting."""
    request.state.current_path = request.url.path
    response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# Router Registration
# ---------------------------------------------------------------------------

from routers.api import router as api_router
from routers.home import router as home_router
from routers.screener import router as screener_router
from routers.analysis import router as analysis_router
from routers.economy import router as economy_router
from routers.directory import router as directory_router
from routers.sectors import router as sectors_router
from routers.lexicon import router as lexicon_router
from routers.watchlist import router as watchlist_router
from routers.journal import router as journal_router
from routers.backtesting import router as backtesting_router

app.include_router(api_router)
app.include_router(home_router)
app.include_router(screener_router)
app.include_router(analysis_router)
app.include_router(economy_router)
app.include_router(directory_router)
app.include_router(sectors_router)
app.include_router(lexicon_router)
app.include_router(watchlist_router)
app.include_router(journal_router)
app.include_router(backtesting_router)
