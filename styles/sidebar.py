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


def css_sidebar_watchlist() -> str:
    """Sidebar-Watchlist: Gruppierte Mini-Karten mit Status-Dots."""
    return f"""
/* ── Watchlist: Gruppen-Header ── */
.wl-group-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 4px 4px 4px;
    margin-top: 8px;
    margin-bottom: 2px;
}}
.wl-group-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    box-shadow: 0 0 6px currentColor;
}}
.wl-group-title {{
    font-family: {FONT["family"]};
    font-size: 0.7rem;
    font-weight: {FONT["weight_semibold"]};
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {COLORS["text_dim"]};
    flex-grow: 1;
}}
.wl-group-count {{
    font-family: {FONT["family"]};
    font-size: 0.65rem;
    font-weight: {FONT["weight_semibold"]};
    color: {COLORS["text_muted"]};
    background: rgba(148, 163, 184, 0.12);
    padding: 1px 7px;
    border-radius: 10px;
    min-width: 18px;
    text-align: center;
}}

/* ── Watchlist: Ticker-Karte ── */
.wl-card {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 8px;
    border-radius: 6px;
    transition: {TRANSITION["fast"]};
    cursor: default;
    margin: -4px 0;
}}
.wl-card:hover {{
    background: rgba(148, 163, 184, 0.08);
}}
.wl-card-dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
    opacity: 0.85;
}}
.wl-card-info {{
    display: flex;
    flex-direction: column;
    gap: 0px;
    min-width: 0;
    overflow: hidden;
}}
.wl-card-ticker {{
    font-family: {FONT["family"]};
    font-size: 0.82rem;
    font-weight: {FONT["weight_semibold"]};
    color: {COLORS["text"]};
    letter-spacing: 0.03em;
    line-height: 1.2;
}}
.wl-card-name {{
    font-family: {FONT["family"]};
    font-size: 0.65rem;
    font-weight: {FONT["weight_regular"]};
    color: {COLORS["text_muted"]};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
}}
"""
