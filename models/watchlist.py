"""
models/watchlist.py — Domain-Datenklasse für Watchlist-Einträge.
"""

from dataclasses import dataclass


@dataclass
class WatchlistItem:
    """Ein Eintrag in der Watchlist."""
    ticker: str
    name: str
    display: str = ""
    status: str = "Beobachtet"
