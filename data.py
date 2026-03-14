"""
data.py — Backward-Compatibility-Shim.

Leitet alle Importe an services.market_data und services.news weiter.
Externe Skripte, die `from data import …` verwenden, funktionieren weiterhin.
"""

from services.market_data import *  # noqa: F401,F403
from services.news import *  # noqa: F401,F403
