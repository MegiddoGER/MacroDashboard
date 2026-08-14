"""routers/sources.py — Datenquellen & Methodik-Dokumentation."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    templates = request.app.state.templates
    ctx = {
        "current_path": "/sources",
    }
    return templates.TemplateResponse(
        request=request, name="pages/sources.html", context=ctx
    )
