# `.claude/` — the MacroDashboard working environment

Two layers, deliberately separated:

- **Skills** (`.claude/skills/*/SKILL.md`) are *procedures* — how this repo does a thing.
  They load into the main session, cost nothing extra, and keep a multi-file recipe from
  being re-derived (and half-done) each time.
- **Agents** (`.claude/agents/*.md`) are *specialists with their own context*. Reserved for
  independent verification, token-heavy research, and parallel fan-out — not for work the
  main session can already do.

Every file here is written against **this** repository. Do not drop in a generic agent from
a catalogue: the previous `ui-designer` was one, and it opened by demanding a handshake with
a `context-manager` agent that does not exist, which made it unusable until the brief was
rewritten to cancel it out.

## "I want to…"

| Task | Use |
|---|---|
| Finish any Python change — know it actually works | skill **`ship-check`** |
| Add error handling, or replace `print()` with logging | skill **`observability`** |
| Write tests for a calculation engine | skill **`quant-testing`** |
| Wire in a new external API / data feed | skill **`new-data-source`** |
| Add a page, tab, or HTMX fragment | skill **`new-surface`** |
| Do visual/CSS work | skill **`design-brief`** + agent **`ui-designer`** |
| Check a stop/P&L/backtest calculation for domain errors | agent **`quant-reviewer`** |
| Get test coverage onto an engine (one per invocation, parallelizable) | agent **`test-author`** |
| Confirm an API's real field names before trusting a mapping | agent **`data-source-scout`** |
| Find general bugs in a diff | built-in `/code-review` |

`quant-reviewer` and `/code-review` do different jobs. `/code-review` finds bugs in code
that is wrong *as code*; `quant-reviewer` finds code that is valid Python and computes the
wrong number — sign inversions, unit mixing, look-ahead bias. Neither replaces the other.

## What the environment is aimed at

The four recurring gaps from `REVIEW.md`, each with an owner above:

1. **Untested money math** — one test file covers the v2 position pipeline; the risk, P&L
   and stop engines have no coverage. → `quant-testing`, `test-author`
2. **Unverified external data** — `services/quiver.py` still carries three
   `# TODO: verify` field-mapping markers (lines 215, 278, 365). → `data-source-scout`,
   `new-data-source`
3. **Multi-file features landing half-done** — a feed or a page touches 5 files in a fixed
   order. → `new-data-source`, `new-surface`, `ship-check`
4. **Silent failures** — ~190 broad `except Exception` and ad hoc `print()` outside
   `snapshot_engine/`. → `observability`

## Conventions these files enforce

Definitions are in English; the code they produce follows the repo: **German comments and
commit messages**, `routers/` → `services/` → `models/` layering, all environment config
through `config.py`, all external fetches cached through `services/cache_core.py`.

## Deliberately absent

- **No orchestrator / `context-manager` agent.** The main session orchestrates. Adding one
  reproduces the exact failure that made the old `ui-designer` unusable.
- **No agent for one-time migrations** (the `scoring.py` vs `scoring_engine_v2.py`
  untangling, for instance). Those are jobs to run *using* this environment, not members of
  it.
- **No CI, no `pyproject.toml`, no `mypy.ini`.** Worth adding — it is the natural next step,
  and would let `ship-check` become an enforced gate rather than a procedure — but it is
  repo infrastructure, not part of the agent environment.
