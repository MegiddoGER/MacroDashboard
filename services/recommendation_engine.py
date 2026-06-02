"""
services/recommendation_engine.py — Regelbasierte, erklärbare Empfehlung.

Liefert: primary, alternative, confidence, summary, nextActions,
forbiddenActions, warnings, reviewTriggers, dataQualityNotes.

KEINE Anlageberatung — regelbasierte Entscheidungsunterstützung.
"""

from __future__ import annotations

from typing import Optional

from services.position_types import (
    PositionSide, AnalysisMode, TargetStatus, StopStatus,
    RecommendationType, RecommendationResult,
    ValidationResult, PositionMetrics, ScoreBreakdown,
    PositionState, StopProposal, DataQualityResult,
)


def generate_recommendation(
    mode: AnalysisMode,
    state: PositionState,
    validation: ValidationResult,
    metrics: PositionMetrics,
    scores: ScoreBreakdown,
    signals: dict,
    stop_proposals: list[StopProposal],
    data_quality: DataQualityResult,
    side: PositionSide = PositionSide.LONG,
    current_price: float = 0.0,
    entry_price: float = 0.0,
    original_take_profit: Optional[float] = None,
    suggested_stop: Optional[float] = None,
    suggested_take_profit: Optional[float] = None,
    volume_modifier: str = "mittel",
) -> RecommendationResult:
    """Erzeugt eine erklärbare, regelbasierte Empfehlung.

    Die Empfehlung wird aus den Ergebnissen aller vorherigen Engines
    zusammengesetzt. Keine neue Analyse — nur Synthese und Erklärung.

    Returns:
        RecommendationResult mit allen Feldern
    """
    rec = RecommendationResult()
    rec.suggested_optimal_stop = suggested_stop
    rec.suggested_take_profit = suggested_take_profit

    next_actions: list[str] = []
    optional_actions: list[str] = []
    forbidden_actions: list[str] = []
    warnings_list: list[str] = []
    rationale: list[str] = []
    review_triggers: list[str] = []
    dq_notes: list[str] = []

    pnl_pct = (metrics.unrealized_pnl_pct or 0) * 100  # Convert to %
    in_profit = pnl_pct > 0
    trend_intact = signals.get("trend_macro_bullish", False)
    macd_bearish = signals.get("macd_bearish", False)
    obv_falling = not signals.get("obv_bullish", True)

    # ── 1. STOP BREACHED → EXIT ──────────────────────────────────
    if validation.stop_status == StopStatus.STOP_BREACHED:
        rec.primary = RecommendationType.EXIT_REVIEW
        rec.alternative = RecommendationType.EXIT
        rec.status = "STOP_BREACHED"
        rec.confidence = 0.85
        rec.summary = (
            "Der aktive Stop-Loss wurde unterschritten. "
            "Exit-Strategie prüfen — normale HOLD-Empfehlung ist nicht zulässig."
        )
        next_actions.append("Exit-Strategie definieren")
        next_actions.append("Schlusskurs-Bestätigung abwarten oder sofort handeln")
        forbidden_actions.append("Normale HOLD-Empfehlung bei durchbrochenem Stop")
        forbidden_actions.append("Nachkaufen in einen Stop-Bruch")
        warnings_list.append("Stop-Loss unterschritten")
        rationale.append("Der Kurs hat den aktiven Stop-Loss erreicht oder unterschritten.")

    # ── 2. TARGET REACHED → PROFIT PROTECTION ────────────────────
    elif validation.target_status == TargetStatus.TARGET_REACHED:
        rec.primary = RecommendationType.HOLD_WITH_TRAILING_STOP
        rec.alternative = RecommendationType.PARTIAL_TAKE_PROFIT
        rec.status = "PROFIT_PROTECTION_MODE"
        rec.confidence = 0.65

        summary_parts = [
            "Ursprüngliches Kursziel wurde erreicht oder überschritten."
        ]

        if trend_intact:
            summary_parts.append("Der übergeordnete Trend ist intakt.")
            rec.confidence += 0.05
        else:
            summary_parts.append("Der übergeordnete Trend zeigt Schwäche.")
            rec.confidence -= 0.05

        if macd_bearish or obv_falling:
            summary_parts.append("Kurzfristiges Momentum und/oder Volumenstruktur schwächen sich ab.")
            rec.confidence -= 0.05

        summary_parts.append("Gewinnsicherung per Trailing Stop oder Teilgewinnmitnahme prüfen.")
        rec.summary = " ".join(summary_parts)

        # Next Actions
        if original_take_profit:
            next_actions.append(f"Alten Take-Profit {original_take_profit:.2f} EUR deaktivieren")

        if suggested_stop:
            next_actions.append(
                f"Gewinnsichernden Stop bei {suggested_stop:.2f} EUR prüfen"
            )

        next_actions.append("Teilgewinnmitnahme optional, falls Bewertungsrisiko reduziert werden soll")
        next_actions.append("Kein neuer Entry auf aktuellem Niveau")
        next_actions.append("Neues Ziel oberhalb des aktuellen Kurses nur bei bestätigter These berechnen")

        # Forbidden Actions — NICHT VERHANDELBAR
        forbidden_actions.append("Take-Profit unter aktuellem Kurs als aktives Ziel setzen")
        forbidden_actions.append("Halten bis altem Take-Profit")
        forbidden_actions.append("Nachkaufen ohne neues Reward/Risk und neue These")

        # Warnings
        warnings_list.append("Ursprüngliches Kursziel erreicht")
        if macd_bearish:
            warnings_list.append("MACD bearish")
        if obv_falling:
            warnings_list.append("OBV fallend")
        if not signals.get("vwap_bullish", True):
            warnings_list.append("Kurs unter VWMA")

        rationale.append("Das ursprüngliche Kursziel wurde erreicht — der alte Take-Profit ist nicht mehr als aktives Ziel gültig.")
        if trend_intact:
            rationale.append("Der übergeordnete Trend (Kurs > SMA200) ist intakt, was für weiteres Potenzial spricht.")
        rationale.append("Gewinnsicherung hat jetzt Priorität vor Gewinnmaximierung.")

    # ── 3. LOSS POSITION ─────────────────────────────────────────
    elif mode == AnalysisMode.LOSS_POSITION:
        if trend_intact:
            rec.primary = RecommendationType.HOLD_BUT_REDUCE_RISK
            rec.confidence = 0.45
            rec.summary = "Position im Verlust, aber übergeordneter Trend intakt. Stop überprüfen."
        else:
            rec.primary = RecommendationType.LOSS_POSITION_REVIEW
            rec.alternative = RecommendationType.EXIT_REVIEW
            rec.confidence = 0.35
            rec.summary = "Position im deutlichen Verlust und Trend gebrochen. Exit-Strategie prüfen."
            next_actions.append("Exit-Strategie definieren")
            warnings_list.append("Position im Verlust + Trend negativ")
        rec.status = "LOSS_POSITION"

    # ── 4. THESIS REVIEW ─────────────────────────────────────────
    elif mode == AnalysisMode.THESIS_REVIEW:
        rec.primary = RecommendationType.THESIS_REVIEW
        rec.status = "THESIS_REVIEW"
        rec.confidence = 0.40
        rec.summary = "Mehrere Warnsignale aktiv. These und Positionslogik überprüfen."
        next_actions.append("Investmentthese überprüfen")
        next_actions.append("Stop-Loss auf aktuelles Niveau anpassen")

    # ── 5. PROFIT PROTECTION (by warning score) ──────────────────
    elif state.profit_protection_mode and in_profit:
        rec.primary = RecommendationType.PROFIT_PROTECTION_MODE
        rec.alternative = RecommendationType.HOLD_WITH_TRAILING_STOP
        rec.status = "PROFIT_PROTECTION_MODE"
        rec.confidence = 0.55
        rec.summary = "Position im Gewinn, aber erhöhte Warnsignale. Gewinnsicherung prüfen."
        if suggested_stop:
            msg = f"Trailing Stop bei {suggested_stop:.2f} EUR prüfen"
            if suggested_take_profit and not validation.active_take_profit:
                msg += f" (Dazu TP bei {suggested_take_profit:.2f} EUR)"
            next_actions.append(msg)
        next_actions.append("Teilgewinnmitnahme erwägen")

    # ── 6. NORMAL HOLD ───────────────────────────────────────────
    elif in_profit and trend_intact and state.technical_warning_score <= 1:
        rec.primary = RecommendationType.NORMAL_HOLD
        rec.status = "NORMAL_HOLD"
        rec.confidence = 0.70
        rec.summary = (
            "Position im Gewinn, Trend intakt, keine kritischen Warnsignale. "
            "Position halten und regelmäßig überprüfen."
        )
        if suggested_stop:
            msg = f"Stop bei {suggested_stop:.2f} EUR als Absicherung prüfen"
            if suggested_take_profit and not validation.active_take_profit:
                msg += f" (Dazu TP bei {suggested_take_profit:.2f} EUR)"
            next_actions.append(msg)
        rationale.append("Trend intakt, Momentum unterstützt die Position.")

    # ── 7. HOLD WITH TRAILING STOP ───────────────────────────────
    elif in_profit:
        rec.primary = RecommendationType.HOLD_WITH_TRAILING_STOP
        rec.status = "HOLD_WITH_TRAILING_STOP"
        rec.confidence = 0.60
        rec.summary = "Position im Gewinn. Trailing Stop zur Gewinnsicherung empfohlen."
        if suggested_stop:
            msg = f"Trailing Stop bei {suggested_stop:.2f} EUR prüfen"
            if suggested_take_profit and not validation.active_take_profit:
                msg += f" (Dazu TP bei {suggested_take_profit:.2f} EUR)"
            next_actions.append(msg)

    # ── 8. DEFAULT HOLD ──────────────────────────────────────────
    else:
        rec.primary = RecommendationType.HOLD
        rec.status = "HOLD"
        rec.confidence = 0.50
        rec.summary = "Keine klare Handlungsempfehlung. Position beobachten."

    # ── Global Warnings ──────────────────────────────────────────
    dcf_upside = signals.get("dcf_upside")
    if dcf_upside is not None and dcf_upside < -20:
        warnings_list.append("DCF zeigt starkes Bewertungsrisiko")

    cp = signals.get("current_price", current_price)
    sma20 = signals.get("sma20_val")
    if cp and sma20 and cp < sma20:
        warnings_list.append("Kurs unter SMA20 trotz intaktem übergeordnetem Trend")

    # ── Data Quality Adjustments ─────────────────────────────────
    if data_quality.score < 50:
        rec.confidence *= 0.7
        dq_notes.append("Datenqualität eingeschränkt — Confidence reduziert")
        if rec.confidence < 0.3:
            rec.primary = RecommendationType.NO_ACTION_DATA_INSUFFICIENT
            rec.summary = "Unzureichende Datenqualität für eine belastbare Empfehlung."
    elif data_quality.score < 70:
        rec.confidence *= 0.85
        dq_notes.append("Einige Datenpunkte fehlen — Confidence leicht reduziert")

    for w in data_quality.warnings:
        dq_notes.append(w)

    # ── Volume Modifier Adjustments ──────────────────────────────
    if volume_modifier == "gross":
        rec.confidence -= 0.05  # Große Positionen erfordern mehr Sicherheit
        warnings_list.append("Übergewichtete Position (Groß). Strengeres Risikomanagement priorisieren.")
        rationale.append("Da es sich um eine große Position handelt, liegt der Fokus auf Kapitalerhalt.")
        if rec.primary == RecommendationType.NORMAL_HOLD:
            rec.summary += " Position engmaschig überwachen aufgrund der Größe."
    elif volume_modifier == "klein":
        rec.confidence += 0.05  # Kleine Positionen haben mehr Spielraum
        rationale.append("Da es sich um eine kleine Position handelt, kann dem Kurs mehr Volatilität eingeräumt werden.")

    # ── Review Triggers (ereignisbasiert statt pauschal) ─────────
    if validation.stop_status == StopStatus.ACTIVE:
        review_triggers.append("Schlusskurs unter aktivem Stop")
    if signals.get("sma50_val"):
        review_triggers.append("Schlusskurs unter SMA50")
    if signals.get("sma200_val"):
        review_triggers.append("Schlusskurs unter SMA200")
    review_triggers.append("Weitere Momentum-Verschlechterung (MACD + OBV + VWMA bearish)")
    review_triggers.append("Earnings/Event innerhalb von 7 Tagen")
    if metrics.profit_giveback_ratio is not None and metrics.profit_giveback_ratio > 0.5:
        review_triggers.append("ProfitGivebackRatio über 50%")
    if metrics.stop_distance_atr is not None and metrics.stop_distance_atr < 1:
        review_triggers.append("StopDistanceATR unter 1 — Stop sehr eng")

    # ── Confidence clamping ──────────────────────────────────────
    rec.confidence = max(0.0, min(1.0, rec.confidence))

    # ── Mode Title Mapping ───────────────────────────────────────
    MODE_TITLES = {
        RecommendationType.NORMAL_HOLD.value: "✅ Intakter Trend (Halten)",
        RecommendationType.PROFIT_PROTECTION_MODE.value: "🛡️ Gewinne absichern",
        RecommendationType.HOLD_WITH_TRAILING_STOP.value: "🛡️ Gewinne laufen lassen & absichern",
        RecommendationType.TARGET_REACHED_REVIEW.value: "🎯 Kursziel erreicht (Handeln!)",
        RecommendationType.EXIT_REVIEW.value: "🚨 Kritisch: Ausstieg prüfen",
        RecommendationType.EXIT.value: "🚨 Kritisch: Ausstieg prüfen",
        RecommendationType.LOSS_POSITION_REVIEW.value: "⚠️ Kritischer Verlust: These prüfen",
        RecommendationType.THESIS_REVIEW.value: "🤔 Warnsignale: Investment-These prüfen",
        RecommendationType.ADD_ALLOWED.value: "📈 Stärke ausbauen (Nachkaufen)",
        RecommendationType.NO_ACTION_DATA_INSUFFICIENT.value: "⏸️ Daten unzureichend",
        RecommendationType.HOLD_BUT_REDUCE_RISK.value: "⚠️ Halten, aber Risiko reduzieren",
    }
    rec.mode_title = MODE_TITLES.get(
        rec.primary.value if hasattr(rec.primary, 'value') else str(rec.primary),
        str(rec.primary)
    )

    # ── Assemble ─────────────────────────────────────────────────
    rec.next_actions = next_actions
    rec.optional_actions = optional_actions
    rec.forbidden_actions = forbidden_actions
    rec.warnings = warnings_list
    rec.rationale = rationale
    rec.review_triggers = review_triggers
    rec.data_quality_notes = dq_notes

    return rec
