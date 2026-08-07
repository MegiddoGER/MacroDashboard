# MacroDashboard — Code Review

_Reviewed: 2026-08-07 · ~18,700 LOC Python · 122 commits · single-author (Megiddo)_

## Overview

A self-hosted, local-first trading/investing terminal: FastAPI + Jinja2 + HTMX
frontend, SQLAlchemy/SQLite persistence, APScheduler background jobs, Plotly
charts, yfinance/pandas_datareader/Quiver Quantitative for market data. Covers
portfolio tracking, a technical+fundamental screener, single-stock deep
analysis (SMC/liquidity, sector-adaptive quant scoring), backtesting, a trade
journal, sector heatmaps, and a daily snapshot engine that appears to be
laying groundwork for signal outcome tracking / ML feedback.

The project is well-organized at the directory level (`routers/` /
`services/` / `models/` separation is consistently followed) and unusually
well-documented for a solo project — `Benutzerhandbuch.md` reads like real
end-user docs, not a README stub.

## Strengths

- **Clean layering.** Routers stay thin; business logic consistently lives in
  `services/`. No obvious cases of DB access or scoring logic leaking into
  route handlers in the files sampled.
- **Sensible caching.** `services/cache_core.py` uses `cachetools.TTLCache`
  with market-hours-aware TTL (5 min open / 30 min closed) instead of a naive
  fixed cache — a detail a lot of hobby dashboards skip.
- **Graceful external-data degradation.** Quiver Quantitative integration
  falls back to yfinance when no API token is configured, rather than hard
  failing.
- **Daily snapshot/outcome engine** (`snapshot_engine/`) with an
  AsyncIOScheduler cron job is a genuinely nice piece of design — it
  separates "make a prediction" from "record what happened," which is the
  right foundation if the goal is eventually scoring signal quality or
  training on outcomes.
- **User-facing documentation exists and is good.** Most solo projects this
  size have none.

## Areas for Improvement

### 1. Error handling is broad and silent
35 files use `except Exception`, and two spots (`launcher.py:177`,
`services/portfolio.py:145`) use bare `except:`. Combined with there being
**no `logging` usage anywhere in the codebase** (only ad hoc `print()` in 10
files), failures in scheduled jobs or data-fetch paths can disappear
silently — you'd only notice missing data, not why it's missing. Worth
introducing `logging` with at least a rotating file handler, and narrowing
the broad excepts to the specific exceptions each call site can actually
raise (e.g. `requests`/`yfinance` errors vs. `KeyError` on malformed API
responses).

### 2. `services/scoring.py` is a 1,582-line monolith, and a v2 exists alongside it
`scoring.py` (73KB) and `scoring_engine_v2.py` (301 lines) coexist. It's
unclear from the file layout alone whether v2 has fully superseded v1,
partially replaces it, or is an experiment. This is the kind of thing that
becomes very hard to untangle six months from now — worth either finishing
the migration and deleting v1, or renaming to make the relationship explicit
(e.g. `scoring_legacy.py`).

### 3. Near-zero test coverage
Only one test file, `tests/test_position_management.py`. For a codebase that
computes stop-losses, position sizing, drawdown, and portfolio P&L — numbers
a real person might act on financially — the risk/scoring engines
(`position_metrics_engine.py`, `position_state_engine.py`,
`trailing_stop_engine.py`, `target_stop_validator.py`, `scoring_engine_v2.py`)
are exactly the modules I'd prioritize covering first, since a silent
miscalculation there is the costliest possible bug class in this app.

### 4. Type-checking isn't wired in, despite being used
A `.mypy_cache/` exists and a recent commit is literally titled "typecheck
errors," but there's no `mypy.ini` / `pyproject.toml` / `setup.cfg` with a
`[mypy]` section in the repo. Type checking is apparently being run ad hoc
rather than as a repeatable, configured step (and isn't enforced in CI,
since there's no CI config either).

### 5. Loose ends
- `services/quiver.py` has three identical `# TODO: verify — Feldnamen der
  Quiver API prüfen` comments (lines 222, 285, 372) — flags that the Quiver
  field-mapping was never confirmed against real API responses.
- `data/streamlit_charts_old.py.txt` is leftover from the pre-FastAPI
  Streamlit version. Harmless, but dead weight in the repo.
- No CI workflow (`.github/workflows/`) — tests and type-checking, such as
  they are, only run when you remember to run them locally.

## Suggested Priority Order

1. Add coverage for the position/risk/scoring engines — this is the one
   category of bug that costs real money.
2. Introduce `logging` + narrow the broad `except Exception`/bare `except`
   blocks, at minimum in the scheduler and data-fetch paths, so failures are
   visible instead of silent.
3. Resolve the `scoring.py` / `scoring_engine_v2.py` duplication one way or
   the other.
4. Formalize the mypy config and (optionally) add a minimal CI workflow that
   runs it plus the test suite on push.
5. Clear the three Quiver TODOs and drop the leftover Streamlit file.

## Not Reviewed

This pass covered structure, cross-cutting patterns (error handling, caching,
testing, typing), and file-level sizing/duplication signals — it did not
review business-logic correctness inside individual services (e.g. whether
the SMC liquidity-sweep detection or the sector-adaptive quant models are
computing the right thing). That would need a targeted review per module.
