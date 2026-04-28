"""routers/lexicon.py — Analyse-Lexikon (rein statischer Content)."""
import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

def _get_header_metrics():
    from main import get_header_metrics
    return get_header_metrics()

@router.get("/lexicon", response_class=HTMLResponse)
async def lexicon_page(request: Request):
    templates = request.app.state.templates
    manual_html = ""
    manual_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Benutzerhandbuch.md")
    if os.path.exists(manual_path):
        try:
            import markdown
            with open(manual_path, "r", encoding="utf-8") as f:
                manual_html = markdown.markdown(f.read(), extensions=["tables", "fenced_code"])
        except ImportError:
            with open(manual_path, "r", encoding="utf-8") as f:
                manual_html = f"<pre>{f.read()}</pre>"
    ctx = {
        "current_path": "/lexicon",
        "header_metrics": _get_header_metrics(),
        "manual_html": manual_html,
    }
    return templates.TemplateResponse(request=request, name="pages/lexicon.html", context=ctx)
