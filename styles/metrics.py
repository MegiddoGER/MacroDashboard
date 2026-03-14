"""
styles/metrics.py — Styles für Metrik-Karten (st.metric).
"""

from styles.theme import COLORS, FONT, SPACING


def css_metrics() -> str:
    return f"""
/* ── Metrik-Karten ── */
div[data-testid="stMetric"] {{
    background: {COLORS["bg_card"]};
    border: 1px solid {COLORS["border"]};
    border-radius: {SPACING["radius_md"]};
    padding: {SPACING["padding_card"]};
}}
div[data-testid="stMetric"] label {{
    color: var(--text-dim) !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: {FONT["weight_medium"]};
}}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
    color: {COLORS["text"]} !important;
    font-weight: {FONT["weight_semibold"]};
    font-size: 1.35rem !important;
}}
"""
