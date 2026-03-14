"""
controllers/home.py — Orchestriert die Startseite.
"""

from views.pages.home import page_market


def run():
    """Führt die Startseite aus."""
    page_market()
