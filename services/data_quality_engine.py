"""
services/data_quality_engine.py — Prüft Datenvollständigkeit und -qualität.

Fehlende Werte reduzieren den Score und die Confidence.
Keine Scheinsicherheit bei unvollständigen Daten.
"""

from __future__ import annotations

from services.position_types import DataQualityResult


def assess_data_quality(
    position_data: dict,
    signals: dict,
    has_dcf: bool = False,
    has_balance: bool = False,
    has_earnings: bool = False,
) -> DataQualityResult:
    """Bewertet die Datenqualität für eine Positionsanalyse.

    Args:
        position_data: Positionsdaten dict
        signals: Scoring-Signale dict
        has_dcf: Ob DCF-Daten verfügbar sind
        has_balance: Ob Bilanzdaten verfügbar sind
        has_earnings: Ob Earnings-Daten verfügbar sind

    Returns:
        DataQualityResult mit Score, fehlenden Feldern und Warnungen
    """
    result = DataQualityResult()
    score = 100.0
    missing: list[str] = []
    warnings: list[str] = []

    # ── Pflichtfelder ─────────────────────────────────────────────
    if not position_data.get("buy_price"):
        score -= 20
        missing.append("Kaufkurs")
        warnings.append("Kaufkurs fehlt — Positionsanalyse stark eingeschränkt")

    if not position_data.get("current_price"):
        score -= 20
        missing.append("Aktueller Kurs")
        warnings.append("Aktueller Kurs fehlt — keine Analyse möglich")

    if not position_data.get("quantity"):
        score -= 10
        missing.append("Stückzahl")
        warnings.append("Stückzahl fehlt — keine absolute P&L-/Risikoberechnung")

    # ── Risikomanagement ──────────────────────────────────────────
    if not position_data.get("stop_loss"):
        score -= 10
        missing.append("Stop-Loss")
        warnings.append("Kein aktives Risikolevel definiert")

    if not position_data.get("take_profit"):
        score -= 5
        missing.append("Take-Profit")

    # ── Zeitdaten ─────────────────────────────────────────────────
    if not position_data.get("buy_date"):
        score -= 5
        missing.append("Kaufdatum")
        warnings.append("Kaufdatum fehlt — Haltedauer und CAGR nicht berechenbar")

    # ── Technische Signale ────────────────────────────────────────
    if signals.get("sma200_val") is None:
        score -= 5
        missing.append("SMA200")

    if signals.get("adx_val") is None:
        score -= 3
        missing.append("ADX")

    if signals.get("rsi_val") is None:
        score -= 3
        missing.append("RSI")

    if not position_data.get("atr_val"):
        score -= 5
        missing.append("ATR")
        warnings.append("ATR fehlt — Stop-Vorschläge und Volatilitätsanalyse eingeschränkt")

    # ── Fundamentaldaten ──────────────────────────────────────────
    if not has_dcf:
        score -= 8
        missing.append("DCF-Bewertung")

    if not has_balance:
        score -= 5
        missing.append("Bilanzdaten")

    if not has_earnings:
        score -= 3
        missing.append("Earnings-Daten")
        warnings.append("Eventdaten fehlen — ereignisbasierter Review eingeschränkt")

    # ── Erweiterte Metriken (nice-to-have) ────────────────────────
    # These reduce score slightly but don't generate warnings
    # highSinceEntry, impliedVolatility, benchmark, sector ETF
    # → These will typically be null in the current data model

    # ── Confidence Modifier ───────────────────────────────────────
    score = max(0.0, min(100.0, score))

    if score >= 80:
        confidence_mod = 1.0
    elif score >= 60:
        confidence_mod = 0.85
    elif score >= 40:
        confidence_mod = 0.7
    elif score >= 20:
        confidence_mod = 0.5
    else:
        confidence_mod = 0.3

    result.score = score
    result.missing_fields = missing
    result.warnings = warnings
    result.confidence_modifier = confidence_mod

    return result
