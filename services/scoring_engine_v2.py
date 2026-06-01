"""
services/scoring_engine_v2.py — Multi-Score Breakdown (12 Teilscores).

Jeder Teilscore: 0–100, mit Ampelfarbe.
Overall Score darf harte Validierungsfehler NICHT verstecken.
"""

from __future__ import annotations

from typing import Optional

from services.position_types import (
    PositionSide, TargetStatus, StopStatus, Severity,
    ValidationResult, PositionMetrics, ScoreBreakdown,
)


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def calc_position_scores(
    signals: dict,
    position_data: dict,
    validation: ValidationResult,
    metrics: PositionMetrics,
    dcf_data: Optional[dict] = None,
    balance_data: Optional[dict] = None,
) -> ScoreBreakdown:
    """Berechnet 12 Teilscores basierend auf Signalen, Validierung und Metriken.

    Args:
        signals: Signale aus calc_full_score() ScoreResult.signals
        position_data: Positionsdaten (pnl_pct, holding_days, etc.)
        validation: Ergebnis der Target/Stop-Validierung
        metrics: Berechnete Positionsmetriken
        dcf_data: DCF-Bewertungsdaten (optional)
        balance_data: Bilanzdaten (optional)

    Returns:
        ScoreBreakdown mit 12 Teilscores + Overall
    """
    s = ScoreBreakdown()

    # ── 1. TrendHealthScore ──────────────────────────────────────
    trend_score = 50.0
    if signals.get("trend_macro_bullish"):
        trend_score += 20
    else:
        trend_score -= 20

    if signals.get("cross_bullish"):
        trend_score += 15
    elif signals.get("cross_bearish"):
        trend_score -= 15

    adx_val = signals.get("adx_val")
    if adx_val and adx_val > 25:
        trend_score += 10
    elif adx_val and adx_val < 20:
        trend_score -= 5

    # Kurs vs SMAs
    current = signals.get("current_price", position_data.get("current_price", 0))
    sma20 = signals.get("sma20_val")
    sma50 = signals.get("sma50_val")
    sma200 = signals.get("sma200_val")

    if current and sma20 and current > sma20:
        trend_score += 5
    elif current and sma20 and current < sma20:
        trend_score -= 5

    s.trend_health = _clamp(trend_score)

    # ── 2. MomentumScore ─────────────────────────────────────────
    mom_score = 50.0
    if signals.get("macd_bullish"):
        mom_score += 15
    elif signals.get("macd_bearish"):
        mom_score -= 15

    rsi_val = signals.get("rsi_val")
    if rsi_val:
        if rsi_val > 70:
            mom_score -= 10  # Überkauft
        elif rsi_val < 30:
            mom_score += 10  # Überverkauft (Rebound-Chance)
        elif rsi_val > 50:
            mom_score += 5
        else:
            mom_score -= 5

    boll = signals.get("bollinger_state", "Neutral")
    if boll == "Am oberen Band":
        mom_score -= 10
    elif boll == "Am unteren Band":
        mom_score += 10

    s.momentum = _clamp(mom_score)

    # ── 3. VolumeStructureScore ──────────────────────────────────
    vol_score = 50.0
    if signals.get("obv_bullish"):
        vol_score += 20
    elif signals.get("obv_bullish") is not None:
        vol_score -= 20

    if signals.get("vwap_bullish"):
        vol_score += 15
    elif signals.get("vwap_bullish") is not None:
        vol_score -= 15

    if signals.get("poc_bullish"):
        vol_score += 10
    elif signals.get("poc_bullish") is not None:
        vol_score -= 10

    s.volume_structure = _clamp(vol_score)

    # ── 4. RelativeStrengthScore ─────────────────────────────────
    # Requires benchmark data — often not available
    s.relative_strength = None  # DataQuality note added below

    # ── 5. ValuationScore ────────────────────────────────────────
    if dcf_data:
        val_score = 50.0
        upside = dcf_data.get("upside_pct", 0)
        if upside > 30:
            val_score = 85
        elif upside > 10:
            val_score = 70
        elif upside > -10:
            val_score = 50
        elif upside > -30:
            val_score = 30
        else:
            val_score = 15
        s.valuation = _clamp(val_score)
    else:
        s.valuation = None

    # ── 6. BalanceSheetScore ─────────────────────────────────────
    if balance_data:
        bal_score = 50.0
        bs_score = balance_data.get("score", 0)
        if bs_score >= 3:
            bal_score = 85
        elif bs_score >= 2:
            bal_score = 70
        elif bs_score >= 0:
            bal_score = 50
        elif bs_score >= -1:
            bal_score = 30
        else:
            bal_score = 15
        s.balance_sheet = _clamp(bal_score)
    else:
        s.balance_sheet = None

    # ── 7. QualityProfitabilityScore ─────────────────────────────
    # Requires profitability data — use what's available
    s.quality_profitability = None

    # ── 8. SentimentScore ────────────────────────────────────────
    sent_avg = signals.get("sentiment_avg")
    if sent_avg is not None:
        sent_score = 50.0 + sent_avg * 100  # avg_compound ∈ [-1, 1]
        s.sentiment = _clamp(sent_score)
    else:
        s.sentiment = None

    # ── 9. RiskManagementScore ───────────────────────────────────
    risk_score = 50.0

    if validation.stop_status == StopStatus.ACTIVE:
        risk_score += 15
    elif validation.stop_status == StopStatus.NO_STOP:
        risk_score -= 20
    elif validation.stop_status == StopStatus.STOP_BREACHED:
        risk_score -= 40

    if validation.stop_locks_profit:
        risk_score += 15

    if metrics.secured_profit_ratio is not None:
        if metrics.secured_profit_ratio > 0.66:
            risk_score += 10
        elif metrics.secured_profit_ratio > 0.33:
            risk_score += 5

    if metrics.r_multiple is not None:
        if metrics.r_multiple > 3:
            risk_score += 10
        elif metrics.r_multiple > 1:
            risk_score += 5
        elif metrics.r_multiple < 0:
            risk_score -= 10

    if metrics.profit_giveback_ratio is not None:
        if metrics.profit_giveback_ratio > 0.75:
            risk_score -= 20
        elif metrics.profit_giveback_ratio > 0.5:
            risk_score -= 10

    s.risk_management = _clamp(risk_score)

    # ── 10. TargetQualityScore ───────────────────────────────────
    target_score = 50.0

    if validation.target_status == TargetStatus.TARGET_REACHED:
        # CRITICAL: Target already reached — score must be low
        target_score = 15.0
    elif validation.target_status == TargetStatus.ACTIVE:
        target_score = 75.0
        if metrics.remaining_reward_risk is not None:
            if metrics.remaining_reward_risk > 2:
                target_score = 85
            elif metrics.remaining_reward_risk < 0.5:
                target_score = 40
    elif validation.target_status == TargetStatus.NO_TARGET:
        target_score = 35.0

    s.target_quality = _clamp(target_score)

    # ── 11. EventRiskScore ───────────────────────────────────────
    # Requires event data — basic implementation
    s.event_risk = None  # Will be enhanced when earnings data is available

    # ── 12. DataQualityScore ─────────────────────────────────────
    dq_score = 100.0
    missing = 0
    if metrics.r_multiple is None:
        dq_score -= 10
        missing += 1
    if validation.stop_status == StopStatus.NO_STOP:
        dq_score -= 10
        missing += 1
    if validation.target_status == TargetStatus.NO_TARGET:
        dq_score -= 5
        missing += 1
    if metrics.drawdown_from_high is None:
        dq_score -= 5
        missing += 1
    if metrics.profit_giveback_ratio is None:
        dq_score -= 5
        missing += 1
    if s.valuation is None:
        dq_score -= 10
        missing += 1
    if s.balance_sheet is None:
        dq_score -= 5
        missing += 1
    if s.sentiment is None:
        dq_score -= 5
        missing += 1
    if s.relative_strength is None:
        dq_score -= 5
        missing += 1

    s.data_quality = _clamp(dq_score)

    # ── Overall Score ────────────────────────────────────────────
    # Gewichteter Durchschnitt der verfügbaren Scores
    weights_and_scores = [
        (0.20, s.trend_health),
        (0.10, s.momentum),
        (0.10, s.volume_structure),
        (0.05, s.relative_strength),
        (0.10, s.valuation),
        (0.05, s.balance_sheet),
        (0.05, s.quality_profitability),
        (0.05, s.sentiment),
        (0.15, s.risk_management),
        (0.10, s.target_quality),
        (0.03, s.event_risk),
        (0.02, s.data_quality),
    ]

    total_weight = 0.0
    weighted_sum = 0.0
    for weight, score in weights_and_scores:
        if score is not None:
            weighted_sum += weight * score
            total_weight += weight

    if total_weight > 0:
        s.overall = _clamp(weighted_sum / total_weight)
    else:
        s.overall = None

    # ── Critical Warning Flag ────────────────────────────────────
    # Overall Score darf harte Validierungsfehler NICHT verstecken
    if validation.has_errors or validation.has_critical_warnings:
        s.has_critical_warning = True
    if validation.target_status == TargetStatus.TARGET_REACHED:
        s.has_critical_warning = True
    if validation.stop_status == StopStatus.STOP_BREACHED:
        s.has_critical_warning = True

    return s
