"""
models/quote.py — Domain-Datenklassen für Aktien-Kursdaten.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuoteData:
    """Aktueller Kurs und tägliche Veränderung."""
    price: float
    change_pct: float


@dataclass
class FinancialRecord:
    """Ein Jahres-Finanzeintrag (Umsatz, EBITDA, Nettogewinn)."""
    year: int | str
    date: object = None
    revenue: Optional[float] = None
    revenue_yoy: Optional[float] = None
    ebitda: Optional[float] = None
    ebitda_yoy: Optional[float] = None
    net_income: Optional[float] = None
    net_income_yoy: Optional[float] = None


@dataclass
class StockStats:
    """Kernkennzahlen einer Aktie."""
    current_price: float
    high_52w: float
    low_52w: float
    volatility: float
    rsi: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    avg_volume: int = 0
    name: str = ""
    sector: str = "—"
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    earnings_date: Optional[str] = None


@dataclass
class StockDetails:
    """Gesamtpaket einer Aktienanalyse (Daten + berechnete Serien)."""
    info: dict = field(default_factory=dict)
    stats: Optional[StockStats] = None
    hist_1d: object = None
    hist_1w: object = None
    hist_1m: object = None
    hist_ytd: object = None
    hist_1y: object = None
    hist_5y: object = None
    hist_max: object = None
    rsi_series: object = None
    sma_20: object = None
    sma_50: object = None
    sma_200: object = None
    returns: object = None
    financials: list = field(default_factory=list)
