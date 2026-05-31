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

    # Quiver Token
    quiver_token = get_setting("QUIVER_API_TOKEN", "")
    quiver_token_masked = ""
    if quiver_token:
        if len(quiver_token) > 8:
            quiver_token_masked = quiver_token[:4] + "•" * (len(quiver_token) - 8) + quiver_token[-4:]
        else:
            quiver_token_masked = "•" * len(quiver_token)

    # Finnhub Token
    finnhub_token = get_setting("FINNHUB_API_TOKEN", "")
    finnhub_token_masked = ""
    if finnhub_token:
        if len(finnhub_token) > 8:
            finnhub_token_masked = finnhub_token[:4] + "•" * (len(finnhub_token) - 8) + finnhub_token[-4:]
        else:
            finnhub_token_masked = "•" * len(finnhub_token)

    return templates.TemplateResponse(request=request, name="pages/settings.html", context={
        "request": request,
        "quiver_token_masked": quiver_token_masked,
        "quiver_token_set": bool(quiver_token),
        "finnhub_token_masked": finnhub_token_masked,
        "finnhub_token_set": bool(finnhub_token),
        "current_path": "/settings",
    })


@router.post("/settings/api-keys", response_class=HTMLResponse)
async def save_api_keys(
    request: Request,
    quiver_token: str = Form(None),
    finnhub_token: str = Form(None)
):
    """Speichert die API Tokens in der Datenbank."""
    templates = request.app.state.templates
    saved = False
    error = ""

    # --- Quiver Token ---
    if quiver_token is not None:
        qt = quiver_token.strip()
        if qt:
            if len(qt) < 10:
                error += "Der Quiver Token ist zu kurz. "
            else:
                set_setting("QUIVER_API_TOKEN", qt)
                saved = True
                try:
                    from services.quiver import _cache, _cache_lock
                    with _cache_lock:
                        _cache.clear()
                except Exception:
                    pass
        else:
            set_setting("QUIVER_API_TOKEN", "")
            saved = True

    # --- Finnhub Token ---
    if finnhub_token is not None:
        ft = finnhub_token.strip()
        if ft:
            if len(ft) < 10:
                error += "Der Finnhub Token ist zu kurz. "
            else:
                set_setting("FINNHUB_API_TOKEN", ft)
                saved = True
                try:
                    from services.cache_core import _company_news_cache, _lock
                    with _lock:
                        _company_news_cache.clear()
                except Exception:
                    pass
        else:
            set_setting("FINNHUB_API_TOKEN", "")
            saved = True
            
            try:
                from services.cache_core import _company_news_cache, _lock
                with _lock:
                    _company_news_cache.clear()
            except Exception:
                pass

    # Maskierte Tokens für Feedback neu laden
    qt_current = get_setting("QUIVER_API_TOKEN", "")
    qt_masked = ""
    if qt_current:
        if len(qt_current) > 8:
            qt_masked = qt_current[:4] + "•" * (len(qt_current) - 8) + qt_current[-4:]
        else:
            qt_masked = "•" * len(qt_current)

    ft_current = get_setting("FINNHUB_API_TOKEN", "")
    ft_masked = ""
    if ft_current:
        if len(ft_current) > 8:
            ft_masked = ft_current[:4] + "•" * (len(ft_current) - 8) + ft_current[-4:]
        else:
            ft_masked = "•" * len(ft_current)

    return templates.TemplateResponse(request=request, name="partials/settings_feedback.html", context={
        "request": request,
        "saved": saved,
        "error": error.strip(),
        "quiver_token_masked": qt_masked,
        "quiver_token_set": bool(qt_current),
        "finnhub_token_masked": ft_masked,
        "finnhub_token_set": bool(ft_current),
    })
