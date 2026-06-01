import pytest

from services.position_types import (
    PositionSide, TargetStatus, StopStatus, AnalysisMode, RecommendationType
)
from services.target_stop_validator import validate_target_stop
from services.position_state_engine import determine_position_state
from services.position_metrics_engine import calc_position_metrics
from services.scoring_engine_v2 import calc_position_scores
from services.recommendation_engine import generate_recommendation
from services.data_quality_engine import assess_data_quality


def test_long_target_reached():
    """1. LONG: currentPrice > takeProfit -> TARGET_REACHED"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=120.0,
        entry_price=100.0,
        take_profit=110.0,
        active_stop=90.0,
        previous_stop=None,
        initial_stop=90.0
    )
    assert val.target_status == TargetStatus.TARGET_REACHED
    assert val.active_take_profit is None
    assert val.profit_protection_mode is True
    assert any(e.rule_id == "LONG_TARGET_ALREADY_REACHED" for e in val.triggered_rules)


def test_abea_special_case():
    """2. LONG: ABEA-Spezialfall (324.05 vs 292.75)"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=324.05,
        entry_price=275.05,
        take_profit=292.75,
        active_stop=280.0,
        previous_stop=None,
        initial_stop=260.0
    )
    assert val.target_status == TargetStatus.TARGET_REACHED
    assert val.active_take_profit is None
    
    # State Engine
    metrics = calc_position_metrics(
        side=PositionSide.LONG,
        entry_price=275.05,
        current_price=324.05,
        quantity=10,
        active_stop=val.active_stop,
        active_take_profit=val.active_take_profit,
        original_take_profit=292.75
    )
    state = determine_position_state(
        side=PositionSide.LONG,
        pnl_pct=metrics.unrealized_pnl_pct * 100,
        validation=val,
        signals={"trend_macro_bullish": True},
        current_price=324.05
    )
    
    assert state.mode == AnalysisMode.TARGET_REACHED_REVIEW
    
    # Recommendation
    rec = generate_recommendation(
        mode=state.mode,
        state=state,
        validation=val,
        metrics=metrics,
        scores=calc_position_scores({}, {}, val, metrics),
        signals={"trend_macro_bullish": True},
        stop_proposals=[],
        data_quality=assess_data_quality({}, {}),
        side=PositionSide.LONG,
        current_price=324.05,
        entry_price=275.05,
        original_take_profit=292.75
    )
    
    assert rec.primary == RecommendationType.HOLD_WITH_TRAILING_STOP
    assert "Take-Profit unter aktuellem Kurs als aktives Ziel setzen" in rec.forbidden_actions


def test_long_stop_breached():
    """3. LONG: currentPrice <= activeStop -> STOP_BREACHED"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=85.0,
        entry_price=100.0,
        take_profit=120.0,
        active_stop=90.0,
        previous_stop=None,
        initial_stop=90.0
    )
    assert val.stop_status == StopStatus.STOP_BREACHED
    assert any(e.rule_id == "LONG_STOP_BREACHED" for e in val.triggered_rules)


def test_long_stop_locks_profit():
    """4. LONG: suggestedStop > entryPrice -> stopLocksProfit"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=120.0,
        entry_price=100.0,
        take_profit=130.0,
        active_stop=110.0,
        previous_stop=None,
        initial_stop=90.0
    )
    assert val.stop_status == StopStatus.ACTIVE
    assert val.stop_locks_profit is True


def test_long_stop_loosened_error():
    """5. LONG: previousActiveStop > neuer Stop -> ValidationError"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=120.0,
        entry_price=100.0,
        take_profit=130.0,
        active_stop=105.0,
        previous_stop=110.0,
        initial_stop=90.0
    )
    assert val.has_errors
    assert any(e.rule_id == "LONG_STOP_LOOSENED" for e in val.errors)


def test_short_target_reached():
    """6. SHORT: currentPrice < takeProfit -> TARGET_REACHED"""
    val = validate_target_stop(
        side=PositionSide.SHORT,
        current_price=80.0,
        entry_price=100.0,
        take_profit=90.0,
        active_stop=110.0,
        previous_stop=None,
        initial_stop=110.0
    )
    assert val.target_status == TargetStatus.TARGET_REACHED
    assert val.active_take_profit is None
    assert any(e.rule_id == "SHORT_TARGET_ALREADY_REACHED" for e in val.triggered_rules)


def test_short_stop_loosened_error():
    """7. SHORT: previousActiveStop < neuer Stop -> ValidationError"""
    val = validate_target_stop(
        side=PositionSide.SHORT,
        current_price=90.0,
        entry_price=100.0,
        take_profit=80.0,
        active_stop=105.0,
        previous_stop=102.0,
        initial_stop=110.0
    )
    assert val.has_errors
    assert any(e.rule_id == "SHORT_STOP_LOOSENED" for e in val.errors)


def test_missing_initial_stop():
    """8. Fehlender initialStop -> R-Multiple null, DataQuality reduziert"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=110.0,
        entry_price=100.0,
        take_profit=120.0,
        active_stop=90.0,
        previous_stop=None,
        initial_stop=None
    )
    metrics = calc_position_metrics(
        side=PositionSide.LONG,
        entry_price=100.0,
        current_price=110.0,
        quantity=10,
        active_stop=90.0,
        active_take_profit=120.0,
        initial_stop=None
    )
    assert metrics.r_multiple is None
    
    dq = assess_data_quality({}, {})
    assert dq.score < 100
    assert "Kaufkurs" in dq.missing_fields # As the mock is empty


