"""routers/sectors.py — Sektor-Performance (Heatmap, Drilldown)."""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

from charts import fig_to_json

router = APIRouter(tags=["pages"])

@router.get("/sectors", response_class=HTMLResponse)
async def sectors_page(
    request: Request,
    region: str = Query("us"),
    period: str = Query("1d"),
):
    templates = request.app.state.templates
    from services.cache_core import cached_sectors
    from charts import plot_sector_heatmap

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
            heatmap_json = fig_to_json(fig)
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
        "region": region,
        "period": period,
        "period_labels": period_labels,
        "region_title": region_title,
        "heatmap_json": heatmap_json,
        "rows": rows,
        "best": best,
        "worst": worst,
        "aufschluesselbar": region == "us",
    }
    return templates.TemplateResponse(request=request, name="pages/sectors.html", context=ctx)


@router.get("/sectors/bestandteile", response_class=HTMLResponse)
async def sektor_bestandteile_fragment(
    request: Request,
    sektor: str = Query(""),
    period: str = Query("1d"),
    region: str = Query("us"),
):
    """HTMX-Fragment: die Einzeltitel eines Sektors mit ihrer Veränderung.

    Bewusst nachgeladen statt Teil der Seite: die Aufschlüsselung kostet je
    Sektor einen Kursabruf über bis zu ~80 Titel. Alle zwölf Sektoren beim
    Seitenaufruf zu laden hieße, für einen Blick auf die Heatmap das halbe
    Universum zu ziehen.
    """
    import asyncio

    templates = request.app.state.templates
    from services.cache_core import (
        cached_components_performance, cached_sp500_components,
    )
    from services.market_data import sektor_aufschluesselbar, sektor_bestandteile

    sektor = (sektor or "").strip()
    currency = "$" if region == "us" else "€"

    if not sektor_aufschluesselbar(sektor, region):
        # Kein Fehler, sondern eine Datenlage: für Europa existiert im Projekt
        # keine Bestandteilsliste. Das gehört gesagt, nicht als leere Tabelle
        # getarnt.
        return templates.TemplateResponse(
            request=request, name="partials/sector_bestandteile.html",
            context={"sektor": sektor, "hinweis": (
                "Für den STOXX Europe 600 liegt keine Bestandteilsliste vor — "
                "die Aufschlüsselung gibt es nur für den S&P 500."
                if region != "us" else
                f"Für '{sektor}' ist keine Bestandteilsliste hinterlegt.")})

    titel = sektor_bestandteile(cached_sp500_components(), sektor)
    if not titel:
        return templates.TemplateResponse(
            request=request, name="partials/sector_bestandteile.html",
            context={"sektor": sektor,
                     "hinweis": "Bestandteilsliste derzeit nicht abrufbar."})

    perf = await asyncio.to_thread(
        cached_components_performance, ",".join(sorted(titel)), period)

    zeilen = []
    if perf is not None and not perf.empty:
        for _, r in perf.iterrows():
            ticker = str(r["Ticker"])
            zeilen.append({
                "ticker": ticker,
                "name": titel.get(ticker, ticker),
                "change": float(r["Veränderung %"]),
                "price": f"{float(r['Kurs']):,.2f} {currency}",
            })

    return templates.TemplateResponse(
        request=request, name="partials/sector_bestandteile.html",
        context={
            "sektor": sektor,
            "zeilen": zeilen,
            "anzahl_gesamt": len(titel),
            "periode_label": {
                "1d": "1 Tag", "1w": "1 Woche", "1m": "1 Monat",
                "3m": "3 Monate", "ytd": "Seit Jahresanfang", "1y": "1 Jahr",
            }.get(period, period),
            "hinweis": (None if zeilen else
                        "Für diesen Sektor kamen keine Kursdaten zurück."),
        })
