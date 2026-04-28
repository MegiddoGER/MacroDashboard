"""routers/directory.py — Aktien-Verzeichnis."""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

def _get_header_metrics():
    from main import get_header_metrics
    return get_header_metrics()

@router.get("/directory", response_class=HTMLResponse)
async def directory_page(
    request: Request,
    search: str = Query("", alias="q"),
    exchange: str = Query("Alle", alias="exchange"),
    letter: str = Query("Alle", alias="letter"),
):
    templates = request.app.state.templates
    from services.cache_core import cached_listings
    df = cached_listings()

    rows = []
    total = 0
    exchanges = ["Alle"]
    if df is not None and not df.empty:
        exchanges += sorted(df["Börse"].dropna().unique().tolist())
        filtered = df.copy()
        if exchange != "Alle":
            filtered = filtered[filtered["Börse"] == exchange]
        if search.strip():
            q = search.strip().upper()
            filtered = filtered[
                filtered["Kürzel"].str.upper().str.contains(q, na=False) |
                filtered["Name"].str.upper().str.contains(q, na=False)
            ]
        elif letter != "Alle":
            filtered = filtered[filtered["Kürzel"].str.startswith(letter, na=False)]
        total = len(filtered)
        rows = filtered.head(500).to_dict("records")

    ctx = {
        "current_path": "/directory",
        "header_metrics": _get_header_metrics(),
        "rows": rows,
        "total": total,
        "exchanges": exchanges,
        "search": search,
        "selected_exchange": exchange,
        "selected_letter": letter,
    }
    return templates.TemplateResponse(request=request, name="pages/directory.html", context=ctx)