def test_missing_active_stop():
    """9. Fehlender activeStop -> RiskManagementScore reduziert"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=110.0,
        entry_price=100.0,
        take_profit=120.0,
        active_stop=None,
        previous_stop=None,
        initial_stop=90.0
    )
    assert val.stop_status == StopStatus.NO_STOP
    
    metrics = calc_position_metrics(
        side=PositionSide.LONG,
        entry_price=100.0,
        current_price=110.0,
        quantity=10,
        active_stop=None,
        active_take_profit=120.0,
        initial_stop=90.0
    )
    
    scores = calc_position_scores({}, {}, val, metrics)
    assert scores.risk_management < 50


def test_dcf_warning_trend_strong():
    """10. DCF unter Kurs + Trend stark -> Warnung, kein SELL"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=100.0,
        entry_price=90.0,
        take_profit=120.0,
        active_stop=80.0
    )
    metrics = calc_position_metrics(PositionSide.LONG, 90.0, 100.0, 10, active_stop=80.0, active_take_profit=120.0)
    scores = calc_position_scores(
        {"trend_macro_bullish": True}, 
        {}, val, metrics, 
        dcf_data={"upside_pct": -30.0}
    )
    assert scores.valuation <= 30
    
    state = determine_position_state(PositionSide.LONG, 11.0, val, {"trend_macro_bullish": True})
    
    dq = assess_data_quality({}, {})
    rec = generate_recommendation(
        state.mode, state, val, metrics, scores, 
        {"trend_macro_bullish": True, "dcf_upside": -30.0},
        [], dq
    )
    assert "DCF zeigt starkes Bewertungsrisiko" in rec.warnings
    # Should be HOLD or NORMAL_HOLD since it's not reached target or stop, but has warnings maybe
    assert rec.primary in (RecommendationType.NORMAL_HOLD, RecommendationType.HOLD_WITH_TRAILING_STOP)


def test_profit_protection_momentum():
    """11. MACD bearish + OBV falling + Target reached -> Profit Protection"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=120.0,
        entry_price=100.0,
        take_profit=110.0, # Target reached
        active_stop=105.0
    )
    metrics = calc_position_metrics(PositionSide.LONG, 100.0, 120.0, 10)
    signals = {"macd_bearish": True, "obv_bullish": False, "trend_macro_bullish": True}
    
    state = determine_position_state(PositionSide.LONG, 20.0, val, signals)
    scores = calc_position_scores(signals, {}, val, metrics)
    dq = assess_data_quality({}, {})
    
    rec = generate_recommendation(
        state.mode, state, val, metrics, scores, signals, [], dq,
        original_take_profit=110.0
    )
    
    assert state.mode == AnalysisMode.TARGET_REACHED_REVIEW
    assert rec.primary == RecommendationType.HOLD_WITH_TRAILING_STOP
    assert "MACD bearish" in rec.warnings
    assert "OBV fallend" in rec.warnings


def test_short_term_weakness():
    """12. Kurs unter SMA20, über SMA50/200 -> kurzfristige Schwäche, kein Exit"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=110.0,
        entry_price=100.0,
        take_profit=130.0,
        active_stop=90.0
    )
    signals = {
        "current_price": 110.0,
        "sma20_val": 115.0,
        "sma50_val": 105.0,
        "sma200_val": 95.0,
        "trend_macro_bullish": True
    }
    state = determine_position_state(PositionSide.LONG, 10.0, val, signals)
    
    # 1 warning (Kurs < SMA20) -> should still be NORMAL_HOLD
    assert state.mode == AnalysisMode.NORMAL_HOLD
    assert state.technical_warning_score == 1


def test_low_data_quality():
    """13. DataQualityScore niedrig -> Confidence reduziert"""
    pos_data = {"buy_price": 100.0, "current_price": 110.0} # missing quantity, stop_loss, etc.
    dq = assess_data_quality(pos_data, {})
    assert dq.score < 80
    assert dq.confidence_modifier < 1.0


def test_profit_giveback():
    """14. ProfitGivebackRatio > 0.5 -> Review Trigger"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=110.0,
        entry_price=100.0,
        take_profit=150.0,
        active_stop=105.0
    )
    # High was 130. Giveback: (130-110) / (130-100) = 20 / 30 = 0.66
    metrics = calc_position_metrics(
        PositionSide.LONG, 100.0, 110.0, 10,
        active_stop=105.0, active_take_profit=150.0,
        high_since_entry=130.0
    )
    assert metrics.profit_giveback_ratio > 0.5
    
    scores = calc_position_scores({}, {}, val, metrics)
    state = determine_position_state(PositionSide.LONG, 10.0, val, {})
    dq = assess_data_quality({}, {})
    
    rec = generate_recommendation(state.mode, state, val, metrics, scores, {}, [], dq)
    assert "ProfitGivebackRatio über 50%" in rec.review_triggers


def test_target_quality_red_overall_good():
    """17. TargetQuality rot + Overall gut -> UI zeigt Warnung"""
    val = validate_target_stop(
        side=PositionSide.LONG,
        current_price=130.0,
        entry_price=100.0,
        take_profit=120.0, # Target reached
        active_stop=110.0
    )
    metrics = calc_position_metrics(PositionSide.LONG, 100.0, 130.0, 10, active_stop=110.0)
    scores = calc_position_scores({"trend_macro_bullish": True, "obv_bullish": True}, {}, val, metrics)
    
    assert val.target_status == TargetStatus.TARGET_REACHED
    assert scores.target_quality < 50
    assert scores.overall > 50  # Overal may be good due to trend/momentum
    assert scores.has_critical_warning is True # Because target reached is a hard validation event

