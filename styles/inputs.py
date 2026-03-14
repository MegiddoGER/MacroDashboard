"""
styles/inputs.py — Styles für Selectboxen und Text-Inputs.
"""

from styles.theme import COLORS


def css_inputs() -> str:
    return f"""
/* ── Selectbox / Input ── */
div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label {{
    color: {COLORS["text_dim"]} !important;
    font-size: 0.8rem !important;
}}
"""
