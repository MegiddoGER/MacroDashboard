"""
styles/charts.py — Styles für Plotly Charts (Modebar).
"""

from styles.theme import COLORS


def css_charts() -> str:
    return f"""
/* ── Plotly Modebar ── */
.modebar {{
    visibility: visible !important;
    opacity: 1 !important;
    background-color: transparent !important;
}}
.modebar-btn svg {{
    fill: #ffffff !important;
}}
.modebar-btn:hover svg {{
    fill: {COLORS["accent"]} !important;
}}
"""
