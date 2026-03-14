"""
styles/buttons.py — Styles für alle Button-Varianten.
"""

from styles.theme import COLORS, TRANSITION


def css_buttons() -> str:
    return f"""
/* ═════════════════════════════════════════
   Buttons — via :has() CSS pro Variante
   ═════════════════════════════════════════ */

/* ── Button: System Beenden (Rot) ── */
div[data-testid="stElementContainer"]:has(.marker-btn-quit) + div[data-testid="stElementContainer"] button {{
    background-color: {COLORS["danger"]} !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.4) !important;
    box-shadow: 0 0 8px rgba(255, 255, 255, 0.4) !important;
    transition: {TRANSITION["normal"]};
    font-weight: 600 !important;
    letter-spacing: 0.5px;
}}
div[data-testid="stElementContainer"]:has(.marker-btn-quit) + div[data-testid="stElementContainer"] button:hover {{
    background-color: {COLORS["danger_hover"]} !important;
    border: 1px solid rgba(255, 255, 255, 0.8) !important;
    box-shadow: 0 0 14px rgba(255, 255, 255, 0.8) !important;
    transform: scale(1.02);
}}

/* ── Button: Hinzufügen (Grün) ── */
div[data-testid="stElementContainer"]:has(.marker-btn-add) + div[data-testid="stElementContainer"] button {{
    background-color: rgba(34, 197, 94, 0.15) !important;
    border: 1px solid rgba(34, 197, 94, 0.4) !important;
    color: {COLORS["success"]} !important;
    transition: {TRANSITION["fast"]};
}}
div[data-testid="stElementContainer"]:has(.marker-btn-add) + div[data-testid="stElementContainer"] button:hover {{
    background-color: rgba(34, 197, 94, 0.25) !important;
    border-color: {COLORS["success"]} !important;
}}

/* ── Button: Alle Daten Aktualisieren (Lila) ── */
div[data-testid="stElementContainer"]:has(.marker-btn-refresh) + div[data-testid="stElementContainer"] button {{
    background-color: {COLORS["purple"]} !important;
    color: #ffffff !important;
    border: 1px solid rgba(168, 85, 247, 0.8) !important;
    font-weight: 600 !important;
    transition: {TRANSITION["fast"]};
}}
div[data-testid="stElementContainer"]:has(.marker-btn-refresh) + div[data-testid="stElementContainer"] button:hover {{
    background-color: #9333ea !important;
    color: #ffffff !important;
    box-shadow: 0 0 10px rgba(147, 51, 234, 0.5) !important;
}}
    
/* ── Button: Reset ❌ (Analyse) ── */
div.stButton button:has(div:contains("❌")) {{
    background-color: transparent !important;
    border: 1px solid rgba(239, 68, 68, 0.3) !important;
    color: {COLORS["red"]} !important;
    border-radius: 8px !important;
    padding: 2px !important;
    transition: {TRANSITION["fast"]};
}}
div.stButton button:has(div:contains("❌")):hover {{
    background-color: rgba(239, 68, 68, 0.15) !important;
    border-color: {COLORS["red"]} !important;
    box-shadow: 0 0 8px rgba(239, 68, 68, 0.3) !important;
}}

/* ── Button: Watchlist Entfernen ✕ ── */
div[data-testid="stElementContainer"]:has(.marker-btn-delete) + div[data-testid="stElementContainer"] button {{
    background: transparent !important;
    border: none !important;
    color: {COLORS["text_muted"]} !important;
    font-weight: bold;
    padding: 0 !important;
    min-height: auto !important;
}}
div[data-testid="stElementContainer"]:has(.marker-btn-delete) + div[data-testid="stElementContainer"] button:hover {{
    color: {COLORS["red"]} !important;
    transform: scale(1.1);
}}
"""
