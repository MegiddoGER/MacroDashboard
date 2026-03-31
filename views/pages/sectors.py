import streamlit as st
import pandas as pd
from services.cache import cached_sectors
from views.components.charts import plot_sector_heatmap

def page_sectors():
    st.markdown("## Sektoren")
    st.caption("Sektor-Performance — welche Branchen führen den Markt?")

    # ── Region + Zeitraum ────────────────────────────────────────────
    col_region, col_spacer = st.columns([1, 3])
    with col_region:
        region = st.selectbox(
            "Markt",
            ["us", "eu"],
            format_func=lambda x: "🇺🇸 S&P 500" if x == "us" else "🇪🇺 STOXX Europe 600",
            key="sector_region",
        )

    region_title = "S&P 500" if region == "us" else "STOXX Europe 600"
    currency = "$" if region == "us" else "€"

    period_options = {
        "1d": "1 Tag", "1w": "1 Woche", "1m": "1 Month",
        "3m": "3 Monate", "ytd": "Seit Jahresanfang", "1y": "1 Jahr",
    }
    selected_period = st.radio(
        "Zeitraum",
        list(period_options.keys()),
        format_func=lambda x: period_options[x],
        horizontal=True,
        key="sector_period",
    )

    with st.spinner("Lade Sektor-Daten …"):
        sector_df = cached_sectors(selected_period, region)

    if sector_df is None or sector_df.empty:
        st.error("Sektor-Daten nicht verfügbar.")
        return

    # Heatmap (Treemap)
    selection = st.plotly_chart(
        plot_sector_heatmap(
            sector_df,
            f"{region_title} — Sektor-Heatmap — {period_options[selected_period]}"
        ),
        use_container_width=True,
        on_select="rerun",
        selection_mode="points",
    )

    # Click-Event Auswertung
    selected_sector = None
    if selection and "selection" in selection and "points" in selection["selection"]:
        pts = selection["selection"]["points"]
        if pts:
            idx = pts[0].get("point_index")
            if idx is not None and isinstance(idx, int) and idx < len(sector_df):
                selected_sector = sector_df.iloc[idx]["Sektor"]

    # Detailtabelle darunter
    st.markdown("---")
    st.markdown("##### 📋 Details")

    best = sector_df.iloc[0]
    worst = sector_df.iloc[-1]
    c1, c2 = st.columns(2)
    c1.metric(f"🏆 Bester Sektor: {best['Sektor']}",
              f"{best['Veränderung %']:+.2f} %")
    c2.metric(f"📉 Schwächster: {worst['Sektor']}",
              f"{worst['Veränderung %']:+.2f} %")

    st.dataframe(
        sector_df[["Sektor", "Ticker", "Kurs", "Veränderung %"]].style.format({
            "Kurs": "{:,.2f} " + currency,
            "Veränderung %": "{:+.2f} %",
        }).map(
            lambda v: "color: #22c55e" if isinstance(v, (int, float)) and v > 0
            else ("color: #ef4444" if isinstance(v, (int, float)) and v < 0 else ""),
            subset=["Veränderung %"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    if region == "us":
        st.caption("Daten: S&P 500 Sektor-ETFs (SPDR) + ITA (Rüstung). "
                   "Technologie = XLK, Finanzen = XLF, Rüstung = ITA usw.")
    else:
        st.caption("Daten: STOXX Europe 600 Sektor-ETFs (iShares). "
                   "Gehandelt an der Xetra-Börse.")

    # ── Sektor Drilldown (Top/Flop Aktien) ───────────────────────────
    if selected_sector and region == "us":
        from services.cache import cached_sp500_components, cached_components_performance
        
        # Mapping von deutschen Sektornamen auf GICS (Wikipedia S&P 500)
        gics_map = {
            "Technologie": ("GICS Sector", "Information Technology"),
            "Finanzen": ("GICS Sector", "Financials"),
            "Energie": ("GICS Sector", "Energy"),
            "Gesundheit": ("GICS Sector", "Health Care"),
            "Zyklischer Konsum": ("GICS Sector", "Consumer Discretionary"),
            "Basiskonsum": ("GICS Sector", "Consumer Staples"),
            "Industrie": ("GICS Sector", "Industrials"),
            "Grundstoffe": ("GICS Sector", "Materials"),
            "Immobilien": ("GICS Sector", "Real Estate"),
            "Kommunikation": ("GICS Sector", "Communication Services"),
            "Versorger": ("GICS Sector", "Utilities"),
            "Rüstung & Luftfahrt": ("GICS Sub-Industry", "Aerospace & Defense"),
        }
        
        match_info = gics_map.get(selected_sector)
        if match_info:
            col, expected_val = match_info
            st.markdown("---")
            st.markdown(f"#### Sektor Drilldown: {selected_sector}")
            
            with st.spinner(f"Lade Aktien für {selected_sector} …"):
                components_df = cached_sp500_components()
                
            if components_df is not None and not components_df.empty:
                sector_stocks = components_df[components_df[col] == expected_val]
                symbols = sector_stocks["Symbol"].tolist()
                
                if symbols:
                    with st.spinner(f"Lade Performance-Daten (Zeitraum: {period_options[selected_period]}) …"):
                        perf_df = cached_components_performance(",".join(symbols), selected_period)
                    
                    if perf_df is not None and not perf_df.empty:
                        # Join with names
                        perf_df = perf_df.merge(components_df[["Symbol", "Security"]], 
                                                left_on="Ticker", right_on="Symbol", how="left")
                        perf_df.rename(columns={"Security": "Unternehmen"}, inplace=True)
                        
                        top5 = perf_df.head(5)
                        flop5 = perf_df.tail(5).sort_values("Veränderung %", ascending=True)
                        
                        tc1, tc2 = st.columns(2)
                        with tc1:
                            st.markdown(f"##### 🟢 Stärkste Treiber")
                            st.dataframe(
                                top5[["Ticker", "Unternehmen", "Veränderung %"]].style.format({
                                    "Veränderung %": "{:+.2f} %"
                                }).map(
                                    lambda v: "color: #22c55e", subset=["Veränderung %"]
                                ),
                                use_container_width=True, hide_index=True
                            )
                        with tc2:
                            st.markdown(f"##### 🔴 Schwächste Treiber")
                            st.dataframe(
                                flop5[["Ticker", "Unternehmen", "Veränderung %"]].style.format({
                                    "Veränderung %": "{:+.2f} %"
                                }).map(
                                    lambda v: "color: #ef4444" if isinstance(v, (int, float)) and v < 0 else "",
                                    subset=["Veränderung %"]
                                ),
                                use_container_width=True, hide_index=True
                            )
                        st.caption("Performance-Daten via S&P 500 Komponenten (ausgeschlossen Dividenden, rein kurswirksam).")
                    else:
                        st.warning("Konnte Performance-Daten der Einzelwerte nicht abrufen.")
                else:
                    st.info(f"Keine Einzelwerte für {selected_sector} gefunden.")
            else:
                st.warning("Konnte S&P 500 Komponenten nicht abrufen.")
    elif selected_sector and region == "eu":
        st.markdown("---")
        st.info(f"Sektor Drilldown für **{selected_sector} (Europa)** wird momentan nicht unterstützt, da die genauen STOXX 600 Komponenten nicht frei per API abrufbar sind.")
