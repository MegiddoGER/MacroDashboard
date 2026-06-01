"""
services/trailing_stop_engine.py — Generiert mehrere Stop-Vorschläge.

Für LONG: ATR-basiert (aggressiv/normal/konservativ), Chandelier Exit,
SMA20, SMA50, Break-Even. Jeder Vorschlag mit Erklärung und Suitability.

Ratchet-Regel: Neuer Stop darf vorherigen nie unterschreiten (Long) /
überschreiten (Short).
"""

from __future__ import annotations

import math
from typing import Optional

from services.position_types import (
    PositionSide, StopType, StopSuitability, StopProposal,
)


def _safe(val: Optional[float]) -> Optional[float]:
    """Gibt None zurück bei NaN oder Infinity."""
    if val is None:
        return None
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val


def _calc_stop_details(
    stop_price: float,
    current_price: float,
    entry_price: float,
    quantity: float,
    atr_val: Optional[float],
    side: PositionSide,
) -> dict:
    """Berechnet gemeinsame Details für einen Stop-Vorschlag."""
    if side == PositionSide.LONG:
        distance_pct = ((current_price - stop_price) / current_price) * 100 if current_price > 0 else None
        locks_profit = stop_price >= entry_price
        locked_profit = (stop_price - entry_price) * quantity if locks_profit else None
        locked_profit_pct = ((stop_price - entry_price) / entry_price) * 100 if locks_profit and entry_price > 0 else None
        risk_if_hit = (current_price - stop_price) * quantity
    else:
        distance_pct = ((stop_price - current_price) / current_price) * 100 if current_price > 0 else None
        locks_profit = stop_price <= entry_price
        locked_profit = (entry_price - stop_price) * quantity if locks_profit else None
        locked_profit_pct = ((entry_price - stop_price) / entry_price) * 100 if locks_profit and entry_price > 0 else None
        risk_if_hit = (stop_price - current_price) * quantity

    distance_atr = abs(current_price - stop_price) / atr_val if atr_val and atr_val > 0 else None

    return {
        "distance_pct": _safe(distance_pct),
        "distance_atr": _safe(distance_atr),
        "locks_profit": locks_profit,
        "locked_profit": _safe(locked_profit),
        "locked_profit_pct": _safe(locked_profit_pct),
        "risk_if_hit": _safe(risk_if_hit),
    }


