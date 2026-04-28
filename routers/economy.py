"""routers/economy.py — Gesamtwirtschaft (Kalender, Rohstoffe, Zinsen, Inflation, News)."""
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

def _get_header_metrics():
    from main import get_header_metrics
    return get_header_metrics()

def _fig_to_json(fig):
    if fig is None:
        return "null"
    return json.dumps(fig.to_dict(), default=str)

@router.get("/economy", response_class=HTMLResponse)
async def economy_page(request: Request):
    templates = request.app.state.templates
    from services.cache_core import (
        cached_history, cached_yield_spread, cached_inflation,
        cached_regional_news, cached_upcoming_events, cached_calendar_summary,
    )
    from views.components.charts import plot_timeseries, plot_yield_spread, plot_inflation

    # Calendar
    summary = cached_calendar_summary()
    events_all = cached_upcoming_events(days=14, country="") or []
    events_us = cached_upcoming_events(days=14, country="US") or []
    events_eu = cached_upcoming_events(days=14, country="EU") or []
    events_de = cached_upcoming_events(days=14, country="DE") or []

    # Commodities charts
    charts = {}
    try:
        gold = cached_history("GC=F", "5y")
        charts["gold"] = _fig_to_json(plot_timeseries(gold, "Gold (GC=F)", color="#f59e0b")) if gold is not None else "null"
    except Exception:
        charts["gold"] = "null"
    try:
        oil = cached_history("CL=F", "5y")
        charts["oil"] = _fig_to_json(plot_timeseries(oil, "Rohöl (CL=F)", color="#3b82f6")) if oil is not None else "null"
    except Exception:
        charts["oil"] = "null"

    # Yield spread
    spread_val = None
    ten_y = None
    spread_status = None
    try:
        spread = cached_yield_spread()
        if spread is not None:
            charts["yield"] = _fig_to_json(plot_yield_spread(spread))
            spread_val = float(spread["Spread"].iloc[-1])
            ten_y = float(spread["10Y"].iloc[-1])
            spread_status = "Normal" if spread_val > 0 else "Invertiert — Rezessionswarnung"
        else:
            charts["yield"] = "null"
    except Exception:
        charts["yield"] = "null"

    # Inflation
    infl_val = None
    try:
        inflation = cached_inflation()
        if inflation is not None and not inflation.empty:
            charts["inflation"] = _fig_to_json(plot_inflation(inflation))
            infl_val = float(inflation["Inflation %"].iloc[-1])
        else:
            charts["inflation"] = "null"
    except Exception:
        charts["inflation"] = "null"

    # News
    news_eu = cached_regional_news("europa") or []
    news_us = cached_regional_news("usa") or []
    news_asia = cached_regional_news("asien") or []

    ctx = {
        "current_path": "/economy",
        "header_metrics": _get_header_metrics(),
        "summary": summary,
        "events_all": events_all,
        "events_us": events_us,
        "events_eu": events_eu,
        "events_de": events_de,
        "charts": charts,
        "spread_val": spread_val,
        "ten_y": ten_y,
        "spread_status": spread_status,
        "infl_val": infl_val,
        "news_eu": news_eu,
        "news_us": news_us,
        "news_asia": news_asia,
    }
    return templates.TemplateResponse(request=request, name="pages/economy.html", context=ctx)
