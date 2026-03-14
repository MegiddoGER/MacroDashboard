"""
controllers/directory.py — Orchestriert die Aktien-Verzeichnis-Seite.
"""

from views.pages.directory import page_listings


def run():
    """Führt die Aktien-Verzeichnis-Seite aus."""
    page_listings()
