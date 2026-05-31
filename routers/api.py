"""
routers/api.py — JSON-Endpunkte fuer HTMX-Partials und Daten-APIs.

Enthaelt:
- Header-Metriken (S&P 500, Gold, DXY)
- Watchlist CRUD
- Cache-Management
- System-Shutdown
"""

import os
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse

from services.cache_core import cached_quote, clear_all_caches
from services.watchlist import load_watchlist, add_to_watchlist, remove_from_watchlist, resolve_ticker

router = APIRouter(prefix="/api", tags=["api"])


# ---------------------------------------------------------------------------
# Header Metriken (HTMX Partial)
# ---------------------------------------------------------------------------

@router.get("/header", response_class=HTMLResponse)
async def header_metrics(request: Request):
    """Liefert die Top-3-Metriken als HTML-Partial (fuer HTMX-Refresh)."""
    from main import get_header_metrics
    metrics = get_header_metrics()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="partials/header.html",
        context={"header_metrics": metrics},
    )


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

@router.get("/watchlist/items", response_class=HTMLResponse)
async def watchlist_items(request: Request):
    """Liefert die Watchlist-Items als HTML-Partial."""
    items = load_watchlist()
    invested = [i for i in items if i.get("status") == "Investiert"]
    watching = [i for i in items if i.get("status", "Beobachtet") != "Investiert"]

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="partials/watchlist_items.html",
        context={"invested": invested, "watching": watching},
    )


@router.post("/watchlist/add", response_class=HTMLResponse)
async def watchlist_add(request: Request, query: str = Form("")):
    """Fuegt einen Ticker zur Watchlist hinzu."""
    if not query.strip():
        return HTMLResponse("<div class='alert alert-warning'>Bitte einen Ticker eingeben.</div>")

    result = resolve_ticker(query)
    if result:
        add_to_watchlist(result["ticker"], result["name"], result.get("display", ""))
        # Re-render the whole watchlist
        return await watchlist_items(request)
    else:
        return HTMLResponse(f"<div class='alert alert-danger'>'{query}' nicht gefunden.</div>")


@router.delete("/watchlist/{ticker}", response_class=HTMLResponse)
async def watchlist_delete(request: Request, ticker: str):
    """Entfernt einen Ticker von der Watchlist."""
    remove_from_watchlist(ticker)
    return await watchlist_items(request)


@router.get("/ticker/search")
async def ticker_search(q: str = Query("")):
    """Sucht nach Tickern (Autocomplete-Backend) und liefert JSON."""
    from services.watchlist import _search_xetra_csv
    if not q.strip() or len(q.strip()) < 1:
        return JSONResponse([])
    results = _search_xetra_csv(q)
    # Limitiere auf max 15 Vorschläge für UI-Performance
    return JSONResponse(results[:15])

@router.get("/ticker/quote")
async def ticker_quote(ticker: str = Query(...)):
    """Lädt den aktuellen Live-Kurs für einen Ticker."""
    from services.cache_core import cached_quote
    try:
        quote = cached_quote(ticker)
        price = quote.get("price") if isinstance(quote, dict) else quote
        return JSONResponse({"ticker": ticker, "price": price})
    except Exception:
        return JSONResponse({"ticker": ticker, "price": None})


# ---------------------------------------------------------------------------
# Cache Management
# ---------------------------------------------------------------------------

@router.post("/cache/clear")
async def cache_clear():
    """Leert alle Caches."""
    clear_all_caches()
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@router.post("/shutdown")
async def shutdown():
    """Beendet den Server."""
    os._exit(0)
