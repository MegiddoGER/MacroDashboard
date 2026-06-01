"""
services/position_metrics_engine.py — Berechnung aller Positionsmetriken.

Alle Formeln mit NaN/Infinity-Guards und None-Handling.
Fehlende Daten liefern None — keine Fake-Werte.
"""

from __future__ import annotations

import math
from typing import Optional

from services.position_types import PositionSide, PositionMetrics


def _safe(val: Optional[float]) -> Optional[float]:
    """Gibt None zurück bei NaN oder Infinity."""
    if val is None:
        return None
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val


def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """Sichere Division — gibt None bei 0, None, NaN oder Inf zurück."""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    result = numerator / denominator
    return _safe(result)


def calc_position_metrics(
    side: PositionSide,
    entry_price: float,
    current_price: float,
    quantity: float,
    active_stop: Optional[float] = None,
    active_take_profit: Optional[float] = None,
    initial_stop: Optional[float] = None,
    original_take_profit: Optional[float] = None,
    holding_days: int = 0,
    atr_val: Optional[float] = None,
    high_since_entry: Optional[float] = None,
    low_since_entry: Optional[float] = None,
) -> PositionMetrics:
    """Berechnet alle Positionsmetriken.

    Args:
        side: LONG oder SHORT
        entry_price: Einstiegskurs
        current_price: Aktueller Kurs
        quantity: Stückzahl
        active_stop: Aktiver Stop-Loss (nach Validierung, kann None sein)
        active_take_profit: Aktiver Take-Profit (nach Validierung, kann None sein)
        initial_stop: Initialer Stop bei Eröffnung
        original_take_profit: Ursprünglicher TP (auch wenn inzwischen erreicht)
        holding_days: Haltedauer in Tagen
        atr_val: ATR-Wert
        high_since_entry: Höchster Kurs seit Entry (kann None sein)
        low_since_entry: Tiefster Kurs seit Entry (kann None sein)

    Returns:
        PositionMetrics mit allen berechneten Werten (None bei fehlenden Daten)
    """
    m = PositionMetrics()

    # ── P&L ───────────────────────────────────────────────────────
    if side == PositionSide.LONG:
        m.unrealized_pnl = _safe((current_price - entry_price) * quantity)
        m.unrealized_pnl_pct = _safe_div(current_price - entry_price, entry_price)
    else:
        m.unrealized_pnl = _safe((entry_price - current_price) * quantity)
        m.unrealized_pnl_pct = _safe_div(entry_price - current_price, entry_price)

    # ── Investiertes Kapital und aktueller Wert ───────────────────
    m.invested_capital = _safe(entry_price * quantity)
    m.current_value = _safe(current_price * quantity)

    # ── Gesicherter Gewinn bei Stop ──────────────────────────────
    if active_stop is not None:
        if side == PositionSide.LONG:
            m.secured_profit_at_stop = _safe((active_stop - entry_price) * quantity)
            m.secured_profit_pct_at_stop = _safe_div(active_stop - entry_price, entry_price)
            m.stop_locks_profit = active_stop >= entry_price
        else:
            m.secured_profit_at_stop = _safe((entry_price - active_stop) * quantity)
            m.secured_profit_pct_at_stop = _safe_div(entry_price - active_stop, entry_price)
            m.stop_locks_profit = active_stop <= entry_price

    # ── Offenes Risiko bis Stop ──────────────────────────────────
    if active_stop is not None:
        if side == PositionSide.LONG:
            m.open_risk = _safe((current_price - active_stop) * quantity)
        else:
            m.open_risk = _safe((active_stop - current_price) * quantity)
        # Guard: Open Risk muss >= 0 sein (sonst Stop breached)
        if m.open_risk is not None and m.open_risk < 0:
            m.open_risk = 0.0

    # ── R-Multiple ───────────────────────────────────────────────
    if initial_stop is not None:
        if side == PositionSide.LONG:
            initial_risk = entry_price - initial_stop
            if initial_risk > 0:
                m.r_multiple = _safe_div(current_price - entry_price, initial_risk)
        else:
            initial_risk = initial_stop - entry_price
            if initial_risk > 0:
                m.r_multiple = _safe_div(entry_price - current_price, initial_risk)

    # ── Distanz zu Stop und Ziel ─────────────────────────────────
    if active_stop is not None and current_price > 0:
        if side == PositionSide.LONG:
            m.distance_to_stop_pct = _safe_div(current_price - active_stop, current_price)
        else:
            m.distance_to_stop_pct = _safe_div(active_stop - current_price, current_price)

    if active_take_profit is not None and current_price > 0:
        if side == PositionSide.LONG:
            m.distance_to_target_pct = _safe_div(active_take_profit - current_price, current_price)
        else:
            m.distance_to_target_pct = _safe_div(current_price - active_take_profit, current_price)

    # ── Remaining Reward/Risk ────────────────────────────────────
    if active_take_profit is not None and active_stop is not None:
        if side == PositionSide.LONG:
            reward = active_take_profit - current_price
            risk = current_price - active_stop
            if risk > 0:
                m.remaining_reward_risk = _safe_div(reward, risk)
        else:
            reward = current_price - active_take_profit
            risk = active_stop - current_price
            if risk > 0:
                m.remaining_reward_risk = _safe_div(reward, risk)

    # ── Target Exceeded By ───────────────────────────────────────
    if original_take_profit is not None and original_take_profit > 0:
        if side == PositionSide.LONG and current_price >= original_take_profit:
            m.target_exceeded_by_pct = _safe_div(
                current_price - original_take_profit, original_take_profit
            )
        elif side == PositionSide.SHORT and current_price <= original_take_profit:
            m.target_exceeded_by_pct = _safe_div(
                original_take_profit - current_price, original_take_profit
            )

    # ── Position CAGR ────────────────────────────────────────────
    if holding_days > 0 and m.invested_capital and m.invested_capital > 0 and m.current_value:
        try:
            total_return = m.current_value / m.invested_capital
            if total_return > 0:
                m.position_cagr = _safe(
                    (total_return ** (365.0 / holding_days)) - 1
                )
        except (ValueError, OverflowError):
            m.position_cagr = None

    # ── Stop Distance ATR ────────────────────────────────────────
    if active_stop is not None and atr_val is not None and atr_val > 0:
        m.stop_distance_atr = _safe_div(abs(current_price - active_stop), atr_val)

    # ── Drawdown seit Entry (benötigt highSinceEntry) ────────────
    if side == PositionSide.LONG and high_since_entry is not None and high_since_entry > 0:
        m.drawdown_from_high = _safe_div(current_price, high_since_entry)
        if m.drawdown_from_high is not None:
            m.drawdown_from_high -= 1.0  # Ergebnis ist negativ bei Drawdown

    elif side == PositionSide.SHORT and low_since_entry is not None and low_since_entry > 0:
        m.drawdown_from_high = _safe_div(current_price, low_since_entry)
        if m.drawdown_from_high is not None:
            m.drawdown_from_high -= 1.0

    # ── Profit Giveback Ratio ────────────────────────────────────
    if side == PositionSide.LONG and high_since_entry is not None:
        if high_since_entry > entry_price:
            m.profit_giveback_ratio = _safe_div(
                high_since_entry - current_price,
                high_since_entry - entry_price,
            )
            if m.profit_giveback_ratio is not None:
                m.profit_giveback_ratio = max(0.0, m.profit_giveback_ratio)

    elif side == PositionSide.SHORT and low_since_entry is not None:
        if entry_price > low_since_entry:
            m.profit_giveback_ratio = _safe_div(
                current_price - low_since_entry,
                entry_price - low_since_entry,
            )
            if m.profit_giveback_ratio is not None:
                m.profit_giveback_ratio = max(0.0, m.profit_giveback_ratio)

    # ── Secured Profit Ratio ─────────────────────────────────────
    if active_stop is not None:
        if side == PositionSide.LONG and current_price > entry_price:
            m.secured_profit_ratio = _safe_div(
                active_stop - entry_price,
                current_price - entry_price,
            )
        elif side == PositionSide.SHORT and current_price < entry_price:
            m.secured_profit_ratio = _safe_div(
                entry_price - active_stop,
                entry_price - current_price,
            )

    return m
