"""
services/position_state_engine.py — Bestimmt den Positionszustand.

Erkennt den aktuellen Zustand einer Position basierend auf:
- Validierungsergebnis (Target/Stop Status)
- P&L und Positionsseite
- Warning Scores (technisch/fundamental)
- Datenverfügbarkeit
"""

from __future__ import annotations

from typing import Optional

from services.position_types import (
    PositionSide, AnalysisMode, PositionState,
    TargetStatus, StopStatus, RiskStatus, ThesisStatus,
    ValidationResult,
)


def determine_analysis_mode(
    has_position: bool,
    side: PositionSide = PositionSide.LONG,
    pnl_pct: float = 0.0,
    validation: ValidationResult | None = None,
) -> AnalysisMode:
    """Bestimmt den Analysemodus basierend auf Positionsdaten.

    Args:
        has_position: Ob eine bestehende Position existiert
        side: LONG oder SHORT
        pnl_pct: Unrealisiertes P&L in Prozent
        validation: Validierungsergebnis

    Returns:
        AnalysisMode
    """
    if not has_position:
        return AnalysisMode.NEW_ENTRY

    if side == PositionSide.LONG:
        base_mode = AnalysisMode.EXISTING_LONG
    else:
        base_mode = AnalysisMode.EXISTING_SHORT

    # Validierungs-basierte Modus-Eskalation
    if validation:
        if validation.stop_status == StopStatus.STOP_BREACHED:
            return AnalysisMode.EXIT_REVIEW
        if validation.target_status == TargetStatus.TARGET_REACHED:
            return AnalysisMode.TARGET_REACHED_REVIEW

    # P&L-basierte Modus-Differenzierung
    if pnl_pct < -15:
        return AnalysisMode.LOSS_POSITION

    return base_mode


def determine_position_state(
    side: PositionSide,
    pnl_pct: float,
    validation: ValidationResult,
    signals: dict,
    atr_val: Optional[float] = None,
    current_price: Optional[float] = None,
    active_stop: Optional[float] = None,
) -> PositionState:
    """Bestimmt den vollständigen Positionszustand.

    Kombiniert Validierungsergebnis, Signale und Warning-Scores
    zu einem konsistenten State-Objekt.

    Args:
        side: LONG oder SHORT
        pnl_pct: Unrealisiertes P&L in %
        validation: Validierungsergebnis
        signals: Signale aus der Scoring-Engine
        atr_val: ATR-Wert (optional)
        current_price: Aktueller Kurs (optional)
        active_stop: Aktiver Stop (optional)

    Returns:
        PositionState
    """
    state = PositionState()

    # ── Target und Stop Status direkt aus Validierung ─────────────
    state.target_status = validation.target_status
    state.stop_status = validation.stop_status
    state.profit_protection_mode = validation.profit_protection_mode

    # ── Technical Warning Score ───────────────────────────────────
    tech_warnings = 0

    macd_bearish = signals.get("macd_bearish", False)
    obv_bullish = signals.get("obv_bullish", False)
    vwap_bullish = signals.get("vwap_bullish", False)
    trend_macro_bullish = signals.get("trend_macro_bullish", False)
    cross_bullish = signals.get("cross_bullish", False)
    sma20_val = signals.get("sma20_val")
    sma50_val = signals.get("sma50_val")
    sma200_val = signals.get("sma200_val")
    current = signals.get("current_price", current_price)

    if macd_bearish:
        tech_warnings += 1
    if not obv_bullish and signals.get("obv_bullish") is not None:
        tech_warnings += 1
    if not vwap_bullish and signals.get("vwap_bullish") is not None:
        tech_warnings += 1
    if current and sma20_val and current < sma20_val:
        tech_warnings += 1
    if current and sma50_val and current < sma50_val:
        tech_warnings += 2
    if current and sma200_val and current < sma200_val:
        tech_warnings += 3

    state.technical_warning_score = tech_warnings

    # ── Fundamental Warning Score (aus verfügbaren Signalen) ──────
    fund_warnings = 0
    # DCF Überbewertung (signals might contain dcf_upside)
    # We don't have this directly — will be set by scoring_engine_v2
    state.fundamental_warning_score = fund_warnings

    # ── Mode bestimmen ────────────────────────────────────────────
    if validation.stop_status == StopStatus.STOP_BREACHED:
        state.mode = AnalysisMode.EXIT_REVIEW
        state.risk_status = RiskStatus.CRITICAL
    elif validation.target_status == TargetStatus.TARGET_REACHED:
        state.mode = AnalysisMode.TARGET_REACHED_REVIEW
        state.profit_protection_mode = True
        state.risk_status = RiskStatus.ELEVATED_BUT_CONTROLLED
    elif pnl_pct < -15:
        state.mode = AnalysisMode.LOSS_POSITION
        state.risk_status = RiskStatus.HIGH
    elif tech_warnings >= 5:
        state.mode = AnalysisMode.EXIT_REVIEW
        state.risk_status = RiskStatus.HIGH
    elif tech_warnings >= 3:
        state.mode = AnalysisMode.PROFIT_PROTECTION_MODE
        state.profit_protection_mode = True
        state.risk_status = RiskStatus.ELEVATED
    elif tech_warnings == 2:
        state.mode = AnalysisMode.NORMAL_HOLD  # Watchlist-equivalent
        state.risk_status = RiskStatus.ELEVATED_BUT_CONTROLLED
    elif pnl_pct > 0 and tech_warnings <= 1:
        state.mode = AnalysisMode.NORMAL_HOLD
        state.risk_status = RiskStatus.CONTROLLED
    else:
        state.mode = AnalysisMode.NORMAL_HOLD
        state.risk_status = RiskStatus.CONTROLLED

    # ── Thesis Status ─────────────────────────────────────────────
    if tech_warnings >= 5 or fund_warnings >= 2:
        state.thesis_status = ThesisStatus.REVIEW_NEEDED
    elif tech_warnings >= 3 or fund_warnings >= 1:
        state.thesis_status = ThesisStatus.WEAKENING
    elif not trend_macro_bullish and side == PositionSide.LONG:
        state.thesis_status = ThesisStatus.WEAKENING
    else:
        state.thesis_status = ThesisStatus.INTACT

    return state
