"""
models/market.py — Domain-Datenklassen für Marktdaten.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SectorPerformance:
    """Performance eines Sektors via ETF."""
    sector: str
    ticker: str
    change_pct: float
    price: float


@dataclass
class InflationRecord:
    """Ein einzelner Inflations-Datenpunkt."""
    date: object
    rate: float
