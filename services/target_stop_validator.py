"""
services/target_stop_validator.py — Harte Validierungsregeln für Target und Stop.

NICHT VERHANDELBARE KERNREGELN:
- LONG: currentPrice >= takeProfit → TARGET_REACHED, activeTakeProfit = null
- LONG: currentPrice <= activeStop → STOP_BREACHED
- LONG: neuer Stop < previousStop → ValidationError (Stop darf nicht gelockert werden)
- SHORT: gespiegelte Regeln

Guards gegen NaN, Infinity und fehlende Werte.
"""

from __future__ import annotations

import math
from typing import Optional

from services.position_types import (
    PositionSide, TargetStatus, StopStatus, Severity,
    ValidationEntry, ValidationResult,
)


def _is_valid_price(val: Optional[float]) -> bool:
    """Prüft ob ein Preiswert gültig ist (nicht None, NaN, Infinity, <= 0)."""
    if val is None:
        return False
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return False
    return val > 0


def validate_target_stop(
    side: PositionSide,
    current_price: float,
    entry_price: float,
    take_profit: Optional[float] = None,
    active_stop: Optional[float] = None,
    previous_stop: Optional[float] = None,
    initial_stop: Optional[float] = None,
) -> ValidationResult:
    """Validiert Target und Stop für eine Position.

    Implementiert alle harten Validierungsregeln aus der Spezifikation.
    Diese Funktion ist der zentrale Gatekeeper — sie verhindert
    widersprüchliche Handlungsschritte.

    Args:
        side: LONG oder SHORT
        current_price: Aktueller Kurs
        entry_price: Einstiegskurs
        take_profit: Take-Profit-Ziel (kann None sein)
        active_stop: Aktueller aktiver Stop (kann None sein)
        previous_stop: Vorheriger Stop für Ratchet-Validierung
        initial_stop: Initialer Stop bei Positionseröffnung

    Returns:
        ValidationResult mit target_status, stop_status, Fehlern und Warnungen
    """
    result = ValidationResult()
    errors: list[ValidationEntry] = []
    warnings: list[ValidationEntry] = []
    rules: list[ValidationEntry] = []

    # ── Guard: Pflichtfelder ──────────────────────────────────────────
    if not _is_valid_price(current_price):
        errors.append(ValidationEntry(
            rule_id="MISSING_CURRENT_PRICE",
            severity=Severity.CRITICAL,
            triggered=True,
            message="Kein gültiger aktueller Kurs vorhanden. Positionsanalyse nicht möglich.",
            affected_recommendation="NO_ACTION_DATA_INSUFFICIENT",
        ))
        result.errors = errors
        return result

    if not _is_valid_price(entry_price):
        errors.append(ValidationEntry(
            rule_id="MISSING_ENTRY_PRICE",
            severity=Severity.CRITICAL,
            triggered=True,
            message="Kein gültiger Einstiegskurs vorhanden. Positionsanalyse nicht möglich.",
            affected_recommendation="NO_ACTION_DATA_INSUFFICIENT",
        ))
        result.errors = errors
        return result

    # ── Target-Validierung ────────────────────────────────────────────
    if _is_valid_price(take_profit):
        if side == PositionSide.LONG:
            if current_price >= take_profit:
                # NICHT VERHANDELBARE KERNREGEL:
                # Take-Profit wurde erreicht oder überschritten
                result.target_status = TargetStatus.TARGET_REACHED
                result.active_take_profit = None  # TP deaktiviert
                result.profit_protection_mode = True

                exceeded_pct = ((current_price - take_profit) / take_profit) * 100
                rules.append(ValidationEntry(
                    rule_id="LONG_TARGET_ALREADY_REACHED",
                    severity=Severity.HIGH,
                    triggered=True,
                    message=(
                        f"Aktueller Kurs ({current_price:.2f}) liegt über dem "
                        f"Take-Profit ({take_profit:.2f}). "
                        f"Take-Profit ist nicht mehr als aktives Ziel gültig. "
                        f"Überschritten um {exceeded_pct:.1f}%."
                    ),
                    affected_recommendation="TARGET_REACHED_REVIEW oder PROFIT_PROTECTION_MODE",
                ))
            else:
                # TP noch nicht erreicht — aktiv
                result.target_status = TargetStatus.ACTIVE
                result.active_take_profit = take_profit
        else:
            # SHORT
            if current_price <= take_profit:
                result.target_status = TargetStatus.TARGET_REACHED
                result.active_take_profit = None
                result.profit_protection_mode = True

                exceeded_pct = ((take_profit - current_price) / take_profit) * 100
                rules.append(ValidationEntry(
                    rule_id="SHORT_TARGET_ALREADY_REACHED",
                    severity=Severity.HIGH,
                    triggered=True,
                    message=(
                        f"Aktueller Kurs ({current_price:.2f}) liegt unter dem "
                        f"Take-Profit ({take_profit:.2f}). "
                        f"Take-Profit ist nicht mehr als aktives Ziel gültig. "
                        f"Überschritten um {exceeded_pct:.1f}%."
                    ),
                    affected_recommendation="TARGET_REACHED_REVIEW oder PROFIT_PROTECTION_MODE",
                ))
            else:
                result.target_status = TargetStatus.ACTIVE
                result.active_take_profit = take_profit
    else:
        result.target_status = TargetStatus.NO_TARGET
        result.active_take_profit = None
        warnings.append(ValidationEntry(
            rule_id="NO_TAKE_PROFIT_SET",
            severity=Severity.LOW,
            triggered=True,
            message="Kein Take-Profit definiert. Reward/Risk-Berechnung gegen Ziel nicht möglich.",
            affected_recommendation="TargetQualityScore reduzieren",
        ))

    # ── Stop-Validierung ──────────────────────────────────────────────
    if _is_valid_price(active_stop):
        if side == PositionSide.LONG:
            # Stop breach check
            if current_price <= active_stop:
                result.stop_status = StopStatus.STOP_BREACHED
                rules.append(ValidationEntry(
                    rule_id="LONG_STOP_BREACHED",
                    severity=Severity.CRITICAL,
                    triggered=True,
                    message=(
                        f"Aktueller Kurs ({current_price:.2f}) liegt auf oder unter dem "
                        f"Stop-Loss ({active_stop:.2f}). Exit prüfen."
                    ),
                    affected_recommendation="EXIT_REVIEW oder EXIT",
                ))
            else:
                result.stop_status = StopStatus.ACTIVE
                result.active_stop = active_stop

            # Stop locks profit?
            if active_stop >= entry_price:
                result.stop_locks_profit = True

            # Ratchet-Regel: Stop darf nicht gelockert werden
            if _is_valid_price(previous_stop) and active_stop < previous_stop:
                errors.append(ValidationEntry(
                    rule_id="LONG_STOP_LOOSENED",
                    severity=Severity.HIGH,
                    triggered=True,
                    message=(
                        f"Long-Stop ({active_stop:.2f}) liegt unter dem vorherigen "
                        f"Stop ({previous_stop:.2f}). Long-Stops dürfen nicht gelockert werden."
                    ),
                    affected_recommendation="Stop auf vorheriges Level zurücksetzen",
                ))

        else:
            # SHORT
            if current_price >= active_stop:
                result.stop_status = StopStatus.STOP_BREACHED
                rules.append(ValidationEntry(
                    rule_id="SHORT_STOP_BREACHED",
                    severity=Severity.CRITICAL,
                    triggered=True,
                    message=(
                        f"Aktueller Kurs ({current_price:.2f}) liegt auf oder über dem "
                        f"Stop-Loss ({active_stop:.2f}). Exit prüfen."
                    ),
                    affected_recommendation="EXIT_REVIEW oder EXIT",
                ))
            else:
                result.stop_status = StopStatus.ACTIVE
                result.active_stop = active_stop

            if active_stop <= entry_price:
                result.stop_locks_profit = True

            if _is_valid_price(previous_stop) and active_stop > previous_stop:
                errors.append(ValidationEntry(
                    rule_id="SHORT_STOP_LOOSENED",
                    severity=Severity.HIGH,
                    triggered=True,
                    message=(
                        f"Short-Stop ({active_stop:.2f}) liegt über dem vorherigen "
                        f"Stop ({previous_stop:.2f}). Short-Stops dürfen nicht gelockert werden."
                    ),
                    affected_recommendation="Stop auf vorheriges Level zurücksetzen",
                ))
    else:
        result.stop_status = StopStatus.NO_STOP
        result.active_stop = None
        warnings.append(ValidationEntry(
            rule_id="NO_ACTIVE_STOP",
            severity=Severity.MEDIUM,
            triggered=True,
            message="Kein aktives Risikolevel vorhanden. RiskManagementScore reduziert.",
            affected_recommendation="RiskManagementScore reduzieren",
        ))

    # ── Initial-Stop-Warnung ──────────────────────────────────────────
    if not _is_valid_price(initial_stop):
        warnings.append(ValidationEntry(
            rule_id="NO_INITIAL_STOP",
            severity=Severity.LOW,
            triggered=True,
            message="Kein initialer Stop definiert. R-Multiple kann nicht berechnet werden.",
            affected_recommendation="DataQualityScore reduzieren",
        ))

    result.errors = errors
    result.warnings = warnings
    result.triggered_rules = rules
    return result
