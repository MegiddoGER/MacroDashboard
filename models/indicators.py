"""
models/indicators.py — Domain-Datenklassen für technische Indikatoren.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SwingSignal:
    """Ergebnis der Swing-Trading-Analyse."""
    current: float
    adx: Optional[float] = None
    trend_strength: str = "—"
    cross_status: str = "neutral"
    cross_label: str = "—"
    direction: str = "—"
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    pivot: float = 0.0
    r1: float = 0.0
    r2: float = 0.0
    s1: float = 0.0
    s2: float = 0.0
    atr: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    rr_ratio: Optional[float] = None
    sma20_series: object = None
    sma50_series: object = None


@dataclass
class OrderFlowResult:
    """Ergebnis der Order-Flow-Analyse."""
    vwap: object = None
    vwap_val: Optional[float] = None
    vwap_signal: str = "neutral"
    vwap_desc: str = "—"
    obv: object = None
    obv_signal: str = "neutral"
    obv_desc: str = "—"
    vol_profile: object = None
    poc_price: Optional[float] = None
    spike_dates: list = field(default_factory=list)
    n_spikes_recent: int = 0
    current: float = 0.0


@dataclass
class FearGreedComponents:
    """Fear & Greed Index Ergebnis."""
    total: float
    components: list = field(default_factory=list)


@dataclass
class TechnicalSummary:
    """Gesamt-Fazit aller technischen Indikatoren."""
    score: int = 0
    score_label: str = "Nicht berechenbar"
    checklist: list = field(default_factory=list)
    macro: str = "—"
    micro: str = "—"
    actionable: str = "—"
