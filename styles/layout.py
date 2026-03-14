"""
styles/layout.py — Grundlegende Layout-Styles (App-Hintergrund, Typografie, Abstände).
"""

from styles.theme import COLORS, FONT, SPACING


def css_layout() -> str:
    return f"""
/* ── Layout: Font-Import & Globals ── */
@import url('{FONT["import_url"]}');

:root {{
    --bg-card: {COLORS["bg_card"]};
    --border: {COLORS["border"]};
    --accent: {COLORS["accent"]};
    --red: {COLORS["red"]};
    --green: {COLORS["green"]};
    --text: {COLORS["text"]};
    --text-dim: {COLORS["text_dim"]};
}}
*, *::before, *::after {{
    font-family: {FONT["family"]};
}}
span[data-testid="stIconMaterial"], .material-icons, .material-symbols-rounded {{
    font-family: {FONT["icon_family"]} !important;
}}

/* ── Layout: App-Hintergrund ── */
.stApp {{
    background: linear-gradient(160deg, {COLORS["bg_app_start"]} 0%, {COLORS["bg_app_mid"]} 40%, {COLORS["bg_app_end"]} 100%);
}}

/* ── Layout: Typografie ── */
hr {{ border-color: var(--border); margin: 1.5rem 0; }}
h1, h2, h3, h4 {{ color: var(--text) !important; font-weight: {FONT["weight_semibold"]} !important; }}
p, span, li {{ color: {COLORS["text_secondary"]}; }}

/* ── Layout: Block-Container ── */
.block-container {{ padding-top: 1.5rem; padding-bottom: 1rem; }}

/* ── Layout: Streamlit-UI-Elemente ausblenden ── */
button[data-testid="stSidebarCollapseButton"],
button[data-testid="stSidebarNavCollapseButton"],
div[data-testid="stSidebarCollapsedControl"],
button[data-testid="baseButton-header"],
[data-testid="collapsedControl"] {{
    display: none !important;
    visibility: hidden !important;
}}
div[data-testid="stToolbar"] {{
    display: none !important;
}}
"""
