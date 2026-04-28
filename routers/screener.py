"""
routers/screener.py — Screener-Seite + Scan-Endpoint.

GET  /screener        → rendert die Screener-Seite
POST /screener/scan   → fuehrt den Scan aus, liefert Ergebnisse als HTML-Partial
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from services.screener import PRESETS, scan_sp500, scan_dax_mdax
from main import get_header_metrics

router = APIRouter(tags=["pages"])


# ---------------------------------------------------------------------------
# Hilfsfunktionen (aus views/pages/screener.py portiert)
# ---------------------------------------------------------------------------

def _score_emoji(confidence: float) -> str:
    if confidence >= 75:
        return "🟢"
    elif confidence >= 60:
        return "↗️"
    elif confidence >= 45:
        return "➖"
    elif confidence >= 30:
        return "↘️"
    return "🔴"


def _signal_type(confidence: float) -> str:
    if confidence >= 65:
        return "Buy"
    elif confidence <= 35:
        return "Sell"
    return "Hold"


def _confidence_color(confidence: float) -> str:
    if confidence >= 70:
        return "var(--accent)"
    elif confidence >= 55:
        return "#64C8FF"
    elif confidence >= 40:
        return "var(--text-dim)"
    elif confidence >= 25:
        return "#FFB347"
    return "var(--red)"


def _signal_badge_class(signal: str) -> str:
    if signal == "Buy":
        return "badge-success"
    elif signal == "Sell":
        return "badge-danger"
    return "badge-neutral"


# ---------------------------------------------------------------------------
# Seite
# ---------------------------------------------------------------------------

@router.get("/screener", response_class=HTMLResponse)
async def screener_page(request: Request):
    """Rendert die Screener-Seite (Formular, kein Scan)."""
    templates = request.app.state.templates

    # Sektor-Liste fuer den Filter
    sectors = [
        "", "Information Technology", "Health Care", "Financials",
        "Consumer Discretionary", "Communication Services",
        "Industrials", "Consumer Staples", "Energy",
        "Utilities", "Real Estate", "Materials",
    ]

    ctx = {
        "request": request,
        "current_path": "/screener",
        "header_metrics": get_header_metrics(),
        "presets": PRESETS,
        "sectors": sectors,
    }
    return templates.TemplateResponse(
        request=request,
        name="pages/screener.html",
        context=ctx,
    )


@router.post("/screener/scan", response_class=HTMLResponse)
async def screener_scan(
    request: Request,
    index: str = Form("sp500"),
    preset: str = Form("all"),
    score_min: int = Form(0),
    rsi_min: int = Form(0),
    rsi_max: int = Form(100),
    sector: str = Form(""),
):
    """Fuehrt den Scan aus und liefert die Ergebnis-Tabelle als HTML-Partial."""
    templates = request.app.state.templates
    is_dax = index == "dax"
    currency_symbol = "EUR" if is_dax else "$"

    # Custom-Filter bauen
    custom_filters = {}
    if score_min > 0:
        custom_filters["score_min"] = score_min
    if rsi_min > 0 or rsi_max < 100:
        custom_filters["rsi_min"] = rsi_min
        custom_filters["rsi_max"] = rsi_max
    if sector:
        custom_filters["sector"] = sector

    # Scan ausfuehren
    scan_fn = scan_dax_mdax if is_dax else scan_sp500
    results = scan_fn(
        preset=preset,
        custom_filters=custom_filters if custom_filters else None,
    )

    # Ergebnisse fuer Template vorbereiten
    processed_results = []
    for r in results:
        signal = _signal_type(r["confidence"])
        processed_results.append({
            **r,
            "emoji": _score_emoji(r["confidence"]),
            "signal": signal,
            "signal_badge": _signal_badge_class(signal),
            "confidence_color": _confidence_color(r["confidence"]),
            "rsi_display": f"{r['rsi']:.1f}" if r["rsi"] else "---",
            "price_display": f"{r['price']:,.2f}",
        })

    # Statistiken
    stats = {}
    if results:
        scores = [r["confidence"] for r in results]
        stats = {
            "total": len(results),
            "avg_score": sum(scores) / len(scores),
            "buy_count": sum(1 for s in scores if s >= 65),
            "sell_count": sum(1 for s in scores if s <= 35),
        }

    ctx = {
        "request": request,
        "results": processed_results,
        "stats": stats,
        "currency": currency_symbol,
        "top5": processed_results[:5] if len(processed_results) >= 10 else [],
        "bottom5": list(reversed(processed_results[-5:])) if len(processed_results) >= 10 else [],
    }

    return templates.TemplateResponse(
        request=request,
        name="partials/screener_results.html",
        context=ctx,
    )
