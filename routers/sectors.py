"""routers/sectors.py — Sektor-Performance (Heatmap, Drilldown)."""
import json
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

def _get_header_metrics():
    from main import get_header_metrics
    return get_header_metrics()

def _fig_to_json(fig):
    if fig is None:
        return "null"
    return json.dumps(fig.to_dict(), default=str)

@router.get("/sectors", response_class=HTMLResponse)
async def sectors_page(
    request: Request,
    region: str = Query("us"),
    period: str = Query("1d"),
):
    templates = request.app.state.templates
    from services.cache_core import cached_sectors
    from views.components.charts import plot_sector_heatmap

    period_labels = {
        "1d": "1 Tag", "1w": "1 Woche", "1m": "1 Monat",
        "3m": "3 Monate", "ytd": "Seit Jahresanfang", "1y": "1 Jahr",
    }
    region_title = "S&P 500" if region == "us" else "STOXX Europe 600"
    currency = "$" if region == "us" else "€"

    sector_df = cached_sectors(period, region)
    rows = []
    best = worst = None
    heatmap_json = "null"
    if sector_df is not None and not sector_df.empty:
        try:
            fig = plot_sector_heatmap(sector_df, f"{region_title} — {period_labels.get(period, period)}")
            heatmap_json = _fig_to_json(fig)
        except Exception:
            pass
        best = {"name": sector_df.iloc[0]["Sektor"], "pct": float(sector_df.iloc[0]["Veränderung %"])}
        worst = {"name": sector_df.iloc[-1]["Sektor"], "pct": float(sector_df.iloc[-1]["Veränderung %"])}
        for _, r in sector_df.iterrows():
            rows.append({
                "sector": r.get("Sektor",""),
                "ticker": r.get("Ticker",""),
                "price": f"{r.get('Kurs',0):,.2f} {currency}",
                "change": float(r.get("Veränderung %", 0)),
            })

    ctx = {
        "current_path": "/sectors",
        "header_metrics": _get_header_metrics(),
        "region": region,
        "period": period,
        "period_labels": period_labels,
        "region_title": region_title,
        "heatmap_json": heatmap_json,
        "rows": rows,
        "best": best,
        "worst": worst,
    }
    return templates.TemplateResponse(request=request, name="pages/sectors.html", context=ctx)
