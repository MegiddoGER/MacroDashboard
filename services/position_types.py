"""
services/position_types.py — Zentrale Typdefinitionen für das Positionsmanagement.

Alle Enums, Dataclasses und Typstrukturen für:
- Positionszustände und Analysemodi
- Validierungsergebnisse
- Metriken, Scores und Empfehlungen
- Stop-Vorschläge und Audit-Einträge
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class AnalysisMode(str, Enum):
    NEW_ENTRY = "NEW_ENTRY"
    EXISTING_LONG = "EXISTING_LONG"
    EXISTING_SHORT = "EXISTING_SHORT"
    ADD_TO_WINNER = "ADD_TO_WINNER"
    NORMAL_HOLD = "NORMAL_HOLD"
    TARGET_REACHED_REVIEW = "TARGET_REACHED_REVIEW"
    PROFIT_PROTECTION_MODE = "PROFIT_PROTECTION_MODE"
    STOP_THREATENED = "STOP_THREATENED"
    THESIS_REVIEW = "THESIS_REVIEW"
    LOSS_POSITION = "LOSS_POSITION"
    EXIT_REVIEW = "EXIT_REVIEW"
    NO_ACTION_DATA_INSUFFICIENT = "NO_ACTION_DATA_INSUFFICIENT"


class TargetStatus(str, Enum):
    ACTIVE = "ACTIVE"
    TARGET_REACHED = "TARGET_REACHED"
    NO_TARGET = "NO_TARGET"
    INVALID = "INVALID"


class StopStatus(str, Enum):
    ACTIVE = "ACTIVE"
    STOP_BREACHED = "STOP_BREACHED"
    NO_STOP = "NO_STOP"
    INVALID = "INVALID"


class RiskStatus(str, Enum):
    LOW = "LOW"
    CONTROLLED = "CONTROLLED"
    ELEVATED_BUT_CONTROLLED = "ELEVATED_BUT_CONTROLLED"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class ThesisStatus(str, Enum):
    INTACT = "INTACT"
    WEAKENING = "WEAKENING"
    REVIEW_NEEDED = "REVIEW_NEEDED"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"


class RecommendationType(str, Enum):
    NEW_ENTRY_ALLOWED = "NEW_ENTRY_ALLOWED"
    NEW_ENTRY_NOT_ALLOWED = "NEW_ENTRY_NOT_ALLOWED"
    HOLD = "HOLD"
    NORMAL_HOLD = "NORMAL_HOLD"
    HOLD_WITH_TRAILING_STOP = "HOLD_WITH_TRAILING_STOP"
    HOLD_BUT_REDUCE_RISK = "HOLD_BUT_REDUCE_RISK"
    TARGET_REACHED_REVIEW = "TARGET_REACHED_REVIEW"
    PARTIAL_TAKE_PROFIT = "PARTIAL_TAKE_PROFIT"
    PROFIT_PROTECTION_MODE = "PROFIT_PROTECTION_MODE"
    ADD_ALLOWED = "ADD_ALLOWED"
    ADD_NOT_ALLOWED = "ADD_NOT_ALLOWED"
    STOP_THREATENED = "STOP_THREATENED"
    THESIS_REVIEW = "THESIS_REVIEW"
    LOSS_POSITION_REVIEW = "LOSS_POSITION_REVIEW"
    EXIT_REVIEW = "EXIT_REVIEW"
    EXIT = "EXIT"
    NO_ACTION_DATA_INSUFFICIENT = "NO_ACTION_DATA_INSUFFICIENT"


class StopType(str, Enum):
    AGGRESSIVE_PROFIT_LOCK = "AGGRESSIVE_PROFIT_LOCK"
    NORMAL_TREND_FOLLOWING = "NORMAL_TREND_FOLLOWING"
    CONSERVATIVE_STRUCTURE = "CONSERVATIVE_STRUCTURE"
    BREAK_EVEN = "BREAK_EVEN"
    CHANDELIER_EXIT = "CHANDELIER_EXIT"
    SMA20 = "SMA20"
    SMA50 = "SMA50"
    INVALID = "INVALID"


class StopSuitability(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class ValidationEntry:
    """Eine einzelne Validierungs-Regel (Fehler oder Warnung)."""
    rule_id: str
    severity: Severity
    triggered: bool
    message: str
    affected_recommendation: str = ""


@dataclass
class ValidationResult:
    """Gesamtergebnis der Target/Stop-Validierung."""
    target_status: TargetStatus = TargetStatus.NO_TARGET
    stop_status: StopStatus = StopStatus.NO_STOP
    active_take_profit: Optional[float] = None
    active_stop: Optional[float] = None
    profit_protection_mode: bool = False
    stop_locks_profit: bool = False
    errors: list[ValidationEntry] = field(default_factory=list)
    warnings: list[ValidationEntry] = field(default_factory=list)
    triggered_rules: list[ValidationEntry] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_critical_warnings(self) -> bool:
        return any(
            w.severity in (Severity.HIGH, Severity.CRITICAL)
            for w in self.warnings
        )


# ---------------------------------------------------------------------------
# Metriken
# ---------------------------------------------------------------------------

@dataclass
class PositionMetrics:
    """Alle berechneten Positionsmetriken."""
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    invested_capital: Optional[float] = None
    current_value: Optional[float] = None
    secured_profit_at_stop: Optional[float] = None
    secured_profit_pct_at_stop: Optional[float] = None
    open_risk: Optional[float] = None
    r_multiple: Optional[float] = None
    distance_to_stop_pct: Optional[float] = None
    distance_to_target_pct: Optional[float] = None
    remaining_reward_risk: Optional[float] = None
    target_exceeded_by_pct: Optional[float] = None
    position_cagr: Optional[float] = None
    stop_distance_atr: Optional[float] = None
    stop_locks_profit: bool = False
    # Drawdown/giveback (require highSinceEntry — often null)
    drawdown_from_high: Optional[float] = None
    profit_giveback_ratio: Optional[float] = None
    secured_profit_ratio: Optional[float] = None


# ---------------------------------------------------------------------------
# Stop-Vorschläge
# ---------------------------------------------------------------------------

@dataclass
class StopProposal:
    """Ein einzelner Stop-Vorschlag mit Erklärung."""
    type: StopType
    stop_price: Optional[float] = None
    distance_pct: Optional[float] = None
    distance_atr: Optional[float] = None
    locks_profit: bool = False
    locked_profit: Optional[float] = None
    locked_profit_pct: Optional[float] = None
    risk_if_hit: Optional[float] = None
    explanation: str = ""
    suitability: StopSuitability = StopSuitability.MEDIUM


# ---------------------------------------------------------------------------
# Score Breakdown
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    """12 Teilscores + Overall."""
    trend_health: Optional[float] = None
    momentum: Optional[float] = None
    volume_structure: Optional[float] = None
    relative_strength: Optional[float] = None
    valuation: Optional[float] = None
    balance_sheet: Optional[float] = None
    quality_profitability: Optional[float] = None
    sentiment: Optional[float] = None
    risk_management: Optional[float] = None
    target_quality: Optional[float] = None
    event_risk: Optional[float] = None
    data_quality: Optional[float] = None
    overall: Optional[float] = None
    has_critical_warning: bool = False

    def to_dict(self) -> dict:
        return {
            "trend_health": self.trend_health,
            "momentum": self.momentum,
            "volume_structure": self.volume_structure,
            "relative_strength": self.relative_strength,
            "valuation": self.valuation,
            "balance_sheet": self.balance_sheet,
            "quality_profitability": self.quality_profitability,
            "sentiment": self.sentiment,
            "risk_management": self.risk_management,
            "target_quality": self.target_quality,
            "event_risk": self.event_risk,
            "data_quality": self.data_quality,
            "overall": self.overall,
            "has_critical_warning": self.has_critical_warning,
        }


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

@dataclass
class RecommendationResult:
    """Erklärbare, regelbasierte Empfehlung."""
    primary: RecommendationType = RecommendationType.NORMAL_HOLD
    alternative: Optional[RecommendationType] = None
    status: str = ""
    confidence: float = 0.5
    summary: str = ""
    mode_title: str = ""
    suggested_optimal_stop: Optional[float] = None
    suggested_take_profit: Optional[float] = None
    rationale: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    optional_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    review_triggers: list[str] = field(default_factory=list)
    data_quality_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "primary": self.primary.value if isinstance(self.primary, Enum) else str(self.primary),
            "alternative": self.alternative.value if isinstance(self.alternative, Enum) else self.alternative,
            "status": self.status,
            "confidence": self.confidence,
            "summary": self.summary,
            "mode_title": self.mode_title,
            "suggested_optimal_stop": self.suggested_optimal_stop,
            "suggested_take_profit": self.suggested_take_profit,
            "rationale": self.rationale,
            "next_actions": self.next_actions,
            "optional_actions": self.optional_actions,
            "forbidden_actions": self.forbidden_actions,
            "warnings": self.warnings,
            "review_triggers": self.review_triggers,
            "data_quality_notes": self.data_quality_notes,
        }


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """Ausgelöste Regel im Audit Log."""
    rule_id: str
    severity: Severity
    triggered: bool
    message: str
    affected_recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "ruleId": self.rule_id,
            "severity": self.severity.value,
            "triggered": self.triggered,
            "message": self.message,
            "affectedRecommendation": self.affected_recommendation,
        }


# ---------------------------------------------------------------------------
# Position State
# ---------------------------------------------------------------------------

@dataclass
class PositionState:
    """Aktueller Positionszustand nach State-Engine-Analyse."""
    mode: AnalysisMode = AnalysisMode.NORMAL_HOLD
    target_status: TargetStatus = TargetStatus.NO_TARGET
    stop_status: StopStatus = StopStatus.NO_STOP
    risk_status: RiskStatus = RiskStatus.UNKNOWN
    thesis_status: ThesisStatus = ThesisStatus.UNKNOWN
    profit_protection_mode: bool = False
    technical_warning_score: int = 0
    fundamental_warning_score: int = 0


# ---------------------------------------------------------------------------
# Data Quality
# ---------------------------------------------------------------------------

@dataclass
class DataQualityResult:
    """Ergebnis der Datenqualitätsprüfung."""
    score: float = 100.0  # 0–100
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence_modifier: float = 1.0  # 0–1, multipliziert die Confidence


# ---------------------------------------------------------------------------
# Gesamt-Analyse
# ---------------------------------------------------------------------------

@dataclass
class PositionAnalysis:
    """Komplettes Analyseobjekt einer Position."""
    mode: AnalysisMode = AnalysisMode.NORMAL_HOLD
    side: PositionSide = PositionSide.LONG
    state: PositionState = field(default_factory=PositionState)
    validation: ValidationResult = field(default_factory=ValidationResult)
    metrics: PositionMetrics = field(default_factory=PositionMetrics)
    scores: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    recommendation: RecommendationResult = field(default_factory=RecommendationResult)
    data_quality: DataQualityResult = field(default_factory=DataQualityResult)
    stop_proposals: list[StopProposal] = field(default_factory=list)
    audit_log: list[AuditEntry] = field(default_factory=list)
