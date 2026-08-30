---
name: new-surface
description: Recipe for adding a page or an HTMX-swapped fragment to MacroDashboard — router, main.py wiring, page vs partial template, the PLOTLY_LAYOUT/renderPlotly chart pattern, header_metrics_fn, and the CSS load order. Use when adding any new screen, tab, or dynamically-swapped section to the frontend.
---

# Adding a page or HTMX fragment

Server-rendered Jinja2 + HTMX 2.0.4, both loaded from CDN in
[templates/base.html](templates/base.html). **No bundler, no build step, no JS framework.**
Anything requiring compilation is unusable here.

## 1. Router

New feature area → new `routers/<area>.py`; an extension of an existing area → an endpoint
in the router that already owns it.

```python
"""routers/<area>.py — kurze deutsche Beschreibung."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])


@router.get("/<area>", response_class=HTMLResponse)
async def area_page(request: Request):
    templates = request.app.state.templates
    from services.<area> import load_something
    from services.cache_core import cached_something

    data = load_something()
    return templates.TemplateResponse("pages/<area>.html", {"request": request, "data": data})
```

Points that are conventions here, not accidents:

- **`request.app.state.templates`**, not a module-level `Jinja2Templates` — `main.py` owns
  the environment and its globals.
- **Service imports inside the handler.** Existing routers do this (see
  [routers/watchlist.py](routers/watchlist.py)); it keeps app startup fast and avoids import
  cycles. Follow it.
- **Thin.** Parse the request, call a service, render. No calculations, no DB session. If
  you are writing arithmetic in a router, it belongs in `services/`.
- **Cached wrappers only** — import `cached_*` from
  [services/cache_core.py](services/cache_core.py), never the raw service fetch.

Register it in [main.py](main.py) alongside the other `app.include_router(...)` calls.

## 2. Template: page or partial

- **`templates/pages/<name>.html`** — a full page. `{% extends "base.html" %}`, content in
  `{% block content %}`. It gets the app shell, the top navigation
  (`partials/topnav.html`) and all CSS automatically.
- **`templates/partials/<name>.html`** — a fragment returned to an HTMX swap. **No
  `extends`, no `<html>`** — just the markup being swapped in. Returning a full page into an
  `hx-target` nests a second document inside the first.

Endpoints that serve a partial return only the fragment. If one endpoint serves both a full
page and an HTMX refresh, branch on the `HX-Request` header rather than always rendering the
page.

The top-bar S&P/Gold/DXY metrics need nothing from your router: `header_metrics_fn` is
registered as a Jinja2 global in `main.py:96` and consumed by `partials/header.html`.

## 3. Charts

Plotly figures are built server-side and serialized, never constructed in JavaScript.

Router side — the helper is `fig_to_json` from [charts.py](charts.py) (note: not
`_fig_to_json`, and not defined in the router):

```python
from charts import fig_to_json
charts["rsi"] = fig_to_json(plot_rsi(rsi_series, f"RSI (14) — {ticker}"))
```

Template side — `base.html` provides both a shared `PLOTLY_LAYOUT` (dark, Inter, teal
`#00d4aa` accents) and a `renderPlotly(elementId, figJson)` helper. Merge the shared layout
so a new chart matches every existing one:

```html
<div id="rsi-chart"></div>
<script>
  const fig = JSON.parse({{ charts.rsi | tojson }});
  Plotly.newPlot('rsi-chart', fig.data,
                 Object.assign({}, PLOTLY_LAYOUT, fig.layout || {}),
                 {displayModeBar: true, responsive: true});
</script>
```

For a chart arriving inside an HTMX swap, call `renderPlotly` from the swapped fragment —
the script in the fragment runs after insertion.

## 4. CSS

Files in `static/css/`, loaded in this order — it is meaningful and stated in `base.html`:

```
tokens.css → layout.css → components.css → topnav.css → motion.css
```

Reuse the existing component classes (`.card`, `.btn`, `.badge`, `.data-table`,
`.table-wrapper`, `.caption`, `.muted`, `.positive`, `.negative`, `.page-header`, `.alert`,
`.form-label`). **Do not write inline `style="..."`** — the signal pages
(`pages/signal_quality.html`, `pages/signal_indikatoren.html`, `pages/signal_backfill.html`)
did that and visibly fall out of the system; that is debt being paid down, not a pattern to
copy. If a needed component does not exist, add it to `components.css` as a reusable class.

Any animation needs a `@media (prefers-reduced-motion: reduce)` escape, and animates
`transform`/`opacity` only — never width/height/top/left in tables with hundreds of rows.

For anything beyond reusing existing components, load the **`design-brief`** skill and, for
substantial visual work, the **`ui-designer`** agent.

## 5. Verify

Run the `ship-check` skill. Its route smoke test must include your new path — add it to the
URL list there and confirm every route still returns 200.
