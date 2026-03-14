"""
views/components/formatters.py — Einheitliche Format-Helper für die UI.
"""

import pandas as pd


def fmt_euro(v):
    """Formatiert einen Wert als Euro-Betrag."""
    return f"{v:,.2f} €" if pd.notna(v) else "—"


def fmt_pct(v):
    """Formatiert einen Wert als Prozent mit Vorzeichen."""
    return f"{v:+.2f} %" if pd.notna(v) else "—"


def fmt_rsi(v):
    """Formatiert einen RSI-Wert."""
    return f"{v:.1f}" if pd.notna(v) else "—"


def color_change(v):
    """Gibt CSS-Farbstil für positive/negative Werte zurück."""
    if isinstance(v, (int, float)):
        if v > 0: return "color: #22c55e"
        elif v < 0: return "color: #ef4444"
    return ""


def fmt_big(val):
    """Formatiert große Zahlen (Mrd., Mio., Bio.)."""
    if val >= 1e12: return f"{val/1e12:.1f} Bio."
    if val >= 1e9: return f"{val/1e9:.1f} Mrd."
    if val >= 1e6: return f"{val/1e6:.1f} Mio."
    return f"{val:,.0f}"


def fmt_balance(val):
    """Formatiert Bilanzwerte."""
    if abs(val) >= 1e9: return f"{val/1e9:.1f} Mrd. €"
    if abs(val) >= 1e6: return f"{val/1e6:.1f} Mio. €"
    return f"{val:,.0f} €"


# Rückwärtskompatible Aliase (mit Unterstrich-Prefix wie im Original)
_fmt_euro = fmt_euro
_fmt_pct = fmt_pct
_fmt_rsi = fmt_rsi
_color_change = color_change
