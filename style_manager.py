"""
style_manager.py — Komponiert und injiziert alle Baustein-Styles.

Jeder UI-Baustein (Sidebar, Buttons, Metriken, etc.) hat sein eigenes
Modul unter styles/. Diese Datei fügt sie zu einem Gesamtstylesheet zusammen.

Architektur:
  styles/theme.py     → Zentrale Design-Tokens (Farben, Fonts, Abstände)
  styles/layout.py    → App-Hintergrund, Typografie, Block-Container
  styles/sidebar.py   → Sidebar-Container, Navigation (Glow), Logo
  styles/metrics.py   → Metrik-Karten (st.metric)
  styles/tables.py    → DataFrames / Tabellen
  styles/tabs.py      → Streamlit-Tabs
  styles/inputs.py    → Selectboxen, Text-Inputs
  styles/charts.py    → Plotly Modebar
  styles/buttons.py   → Alle Button-Varianten (5 Typen)
"""

import streamlit as st

from styles.layout import css_layout
from styles.sidebar import css_sidebar, css_sidebar_nav, css_sidebar_logo
from styles.metrics import css_metrics
from styles.tables import css_tables
from styles.tabs import css_tabs
from styles.inputs import css_inputs
from styles.charts import css_charts
from styles.buttons import css_buttons


def apply_custom_styles():
    """Injiziert das vollständige, zusammengesetzte Stylesheet."""
    combined_css = "\n".join([
        css_layout(),
        css_sidebar(),
        css_sidebar_nav(),
        css_sidebar_logo(),
        css_metrics(),
        css_tables(),
        css_tabs(),
        css_inputs(),
        css_charts(),
        css_buttons(),
    ])

    st.markdown(f"<style>{combined_css}</style>", unsafe_allow_html=True)
