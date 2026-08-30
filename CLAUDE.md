# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MacroDashboard is a self-hosted, local-first trading/investing terminal: FastAPI + Jinja2 + HTMX
frontend, SQLAlchemy/SQLite persistence, APScheduler background jobs, Plotly charts, and
yfinance/pandas_datareader/Quiver Quantitative for market data. It covers portfolio tracking, a
technical+fundamental screener, single-stock deep analysis (SMC/liquidity, sector-adaptive quant
scoring), backtesting, a trade journal, sector heatmaps, and a daily snapshot engine for signal
outcome tracking. See `Benutzerhandbuch.md` for the full end-user feature walkthrough (German).

Code comments and commit messages are largely in German; keep that convention when editing
existing modules unless the user asks otherwise.

## Commands

Run everything with the `py` launcher (Windows).

```
py -m uvicorn main:app --reload --port 8501    # dev server with reload
py launcher.py                                  # native desktop window (system tray) + server
py -m pytest                                     # run all tests
py -m pytest tests/test_position_management.py -k test_long_target_reached   # single test
```

There is no lint/format/typecheck config committed (no `pyproject.toml`, `mypy.ini`, or CI
workflow) despite a `.mypy_cache/` existing — type checking has historically been run ad hoc with
`py -m mypy <files>`, not as a repeatable step. Don't assume a `mypy` or `ruff` config exists;
check before relying on one.

## Architecture

### Layering

`routers/*.py` → `services/*.py` → `models/*.py` + `database.py`. Routers stay thin (parse
request, call a service, render a template or HTMX partial); business logic lives in `services/`.
Services should not touch the DB directly except through `models/`. This separation is followed
consistently — preserve it when adding features.

`main.py` wires the FastAPI app: DB init, Jinja2 templates (`app.state.templates`), one router
include per feature area, and a `lifespan` that also boots the snapshot engine's scheduler.

### Configuration (`config.py` + `.env`)

`config.py` is the single entry point for all environment configuration. Importing it loads
`.env` from the project root once via `python-dotenv` (`override=False`, so real OS env vars win
— that matters for server deployment). Any module needing a setting imports `config`, which makes
import order irrelevant. `.env` is gitignored; `.env.example` is the committed template and
documents *every* external API the project touches, including the keyless ones.

- Secrets: `config.get_api_token(key)` reads the DB `Setting` table first (the `/settings` UI),
  then falls back to `.env`. Used by `services/quiver.py` and `services/news.py` (Finnhub).
  DB-first means a token entered in the UI overrides `.env` without a restart.
- Plain values are module-level constants: `DATABASE_URL` (empty → `database.py` keeps its
  absolute SQLite default), `APP_HOST`/`APP_PORT` (`launcher.py`), `SEC_USER_AGENT` /
  `SCRAPER_USER_AGENT` / `CONGRESS_USER_AGENT`, `SNAPSHOT_RUN_TIME`
  (`snapshot_engine/scheduler.py`).

Add new external config here rather than reading `os.environ` ad hoc, and document it in
`.env.example`. Note `config.get_api_token()` imports `database` lazily — `database.py` imports
`config`, so a top-level import would be circular.

### Two different "models"

- `database.py` — the actual SQLAlchemy ORM layer: engine/session factory (`get_session()`),
  every table model (`WatchlistItem`, `Position`, `JournalEntry`, `SignalRecord`, `AlertRecord`,
  `Setting`), and a one-time JSON→SQLite migration (`init_db()` reads legacy `data/*.json` files
  on first run if the DB is empty).
