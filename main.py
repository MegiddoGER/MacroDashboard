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
    description="Trading Macro Dashboard — FastAPI + Jinja2 + HTMX",
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
# Middleware: Inject common template context
# ---------------------------------------------------------------------------

@app.middleware("http")
async def inject_common_context(request: Request, call_next):
    """Injects header_metrics and current_path into every template render."""
    # Store current path for sidebar highlighting
    request.state.current_path = request.url.path
    response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# Template Context Processor
# ---------------------------------------------------------------------------

def _get_header_metrics() -> list[dict]:
    """Berechnet die Top-3-Header-Metriken."""
    from services.cache_core import cached_quote
    metrics = []
    for label, ticker in [
        ("S&P 500 Futures", "ES=F"),
        ("Gold", "GC=F"),
        ("US Dollar Index", "DX-Y.NYB"),
    ]:
        q = cached_quote(ticker)
        if q:
            metrics.append({
                "label": label,
                "value": f"{q['price']:,.2f} €",
                "change_pct": q.get("change_pct"),
            })
        else:
            metrics.append({"label": label, "value": "—", "change_pct": None})
    return metrics


# No monkeypatching needed — header_metrics are fetched explicitly
# in each route via the _get_header_metrics() function, or passed
# directly in the template context.


# ---------------------------------------------------------------------------
# Router Registration
# ---------------------------------------------------------------------------

from routers.api import router as api_router
from routers.home import router as home_router

app.include_router(api_router)
app.include_router(home_router)


# ---------------------------------------------------------------------------
# Placeholder routes for pages not yet migrated
# ---------------------------------------------------------------------------

_PLACEHOLDER_PAGES = {
    "/economy": "Gesamtwirtschaft",
    "/analysis": "Analyse",
    "/screener": "Screener",
    "/backtesting": "Backtesting",
    "/watchlist": "Watchlist",
    "/journal": "Trade-Journal",
    "/sectors": "Sektoren",
    "/lexicon": "Analyse-Lexikon",
    "/directory": "Aktien-Verzeichnis",
}

for path, title in _PLACEHOLDER_PAGES.items():
    def _make_handler(page_title, page_path):
        async def handler(request: Request):
            return templates.TemplateResponse("pages/placeholder.html", {
                "request": request,
                "current_path": page_path,
                "page_title": page_title,
            })
        handler.__name__ = f"placeholder_{page_title.replace('-', '_').lower()}"
        return handler

    app.add_api_route(path, _make_handler(title, path), response_class=HTMLResponse)
