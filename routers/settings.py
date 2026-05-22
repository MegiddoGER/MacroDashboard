"""
routers/settings.py — Einstellungen (API-Keys, Konfiguration).

Bietet eine UI-Seite zum Verwalten von Dashboard-Einstellungen,
insbesondere dem Quiver Quantitative API-Token.
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from database import get_setting, set_setting

router = APIRouter(tags=["settings"])


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Rendert die Einstellungsseite."""
    templates = request.app.state.templates

    # Aktuellen Token laden (maskiert anzeigen)
    token = get_setting("QUIVER_API_TOKEN", "")
    token_masked = ""
    if token:
        if len(token) > 8:
            token_masked = token[:4] + "•" * (len(token) - 8) + token[-4:]
        else:
            token_masked = "•" * len(token)

    return templates.TemplateResponse(request=request, name="pages/settings.html", context={
        "request": request,
        "quiver_token_masked": token_masked,
        "quiver_token_set": bool(token),
        "current_path": "/settings",
    })


@router.post("/settings/api-keys", response_class=HTMLResponse)
async def save_api_keys(request: Request, quiver_token: str = Form("")):
    """Speichert den Quiver API Token in der Datenbank."""
    templates = request.app.state.templates

    quiver_token = quiver_token.strip()
    saved = False
    error = ""

    if quiver_token:
        # Einfache Validierung: Token sollte nicht leer und mindestens 10 Zeichen lang sein
        if len(quiver_token) < 10:
            error = "Der Token ist zu kurz. Bitte prüfe deine Eingabe."
        else:
            set_setting("QUIVER_API_TOKEN", quiver_token)
            saved = True

            # Cache invalidieren, damit der neue Token sofort genutzt wird
            try:
                from services.quiver import _cache, _cache_lock
                with _cache_lock:
                    _cache.clear()
            except Exception:
                pass
    else:
        # Leerer Token = Token löschen
        set_setting("QUIVER_API_TOKEN", "")
        saved = True

    # Token für Anzeige maskieren
    token = get_setting("QUIVER_API_TOKEN", "")
    token_masked = ""
    if token:
        if len(token) > 8:
            token_masked = token[:4] + "•" * (len(token) - 8) + token[-4:]
        else:
            token_masked = "•" * len(token)

    # HTMX-Partial zurückgeben
    return templates.TemplateResponse(request=request, name="partials/settings_feedback.html", context={
        "request": request,
        "saved": saved,
        "error": error,
        "quiver_token_masked": token_masked,
        "quiver_token_set": bool(token),
    })
