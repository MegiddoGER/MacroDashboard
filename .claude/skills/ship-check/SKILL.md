---
name: ship-check
description: What "done" means for a Python change in MacroDashboard — the test, typecheck and route-smoke commands, plus the layering and convention assertions to verify before declaring a change finished. Use before finishing any edit under routers/, services/, models/, snapshot_engine/, database.py or main.py.
---

# Ship check

There is no CI, no `pyproject.toml` and no `mypy.ini` in this repo. Nothing runs unless it
is run deliberately, so "done" has to be an explicit procedure. This is it. Run the parts
that apply to what you touched — all of them, not the convenient ones.

## 1. Tests

```
py -m pytest -q
py -m pytest tests/test_position_management.py -k test_long_target_reached   # einzeln
```

If you changed a calculation engine and wrote no test, the change is not done — see the
`quant-testing` skill. Every argument to those engines is a number someone trades on.

## 2. Typecheck (ad hoc, per file)

```
py -m mypy services/portfolio.py services/risk.py
```

Deliberately per-file: there is **no mypy config committed**, only a stale `.mypy_cache/`
from previous ad hoc runs. A repo-wide `py -m mypy .` will bury you in pre-existing errors
from untouched modules. Check the files you changed. Do not add a config as a side effect of
an unrelated change.

## 3. Route smoke test

The fastest proof the app still renders — no server, no browser:

```
py -c "import warnings; warnings.filterwarnings('ignore'); from fastapi.testclient import TestClient; import main; c=TestClient(main.app); c.__enter__(); [print(c.get(u).status_code, u) for u in ['/','/signals','/signals/indikatoren','/analysis','/screener','/watchlist','/journal','/backtesting','/sectors','/economy','/settings','/lexicon','/sources','/directory']]"
```

Every route must return 200. Run this after any change to `main.py`, a router, a template,
or CSS. For a real interactive check: `py -m uvicorn main:app --reload --port 8501`.

Note this starts the app for real, which boots the APScheduler snapshot job via `main.py`'s
lifespan and touches the ~279 MB SQLite DB. That is normal and safe; the DB is WAL-mode.

## 4. Convention assertions

Check these against your diff before declaring done. Each maps to a rule the codebase
actually holds to.

- **Routers stay thin.** Parse request → call a service → render a template or HTMX
  partial. No DB session, no business logic, no calculation in `routers/`.
- **Services do not touch the DB directly** except through `models/` and `database.py`.
- **No `os.environ` outside `config.py`.** All external configuration goes through
  [config.py](config.py) — a module-level constant for plain values, `config.get_api_token(key)`
  for secrets (DB-first, so the `/settings` UI overrides `.env` without a restart). New
  variables get documented in `.env.example`, which covers *every* external API including
  the keyless ones. Keep that property.
- **No external fetch without a cache wrapper.** New outbound data calls get a `cached_*`
  wrapper in [services/cache_core.py](services/cache_core.py) with a deliberate maxsize and
  TTL. Never cache ad hoc inside a service or router.
- **No new `print()`, no new bare `except:`, no new silent `except: pass`** on a data path —
  see the `observability` skill.
- **German comments and commit messages.** Existing modules are German; keep it.

## 5. The two-`WatchlistItem` trap

`database.py` defines an ORM `WatchlistItem`; `models/watchlist.py` defines a plain
dataclass of the same name. They are different types. When tracing a bug or writing a type
hint, check which module the name was imported from before assuming its fields.

Same care applies to the scoring engines: [services/scoring.py](services/scoring.py) (the
1,354-line legacy monolith that `routers/analysis.py` actually calls) and
[services/scoring_engine_v2.py](services/scoring_engine_v2.py) coexist, and it is not
settled which is authoritative per surface. Check what the call site imports. **Changing one
does not change the other** — if a fix belongs in both, do both, and say so.

## 6. Report honestly

If a test fails, say so and paste the output. If you skipped the smoke test, say which
routes went unverified. A change reported as done that was never run is worse than one
reported as untested.
