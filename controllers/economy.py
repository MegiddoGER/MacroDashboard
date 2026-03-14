"""
controllers/economy.py — Orchestriert die Gesamtwirtschaft-Seite.
"""

from views.pages.economy import page_macro


def run():
    """Führt die Gesamtwirtschaft-Seite aus."""
    page_macro()
