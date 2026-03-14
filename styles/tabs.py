"""
styles/tabs.py — Styles für Streamlit-Tabs.
"""

from styles.theme import COLORS, FONT


def css_tabs() -> str:
    return f"""
/* ── Tabs ── */
div[data-testid="stTabs"] button {{
    color: var(--text-dim) !important;
    font-weight: {FONT["weight_medium"]};
}}
div[data-testid="stTabs"] button[aria-selected="true"] {{
    color: {COLORS["accent"]} !important;
    border-bottom-color: {COLORS["accent"]} !important;
}}
"""
