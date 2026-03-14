"""
services/smc.py — Re-Export des SMC-Subpakets.

Dient als einheitlicher Zugriffspunkt für SMC-Indikatoren und -Charts.
"""

from smc.indicators import analyze_smc
from smc.charts import plot_smc

__all__ = ["analyze_smc", "plot_smc"]
