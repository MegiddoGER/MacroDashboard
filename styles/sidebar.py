"""
styles/sidebar.py — Sidebar-Styles (Container, Navigation, Logo).
"""

from styles.theme import COLORS, FONT, SPACING, TRANSITION, NAV_GLOW_COLORS


def css_sidebar() -> str:
    return f"""
/* ── Sidebar: Container ── */
section[data-testid="stSidebar"] {{
    background: {COLORS["bg_sidebar"]};
    border-right: 1px solid var(--border);
    transform: translateX(0px) !important;
    visibility: visible !important;
    position: relative !important;
    display: flex !important;
    min-width: {SPACING["sidebar_width"]} !important;
    max-width: {SPACING["sidebar_width"]} !important;
}}
section[data-testid="stSidebar"] > div > div:first-child {{
    padding-top: 1rem;
}}
"""


def css_sidebar_nav() -> str:
    """Sidebar-Navigation: Glowing Boxes pro Menüpunkt."""
    base = f"""
/* ── Sidebar Nav: Radio-Buttons als Karten ── */
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label > div:first-child,
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > div > label > div:first-child {{
    display: none !important;
}}

section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label,
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > div > label {{
    background-color: rgba(30, 41, 59, 0.4);
    border: 1px solid {COLORS["border_subtle"]};
    border-radius: {SPACING["radius_sm"]};
    padding: {SPACING["padding_nav"]};
    margin-bottom: 8px;
    width: 100%;
    transition: {TRANSITION["normal"]};
    cursor: pointer;
    box-sizing: border-box;
}}

section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label > div:nth-child(2),
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > div > label > div:nth-child(2) {{
    margin-left: 0 !important;
    font-weight: {FONT["weight_medium"]};
}}

.stRadio > label, .stCheckbox > label {{ color: var(--text-dim) !important; }}
"""

    # Glow-Effekte dynamisch generieren
    glow_rules = ""
    for i, glow in enumerate(NAV_GLOW_COLORS, 1):
        glow_rules += f"""
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:nth-of-type({i}):hover,
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(input:checked):nth-of-type({i}),
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > div:nth-child({i}) label:hover,
section[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > div:nth-child({i}) label:has(input:checked) {{
    border-color: {glow["color"]}; box-shadow: 0 0 15px rgba({glow["rgb"]}, 0.35); background-color: rgba({glow["rgb"]}, 0.15);
}}
"""

    return base + glow_rules


def css_sidebar_logo() -> str:
    return f"""
/* ── Sidebar: Analyzer-Logo mit Glow ── */
.analyzer-logo {{
    font-family: {FONT["family"]};
    font-size: 1.6rem;
    font-weight: {FONT["weight_bold"]};
    letter-spacing: 0.05em;
    text-align: center;
    padding: 24px 0 12px 0;
    margin-top: -55px;
    margin-left: -20px;
    margin-right: -20px;
    border-radius: {SPACING["radius_sm"]};
    position: relative;
    z-index: 9999;
    background: {COLORS["bg_sidebar_solid"]};
    cursor: default;
    transition: {TRANSITION["slow"]};
    color: {COLORS["text"]};
}}
.analyzer-logo:hover {{
    color: {COLORS["accent"]};
    text-shadow: 0 0 8px {COLORS["accent_glow"]},
                 0 0 20px rgba(0, 212, 170, 0.35),
                 0 0 40px rgba(0, 212, 170, 0.15);
}}
.analyzer-logo .logo-icon {{
    font-size: 1.3rem;
    margin-right: 4px;
    vertical-align: middle;
}}
.analyzer-logo .logo-sub {{
    display: block;
    font-size: 0.55rem;
    font-weight: {FONT["weight_regular"]};
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: {COLORS["text_muted"]};
    margin-top: 2px;
    transition: color {TRANSITION["slow"]};
}}
.analyzer-logo:hover .logo-sub {{
    color: {COLORS["accent_glow"]};
}}
"""
