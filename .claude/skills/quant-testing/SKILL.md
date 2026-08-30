---
name: quant-testing
description: How to write tests for MacroDashboard's calculation engines — stop/target validation, position metrics, scoring, risk, P&L, backtesting. Covers the golden-scenario style used in tests/test_position_management.py and the mandatory edge-case matrix (LONG/SHORT symmetry, percent-vs-decimal units, NaN propagation, look-ahead bias). Use when adding or reviewing tests for anything that computes a number a trading decision rests on.
---

# Testing the money math

This app computes stop-losses, position sizing, drawdown and portfolio P&L — numbers its
owner acts on financially. A silent miscalculation here is the costliest bug class in the
codebase, and it is the one class that type checking and general code review both miss,
because the code is perfectly valid and simply wrong.

Coverage today is one file, [tests/test_position_management.py](tests/test_position_management.py),
covering the v2 position pipeline. Uncovered and high-value, in priority order:
`trailing_stop_engine.py`, `position_metrics_engine.py`, `position_state_engine.py`,
`target_stop_validator.py`, `scoring_engine_v2.py`, then `risk.py`, `portfolio.py`,
`backtesting.py`.

## Style: golden scenarios, not mocks

Follow the existing file. These engines are pure functions over plain floats and enums —
they need no fixtures, no DB, no network. That is the whole reason they are testable, so do
not introduce mocking machinery.

```python
def test_long_target_reached():
    """1. LONG: currentPrice > takeProfit -> TARGET_REACHED"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=120.0,
        entry_price=100.0,
        take_profit=110.0,
        active_stop=90.0,
        previous_stop=None,
        initial_stop=90.0,
    )
    assert val.target_status == TargetStatus.TARGET_REACHED
    assert val.active_take_profit is None
    assert any(e.rule_id == "LONG_TARGET_ALREADY_REACHED" for e in val.triggered_rules)
```

What to copy from it:

- **Every argument keyword-named and explicit.** A positional `90.0` in a stop calculation
  is unreadable and hides argument-order bugs — which is exactly a bug class here.
- **A docstring naming the scenario in words**, German or English, matching the file.
- **Assert the enum outcome *and* the `rule_id`.** Asserting only the enum passes when the
  right answer was reached through the wrong rule.
- **Real numbers from real situations.** `test_abea_special_case` uses actual ABEA prices.
  A scenario that once produced a wrong answer belongs in the suite permanently.

Add tests to the existing file when they extend the position pipeline; create
`tests/test_<module>.py` for a new engine.

## The mandatory edge-case matrix

For any engine that returns a number or a state, cover all of these. Missing one is how
these bugs ship.

### 1. LONG/SHORT symmetry — the single highest-yield check
Every LONG case gets a mirrored SHORT case. Nearly all sign bugs live here: a stop that
must sit *below* entry for LONG must sit *above* it for SHORT, and profit is
`current - entry` for one and `entry - current` for the other. Ratchet direction inverts
too — [services/trailing_stop_engine.py](services/trailing_stop_engine.py) states the rule
explicitly: a new stop may never fall below the previous one (Long) / rise above it (Short).

### 2. Percent vs decimal
Is `5%` passed as `5.0` or `0.05`? Mixing them across a call boundary produces a number
100× off that still renders plausibly on some scale. Assert the exact expected value, never
just a sign or a range — a range assertion is what lets a 100× error through.

### 3. Missing data: `None` and `NaN`
`_safe()` in `trailing_stop_engine.py` exists precisely because NaN and Infinity leak in
from yfinance. Test that `None` in gives `None` out — **not `0.0`**. A missing stop rendered
as `0.00` reads as "no risk" instead of "unknown", which is the dangerous direction.

### 4. Boundaries
`current_price == take_profit` exactly. `current_price == stop`. Zero price. Negative price.
Zero quantity (division by zero in any average-cost or percent calculation).

### 5. Gap-through
Price gaps past the stop instead of touching it: `current_price` far below a LONG stop. The
result must be "stop was breached", not a computation against an intact stop.

### 6. No look-ahead
For [snapshot_engine/](snapshot_engine/) and
[services/backtesting.py](services/backtesting.py): a calculation dated *T* may only read
data available at *T*. Test by constructing a series whose post-*T* values are absurd — if
the result at *T* changes when you alter *T+1*, there is look-ahead, and every backtest
number the app has ever shown is optimistic.

## Running them

```
py -m pytest -q                                          # ganze Suite
py -m pytest tests/test_position_management.py -k test_long_target_reached
```

A new test must fail before the fix and pass after it. A test written against current
behaviour, without checking that the behaviour is *right*, just freezes the bug in place.
