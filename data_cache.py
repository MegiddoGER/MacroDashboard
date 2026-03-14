"""
data_cache.py — Backward-Compatibility-Shim.

Leitet alle Importe an services.cache, views.components.formatters
und views.components.news_list weiter.
"""

from services.cache import *  # noqa: F401,F403
from views.components.formatters import (  # noqa: F401
    fmt_euro, fmt_pct, fmt_rsi, color_change,
    _fmt_euro, _fmt_pct, _fmt_rsi, _color_change,
    fmt_big, fmt_balance,
)
from views.components.news_list import render_news_list, _render_news_list  # noqa: F401