def generate_stop_proposals(
    side: PositionSide,
    current_price: float,
    entry_price: float,
    quantity: float = 1.0,
    atr_val: Optional[float] = None,
    highest_high_22: Optional[float] = None,
    sma20: Optional[float] = None,
    sma50: Optional[float] = None,
    previous_stop: Optional[float] = None,
) -> list[StopProposal]:
    """Generiert mehrere Stop-Vorschläge mit Erklärung.

    Args:
        side: LONG oder SHORT
        current_price: Aktueller Kurs
        entry_price: Einstiegskurs
        quantity: Stückzahl
        atr_val: ATR(14) Wert
        highest_high_22: Höchstes Hoch der letzten 22 Tage (für Chandelier)
        sma20: SMA20 Wert
        sma50: SMA50 Wert
        previous_stop: Vorheriger aktiver Stop (Ratchet-Basis)

    Returns:
        Liste von StopProposal-Objekten, sortiert nach Aggressivität
    """
    proposals: list[StopProposal] = []

    if current_price <= 0 or entry_price <= 0:
        return proposals

    # ── ATR-basierte Stops ────────────────────────────────────────
    if atr_val and atr_val > 0:
        atr_configs = [
            (1.5, StopType.AGGRESSIVE_PROFIT_LOCK, StopSuitability.LOW,
             "Aggressiver Gewinnschutz (1,5× ATR). Kann bei normaler Volatilität schnell ausgelöst werden."),
            (2.5, StopType.NORMAL_TREND_FOLLOWING, StopSuitability.HIGH,
             "Standard-Trendfolge-Stop (2,5× ATR). Guter Kompromiss zwischen Schutz und Spielraum."),
            (3.5, StopType.CONSERVATIVE_STRUCTURE, StopSuitability.MEDIUM,
             "Konservativer Struktur-Stop (3,5× ATR). Gibt dem Trend mehr Raum, sichert weniger Gewinn."),
        ]

        for multiplier, stop_type, suitability, explanation in atr_configs:
            if side == PositionSide.LONG:
                stop_price = current_price - multiplier * atr_val
            else:
                stop_price = current_price + multiplier * atr_val

            stop_price = _safe(stop_price)
            if stop_price is None or stop_price <= 0:
                continue

            details = _calc_stop_details(stop_price, current_price, entry_price, quantity, atr_val, side)

            proposals.append(StopProposal(
                type=stop_type,
                stop_price=round(stop_price, 2),
                distance_pct=details["distance_pct"],
                distance_atr=details["distance_atr"],
                locks_profit=details["locks_profit"],
                locked_profit=details["locked_profit"],
                locked_profit_pct=details["locked_profit_pct"],
                risk_if_hit=details["risk_if_hit"],
                explanation=explanation,
                suitability=suitability,
            ))

    # ── Chandelier Exit ──────────────────────────────────────────
    if atr_val and atr_val > 0 and highest_high_22 is not None:
        if side == PositionSide.LONG:
            chandelier_price = highest_high_22 - 3.0 * atr_val
        else:
            # For short: LowestLow + 3*ATR (highest_high_22 should be lowest_low for short)
            chandelier_price = highest_high_22 + 3.0 * atr_val

        chandelier_price = _safe(chandelier_price)
        if chandelier_price is not None and chandelier_price > 0:
            details = _calc_stop_details(chandelier_price, current_price, entry_price, quantity, atr_val, side)
            proposals.append(StopProposal(
                type=StopType.CHANDELIER_EXIT,
                stop_price=round(chandelier_price, 2),
                distance_pct=details["distance_pct"],
                distance_atr=details["distance_atr"],
                locks_profit=details["locks_profit"],
                locked_profit=details["locked_profit"],
                locked_profit_pct=details["locked_profit_pct"],
                risk_if_hit=details["risk_if_hit"],
                explanation="Chandelier Exit (3× ATR unter 22-Tage-Hoch). Dynamischer Trailing Stop, passt sich an Hochs an.",
                suitability=StopSuitability.HIGH,
            ))

    # ── SMA-basierte Stops ───────────────────────────────────────
    if sma20 is not None and sma20 > 0:
        details = _calc_stop_details(sma20, current_price, entry_price, quantity, atr_val, side)
        proposals.append(StopProposal(
            type=StopType.SMA20,
            stop_price=round(sma20, 2),
            distance_pct=details["distance_pct"],
            distance_atr=details["distance_atr"],
            locks_profit=details["locks_profit"],
            locked_profit=details["locked_profit"],
            locked_profit_pct=details["locked_profit_pct"],
            risk_if_hit=details["risk_if_hit"],
            explanation="SMA20-Stop. Kurzfristiger Trendindikator — aggressiver Stop.",
            suitability=StopSuitability.LOW,
        ))

    if sma50 is not None and sma50 > 0:
        details = _calc_stop_details(sma50, current_price, entry_price, quantity, atr_val, side)
        proposals.append(StopProposal(
            type=StopType.SMA50,
            stop_price=round(sma50, 2),
            distance_pct=details["distance_pct"],
            distance_atr=details["distance_atr"],
            locks_profit=details["locks_profit"],
            locked_profit=details["locked_profit"],
            locked_profit_pct=details["locked_profit_pct"],
            risk_if_hit=details["risk_if_hit"],
            explanation="SMA50-Stop. Mittelfristiger Trendindikator — moderater Stop.",
            suitability=StopSuitability.MEDIUM,
        ))

    # ── Break-Even Stop ──────────────────────────────────────────
    if side == PositionSide.LONG and current_price > entry_price:
        details = _calc_stop_details(entry_price, current_price, entry_price, quantity, atr_val, side)
        proposals.append(StopProposal(
            type=StopType.BREAK_EVEN,
            stop_price=round(entry_price, 2),
            distance_pct=details["distance_pct"],
            distance_atr=details["distance_atr"],
            locks_profit=False,  # Exactly break-even, no profit locked
            locked_profit=0.0,
            locked_profit_pct=0.0,
            risk_if_hit=details["risk_if_hit"],
            explanation="Break-Even-Stop auf Einstiegskurs. Kein Verlustrisiko, aber auch kein gesicherter Gewinn.",
            suitability=StopSuitability.MEDIUM,
        ))

    elif side == PositionSide.SHORT and current_price < entry_price:
        details = _calc_stop_details(entry_price, current_price, entry_price, quantity, atr_val, side)
        proposals.append(StopProposal(
            type=StopType.BREAK_EVEN,
            stop_price=round(entry_price, 2),
            distance_pct=details["distance_pct"],
            distance_atr=details["distance_atr"],
            locks_profit=False,
            locked_profit=0.0,
            locked_profit_pct=0.0,
            risk_if_hit=details["risk_if_hit"],
            explanation="Break-Even-Stop auf Einstiegskurs.",
            suitability=StopSuitability.MEDIUM,
        ))

    # ── Ratchet-Regel anwenden ───────────────────────────────────
    # Für Long: Kein Vorschlag darf unter dem vorherigen Stop liegen
    # Für Short: Kein Vorschlag darf über dem vorherigen Stop liegen
    if previous_stop is not None and previous_stop > 0:
        for p in proposals:
            if p.stop_price is not None:
                if side == PositionSide.LONG and p.stop_price < previous_stop:
                    p.stop_price = round(previous_stop, 2)
                    p.explanation += f" (Angehoben auf vorherigen Stop {previous_stop:.2f} — Ratchet-Regel)"
                elif side == PositionSide.SHORT and p.stop_price > previous_stop:
                    p.stop_price = round(previous_stop, 2)
                    p.explanation += f" (Gesenkt auf vorherigen Stop {previous_stop:.2f} — Ratchet-Regel)"

    # Sortieren: Aggressivste zuerst (höchster Stop-Preis bei Long)
    if side == PositionSide.LONG:
        proposals.sort(key=lambda p: p.stop_price or 0, reverse=True)
    else:
        proposals.sort(key=lambda p: p.stop_price or float('inf'))

    return proposals


def get_suggested_stop(
    proposals: list[StopProposal],
    side: PositionSide,
    previous_stop: Optional[float] = None,
) -> Optional[float]:
    """Wählt den empfohlenen Stop aus den Vorschlägen.

    Bevorzugt HIGH suitability, dann den besten Kompromiss.
    Respektiert die Ratchet-Regel.
    """
    if not proposals:
        return None

    # Bevorzuge HIGH suitability Vorschläge
    high_suit = [p for p in proposals if p.suitability == StopSuitability.HIGH and p.stop_price]
    if high_suit:
        best = high_suit[0]
    else:
        medium_suit = [p for p in proposals if p.suitability == StopSuitability.MEDIUM and p.stop_price]
        best = medium_suit[0] if medium_suit else proposals[0]

    suggested = best.stop_price

    # Ratchet
    if suggested and previous_stop:
        if side == PositionSide.LONG:
            suggested = max(suggested, previous_stop)
        else:
            suggested = min(suggested, previous_stop)

    return suggested
