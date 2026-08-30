---
name: observability
description: How MacroDashboard logs and handles errors — the logging.getLogger(__name__) convention already established in snapshot_engine/, and the rule for narrowing broad except Exception blocks. Use when adding error handling, converting print() to logging, or debugging a "missing data" report where the cause vanished silently.
---

# Observability: logging and error handling

The app has two halves. `snapshot_engine/`, `backfill_cli.py` and
`services/market_data_batch.py` use `logging` properly. Everything else — routers, most
services, `main.py`, `launcher.py`, `database.py` — uses ad hoc `print()` and swallows
exceptions. That second half is why "data is missing" reports are hard to diagnose: the
failure happened, nothing recorded it.

**Do not invent a new convention.** The one below already exists in the codebase. Match it.

## The logging convention

```python
import logging

logger = logging.getLogger(__name__)   # Modulebene, direkt nach den Imports
```

Reference: [snapshot_engine/backfill_service.py](snapshot_engine/backfill_service.py),
[snapshot_engine/models.py](snapshot_engine/models.py),
[snapshot_engine/auswertung_adapter.py](snapshot_engine/auswertung_adapter.py).

Rules, all visible in those files:

- **Lazy `%s` formatting, never f-strings.** `logger.info("Backfill #%d gestartet: %d Ticker.", job_id, n)` — the format cost is skipped when the level is disabled, and the message stays groupable.
- **German messages**, matching code comments and commits.
- **`exc_info=True` on every `logger.error`** in an except block. Without it you get the message and lose the traceback, which is most of the value.
- **Level discipline:**
  - `logger.error(..., exc_info=True)` — the operation failed and the caller gets nothing useful.
  - `logger.warning(...)` — degraded but continuing (fallback used, a ticker skipped, a field missing).
  - `logger.info(...)` — lifecycle events worth seeing in a normal run (job started/finished, table migrated).
  - `logger.debug(...)` — per-ticker, per-row noise. `snapshot_engine/backfill_service.py:324` is the model: a per-symbol scoring failure inside a loop over hundreds of symbols is `debug`, not `warning`.

## Converting a module from `print()`

1. Add the two lines above.
2. Replace each `print(f"[WARN] ...")` with the matching level and lazy args.
3. `config.py` is the deliberate exception — it prints because it runs before any logging is
   configured, at import time. Leave it.

## Narrowing `except Exception`

There are roughly 190 broad handlers. `services/market_data.py` has 30,
`routers/analysis.py` has 33. Do not attempt a repo-wide sweep; narrow the handlers in the
code you are already touching.

Replace `except Exception:` with what the call site can actually raise:

| Call site | Realistic exceptions |
|---|---|
| `requests` / HTTP | `requests.RequestException` (covers timeout, connection, HTTP error) |
| yfinance / pandas_datareader | `Exception` is genuinely hard to narrow — yfinance raises loosely. Keep broad, but **log it**, and say why in a comment. |
| Parsing an API response dict | `KeyError`, `TypeError`, `ValueError` |
| Numeric conversion | `ValueError`, `TypeError`, `ZeroDivisionError` |
| SQLAlchemy | `sqlalchemy.exc.SQLAlchemyError` |

Two hard rules:

- **Never a bare `except:`.** It catches `KeyboardInterrupt` and `SystemExit`. Two exist
  (`launcher.py`, `services/portfolio.py`) — fix them if you are in the file.
- **Never `except ...: pass` on a data path.** Silence here is the actual bug. At minimum
  `logger.warning("...: %s", e)`. The one acceptable silent handler is
  `config.get_api_token()`, where a DB miss is an expected path with a defined fallback.

When a broad handler must stay, it still logs and still says what it is protecting:

```python
try:
    df = _fetch_history(ticker)
except Exception as e:  # yfinance wirft uneinheitliche Fehlertypen
    logger.warning("Kursdaten für %s nicht abrufbar: %s", ticker, e)
    return None
```

## Degradation must be visible

The Quiver → yfinance fallback in [services/quiver.py](services/quiver.py) is the right
shape, but a fallback that logs nothing looks identical to a success. Any path that returns
lower-quality data logs a `warning` naming the reason, so a wrong number on screen can be
traced back to the feed that produced it.
