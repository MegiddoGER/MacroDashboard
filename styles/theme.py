"""
styles/theme.py — Zentrale Design-Tokens (Farben, Schriften, Abstände).

Alle Komponenten-Styles importieren ihre Tokens von hier.
Änderungen hier wirken sich auf das gesamte Dashboard aus.
"""


# ── Farbpalette ──────────────────────────────────────────────────────────

COLORS = {
    # Hintergrund
    "bg_app_start":      "#0a0f1a",
    "bg_app_mid":        "#0f172a",
    "bg_app_end":        "#111827",
    "bg_card":           "rgba(15, 23, 42, 0.55)",
    "bg_sidebar":        "rgba(10, 15, 26, 0.95)",
    "bg_sidebar_solid":  "rgba(10, 15, 26, 1)",

    # Bordüren
    "border":            "rgba(148, 163, 184, 0.10)",
    "border_subtle":     "rgba(148, 163, 184, 0.15)",

    # Text
    "text":              "#e2e8f0",
    "text_secondary":    "#cbd5e1",
    "text_dim":          "#94a3b8",
    "text_muted":        "#64748b",

    # Akzent-Farben
    "accent":            "#00d4aa",
    "accent_glow":       "rgba(0, 212, 170, 0.6)",

    # Status-Farben
    "green":             "#22c55e",
    "red":               "#ef4444",
    "yellow":            "#eab308",
    "blue":              "#3b82f6",
    "purple":            "#a855f7",
    "sky":               "#87CEEB",

    # Semantische Farben
    "danger":            "#e11d48",
    "danger_hover":      "#be123c",
    "success":           "#22c55e",
}


# ── Navigations-Glow-Farben (je Menüpunkt) ──────────────────────────────

NAV_GLOW_COLORS = [
    {"color": "#3b82f6", "rgb": "59, 130, 246"},    # 1  Startseite — Blau
    {"color": "#10b981", "rgb": "16, 185, 129"},     # 2  Gesamtwirtschaft — Grün
    {"color": "#f59e0b", "rgb": "245, 158, 11"},     # 3  Watchlist — Amber
    {"color": "#a855f7", "rgb": "168, 85, 247"},     # 4  Screener — Violett
    {"color": "#ec4899", "rgb": "236, 72, 153"},     # 5  Analyse — Pink
    {"color": "#f97316", "rgb": "249, 115, 22"},     # 6  Backtesting — Orange
    {"color": "#eab308", "rgb": "234, 179, 8"},      # 7  Trade-Journal — Gelb
    {"color": "#14b8a6", "rgb": "20, 184, 166"},     # 8  Sektoren — Teal
    {"color": "#06b6d4", "rgb": "6, 182, 212"},      # 9  Analyse-Lexikon — Cyan
    {"color": "#94a3b8", "rgb": "148, 163, 184"},    # 10 Aktien-Verzeichnis — Grau
]


# ── Typografie ───────────────────────────────────────────────────────────

FONT = {
    "family":            "'Inter', sans-serif",
    "import_url":        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    "icon_family":       '"Material Symbols Rounded", "Material Icons", sans-serif',
    "weight_regular":    400,
    "weight_medium":     500,
    "weight_semibold":   600,
    "weight_bold":       700,
}


# ── Abstände & Radien ────────────────────────────────────────────────────

SPACING = {
    "radius_sm":         "8px",
    "radius_md":         "10px",
    "radius_lg":         "12px",
    "padding_card":      "14px 18px",
    "padding_nav":       "12px 16px",
    "sidebar_width":     "21rem",
}


# ── Transitions ──────────────────────────────────────────────────────────

TRANSITION = {
    "fast":              "all 0.2s ease",
    "normal":            "all 0.3s ease",
    "slow":              "all 0.4s ease",
}