- `models/*.py` — plain dataclasses / domain types used by services (e.g. `models/watchlist.py`
  defines a `WatchlistItem` dataclass distinct from `database.py`'s ORM `WatchlistItem`). Don't
  confuse the two when tracing a bug — check which module a name was imported from.

SQLite runs in WAL mode with foreign keys on. Switching to Postgres is a single line
(`DATABASE_URL` in `database.py`).

### Caching

`services/cache_core.py` wraps most external-data service calls (`services/market_data.py`,
`services/news.py`, `services/economic_calendar.py`, `services/options.py`,
`services/portfolio.py`, `services/risk.py`, `services/signal_history.py`) in
`cachetools.TTLCache` instances, keyed per data type with its own maxsize/TTL. Market-hours
awareness (`_is_market_open()`, Xetra/US sessions in `Europe/Berlin` time) exists but individual
cache TTLs are currently hardcoded rather than driven by `_market_ttl()`. `clear_all_caches()` is
the "force refresh" hook wired to the sidebar's manual refresh button. When adding a new external
data fetch, add a `cached_*` wrapper here rather than caching ad hoc in the service or router.

### Position analysis pipeline (two generations coexist)

- **Legacy / current production path**: `services/scoring.py` (a 1,354-line monolith) is what
  `routers/analysis.py` actually calls today (`calc_quick_score`, `calc_position_score`,
  `generate_position_relevance`).
- **Newer, more structured engine**: `services/position_types.py` (all enums/dataclasses —
  `PositionSide`, `AnalysisMode`, `TargetStatus`, `RecommendationType`, etc.) feeds a pipeline of
  `services/target_stop_validator.py` → `services/position_state_engine.py` →
  `services/position_metrics_engine.py` → `services/scoring_engine_v2.py` →
  `services/recommendation_engine.py`, with `services/data_quality_engine.py` assessing input
  completeness. `tests/test_position_management.py` (the only test file) exercises this pipeline,
  not `scoring.py`.

It is not fully resolved which path is authoritative for which surface — check which module a
call site actually imports (`services.scoring` vs `services.scoring_engine_v2` /
`services.recommendation_engine`) before assuming behavior, and don't assume changes to one path
affect the other.

### Snapshot engine

`snapshot_engine/` is a self-contained subsystem with its own models (`snapshot_engine/models.py`:
`AnalyseSnapshot`, `SnapshotKonfiguration`), router (prefix `/snapshot`), and an APScheduler
`AsyncIOScheduler` cron job (`snapshot_engine/scheduler.py`, default 18:30 CET) started/stopped
from `main.py`'s lifespan. The daily job always runs in two ordered steps — snapshot creation
(`snapshot_engine.snapshot_service.alle_snapshots_ausfuehren`) then outcome backfill
(`outcomes_nachtragen`) — this order is invariant since outcomes depend on prior snapshots
existing. Purpose is tracking signal predictions against realized outcomes (groundwork for
ML/signal-quality feedback).

### Frontend

Server-rendered Jinja2 (`templates/pages/*.html` for full pages, `templates/partials/*.html` for
HTMX-swapped fragments) + HTMX 2.0.4 (loaded via CDN in `templates/base.html`) + vanilla CSS
(`static/css/`, split into `tokens.css`/`layout.css`/`sidebar.css`/`components.css`). No JS
bundler/frontend framework. Plotly figures are computed server-side and serialized to JSON
(`_fig_to_json` pattern in `routers/analysis.py`) for client-side rendering. `header_metrics_fn`
(defined in `main.py`) is injected as a Jinja2 global so every template can render the top-bar
S&P/Gold/DXY metrics without each router recomputing them.

### External data & degradation

`services/quiver.py` wraps Quiver Quantitative (institutional holdings, congress trades, insider
data — needs `QUIVER_API_TOKEN` in `.env`) and falls back to `yfinance` when no token is
configured. Most other market data goes through `services/market_data.py`
(yfinance/pandas_datareader).

## Known rough edges (see REVIEW.md for full detail)

- Broad `except Exception` (~190 occurrences) and a couple of bare `except:` are still common.
  `logging` has since been adopted in `snapshot_engine/` and `backfill_cli.py`/
  `services/market_data_batch.py`, but the rest of the app (routers, most services, `main.py`,
  `launcher.py`, `database.py`) still relies on ad hoc `print()`. Failures in scheduled jobs or
  data fetches outside `snapshot_engine/` can still fail silently; keep this in mind when
  debugging "missing data" reports.
- `services/quiver.py` has unverified field-mapping TODOs (Quiver API response fields never
  confirmed against real responses).
