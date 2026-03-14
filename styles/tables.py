"""
styles/tables.py — Styles für DataFrames / Tabellen.
"""

from styles.theme import COLORS, SPACING


def css_tables() -> str:
    return f"""
/* ── Tabellen ── */
div[data-testid="stDataFrame"] {{
    background: {COLORS["bg_card"]};
    border-radius: {SPACING["radius_md"]};
    border: 1px solid {COLORS["border"]};
    padding: 4px;
}}
"""
