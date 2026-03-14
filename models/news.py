"""
models/news.py — Domain-Datenklasse für Nachrichten.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NewsArticle:
    """Ein Nachrichtenartikel (RSS oder yfinance)."""
    title: str
    link: str = ""
    published: Optional[datetime] = None
    source: str = ""
    summary: str = ""
