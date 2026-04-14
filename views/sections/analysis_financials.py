"""Finanzdaten-Section: Gemeldete Quartalszahlen mit Umsatz, EBITDA, Nettogewinn."""
import streamlit as st
import pandas as pd
from views.components.charts import plot_financials_chart


def render_financials(details: dict, ticker: str):
    """Rendert die Finanzdaten-Tabelle mit YoY-Vergleichen."""
    fin_data = details.get("financials", [])
    if not fin_data:
        st.info("Für diese Aktie sind momentan keine detaillierten Finanzdaten verfügbar.")
        return

    st.markdown("#### Gemeldete Finanzzahlen")
    is_sec = any(str(item.get("year", "")).startswith("CY") for item in fin_data)
    source_text = "SEC EDGAR (Quarterly Company Facts)" if is_sec else "Yahoo Finance (offizielle Unternehmensmeldungen)"
    st.caption(f"Quelle: {source_text}")
    st.plotly_chart(
        plot_financials_chart(fin_data),
        use_container_width=True,
        config={"scrollZoom": False, "displayModeBar": False}
    )
    st.markdown("---")
    
    def _fmt_fin(val):
        if val is None or pd.isna(val): return "—"
        abs_val = abs(val)
        if abs_val >= 1e9: return f"{val/1e9:,.2f} Mrd. €"
        elif abs_val >= 1e6: return f"{val/1e6:,.2f} Mio. €"
        else: return f"{val:,.0f} €"
            
    def _fmt_yoy(val):
        if val is None or pd.isna(val): return ""
        color = "#22c55e" if val > 0 else "#ef4444"
        arrow = "▲" if val > 0 else "▼"
        return f"<span style='color:{color}; font-weight:bold;'>{arrow} {abs(val):.2f} %</span>"

    for item in fin_data:
        st.markdown(f"**{item['year']}**")
        
        f1, f2, f3 = st.columns([2, 2, 1])
        with f1: st.write("Umsatz")
        with f2: st.write(f"**{_fmt_fin(item['revenue'])}**")
        with f3: st.markdown(_fmt_yoy(item['revenue_yoy']), unsafe_allow_html=True)
        
        f4, f5, f6 = st.columns([2, 2, 1])
        with f4: st.write("EBITDA")
        with f5: st.write(f"**{_fmt_fin(item['ebitda'])}**")
        with f6: st.markdown(_fmt_yoy(item['ebitda_yoy']), unsafe_allow_html=True)
        
        f7, f8, f9 = st.columns([2, 2, 1])
        with f7: st.write("Nettogewinn")
        with f8: st.write(f"**{_fmt_fin(item['net_income'])}**")
        with f9: st.markdown(_fmt_yoy(item['net_income_yoy']), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
