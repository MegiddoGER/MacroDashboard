"""
routers/home.py — Cockpit / Startseite.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from services.cache_core import (
    cached_vix, cached_sp500, cached_gold, cached_multi, cached_hit_rate
)
from services.technical import calc_fear_greed_components, fear_greed_label
from services.watchlist import get_ticker_list, get_display_map, calc_portfolio_summary
from models.alerts import AlertStore
from models.journal import JournalStore
from services.economic_calendar import get_upcoming_events

router = APIRouter(tags=["pages"])


def _header_metrics():
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
                "value": f"{q['price']:,.2f}",
                "change_pct": q.get("change_pct"),
            })
        else:
            metrics.append({"label": label, "value": "---", "change_pct": None})
    return metrics


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Rendert die Cockpit-Startseite."""
    templates = request.app.state.templates

    # 1. Portfolio
    prices = {}
    try:
        ticker_list = get_ticker_list()
        if ticker_list:
            df_prices = cached_multi(",".join(ticker_list))
            if df_prices is not None and not df_prices.empty:
                for _, row in df_prices.iterrows():
                    prices[row["Ticker"]] = row["Kurs (€)"]
    except Exception:
        pass

    portfolio = calc_portfolio_summary(prices)

    # 2. Alerts
    unack_alerts = AlertStore.get_triggered_unacknowledged()
    active_alerts = AlertStore.get_active()

    # 3. Macro Events
    upcoming_macro = None
    try:
        macro_events = get_upcoming_events()
        if macro_events:
            upcoming_macro = macro_events[0]
    except Exception:
        pass

    # 4. Journal Stats
    j_stats = JournalStore.get_statistics()

    # 5. Fear & Greed
    fg_value, fg_label_text = None, None
    vix = cached_vix()
    sp500 = cached_sp500()
    gold = cached_gold()
    if vix is not None and sp500 is not None:
        fg_data = calc_fear_greed_components(vix, sp500, gold)
        fg_value = fg_data["total"]
        fg_label_text = fear_greed_label(fg_value)

    # 6. Hit Rate
    hit_rate = cached_hit_rate(90)

    # 7. Watchlist Flow
    watchlist_df = None
    ticker_list = get_ticker_list()
    display_map = get_display_map()
    if ticker_list:
        df = cached_multi(",".join(ticker_list))
        if df is not None and not df.empty:
            if "Ticker" in df.columns:
                df["Display"] = df["Ticker"].map(lambda t: display_map.get(t, t))
            watchlist_df = df

    # 8. Alert Archiv (History)
    ach_alerts = AlertStore.get_acknowledged()

    ctx = {
        "request": request,
        "current_path": "/",
        "header_metrics": _header_metrics(),
        "portfolio": portfolio,
        "unack_alerts": unack_alerts,
        "active_alerts": active_alerts,
        "ach_alerts": ach_alerts,
        "upcoming_macro": upcoming_macro,
        "j_stats": j_stats,
        "fg_value": fg_value,
        "fg_label": fg_label_text,
        "hit_rate": hit_rate,
        "watchlist_df": watchlist_df,
        "display_map": display_map,
    }
    return templates.TemplateResponse(request=request, name="pages/home.html", context=ctx)


@router.post("/home/clear_archive", response_class=HTMLResponse)
async def clear_archive(request: Request):
    """Löscht alle archivierten Alerts."""
    ach_alerts = AlertStore.get_acknowledged()
    for a in ach_alerts:
        AlertStore.delete_alert(a.id)
    return HTMLResponse("<script>showToast('Archiv geleert!');setTimeout(()=>location.reload(),500);</script>")

