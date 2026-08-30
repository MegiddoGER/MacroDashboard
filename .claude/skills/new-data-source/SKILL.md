---
name: new-data-source
description: End-to-end recipe for wiring a new external data feed into MacroDashboard — .env.example, config.py, the service module with its degradation fallback, the cached_* wrapper in cache_core.py, logging, and verifying field names against a real API response. Use when adding any outbound data call (market data, news, fundamentals, alternative data).
---

# Adding an external data source

Five files in a fixed order. The order matters because the steps that get skipped are
always the ones at the end — and the two most-skipped (caching and field verification) are
the two that cause silent wrong numbers rather than loud failures.

## 1. Document it in `.env.example`

First, not last. [.env.example](.env.example) documents **every** external API this project
touches, including the keyless ones — that completeness is what makes it usable as a
deployment checklist. Add an entry with: what the service provides, whether a key is
required, where to get one, and the free-tier limit if there is one. Comments in German.

`.env` itself is gitignored. Never write a real key into `.env.example`.

## 2. Add the setting to `config.py`

[config.py](config.py) is the single entry point for environment configuration; importing it
loads `.env` once with `override=False`, so real OS env vars win — which is what will matter
when this moves off localhost onto a server.

**Secrets** — do not add a constant. Read them at call time:

```python
import config

token = config.get_api_token("FINNHUB_API_TOKEN")
if not token:
    logger.warning("Finnhub-Token fehlt — Fallback auf yfinance.")
```

`get_api_token()` checks the DB `Setting` table (the `/settings` page) before `.env`, so a
token typed into the UI takes effect without a restart. Reading it at call time is what
makes that work; a module-level constant would freeze the value at import.

**Plain values** — a module-level constant next to the related ones, using `get_env` /
`get_env_int` with a sensible default:

```python
FOO_USER_AGENT = get_env("FOO_USER_AGENT", "MacroDashboard/1.0")
```

Never read `os.environ` from a service or router.

## 3. Write `services/<name>.py`

Plain functions, no DB access, no FastAPI imports, no caching (that comes in step 4).

**Every external feed needs an explicit degradation path.** The reference is
[services/quiver.py](services/quiver.py): no token configured, or the call fails → fall back
to yfinance rather than raising. The dashboard showing slightly worse data beats the
dashboard showing an error page.

Degradation must be *visible* in the log (see the `observability` skill) — a silent fallback
looks exactly like a success, and then a number on screen has no traceable origin:

```python
logger = logging.getLogger(__name__)

def get_insider_activity(ticker: str) -> dict | None:
    """Insider-Aktivität. Ohne Quiver-Token Rückfall auf yfinance."""
    token = config.get_api_token("QUIVER_API_TOKEN")
    if not token:
        logger.warning("Quiver-Token fehlt — %s über yfinance (geringere Qualität).", ticker)
        return _yfinance_fallback(ticker)
    try:
        ...
    except requests.RequestException as e:
        logger.warning("Quiver-Abruf für %s fehlgeschlagen: %s", ticker, e)
        return _yfinance_fallback(ticker)
```

Return `None` for "unknown", never `0` or `0.0`. Downstream, a zero renders as a real value
and reads as fact.

## 4. Add a `cached_*` wrapper in `services/cache_core.py`

Not optional, and not done inside the service. [services/cache_core.py](services/cache_core.py)
is the one place caching lives, which is what makes the sidebar's manual refresh
(`clear_all_caches()`) actually clear everything.

Import the raw function at the top of the module with the others, create a `TTLCache` with a
deliberate `maxsize` and `ttl`, and expose a `cached_<name>` wrapper. Pick the TTL from how
fast the data actually moves: quotes and history use 300 s, slower reference data 1800 s.
There is a market-hours helper (`_is_market_open()`, `_market_ttl()`, Xetra and US sessions
in `Europe/Berlin`) — current caches use hardcoded TTLs rather than calling it, so follow the
neighbouring entries unless you have a reason to differ.

Routers and other services then import `cached_<name>`, never the raw function.

## 5. Verify the field names against a real response

**This is the step that produces wrong numbers when skipped.**
[services/quiver.py](services/quiver.py) still carries three `# TODO: verify — Feldnamen der
Quiver API prüfen` markers (lines 215, 278, 365) because a mapping was written from
assumption and never checked. Code that reads `row["Transaction"]` when the API returns
`row["TransactionType"]` does not crash — it hits the `except`, falls back, and quietly
shows the wrong thing forever.

Confirm every field you read against an actual response — a live call with a real token, or
current provider documentation. Delegate to the **`data-source-scout`** agent, which does
this in its own context so that API documentation does not crowd out the working session.

Only once the mapping is confirmed, remove the TODO marker.

## 6. Finish

Run the `ship-check` skill. If the new feed influences a displayed number, the
`quant-testing` skill governs the test for the calculation that consumes it.
