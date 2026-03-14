"""
controllers/watchlist_page.py — Orchestriert die Watchlist-Seite.
"""

from views.pages.watchlist import page_watchlist


def run():
    """Führt die Watchlist-Seite aus."""
    page_watchlist()
