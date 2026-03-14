import streamlit as st
from data_cache import cached_vix, cached_sp500, cached_gold, cached_multi, _fmt_euro, _fmt_pct, _fmt_rsi, _color_change
from indicators import calc_fear_greed_components, fear_greed_label
from charts import plot_fear_greed_gauge
from watchlist import get_ticker_list, get_display_map

def page_market():
    st.markdown("## Startseite")
    st.caption("Gesamtübersicht: Marktsentiment und Watchlist auf einen Blick")

    # Fear & Greed (5-Komponenten-Modell)
    vix = cached_vix()
    sp500 = cached_sp500()
    gold = cached_gold()
    if vix is not None and sp500 is not None:
        fg_data = calc_fear_greed_components(vix, sp500, gold)
        fg = fg_data["total"]
        lbl = fear_greed_label(fg)

        col_gauge, col_components = st.columns([2, 1])
        with col_gauge:
            st.plotly_chart(plot_fear_greed_gauge(fg, lbl), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        with col_components:
            st.markdown("##### Einzelkomponenten")
            for comp in fg_data["components"]:
                pct = comp["score"] / comp["max"] * 100
                color = "#22c55e" if pct >= 60 else ("#ef4444" if pct <= 40 else "#eab308")
                st.markdown(
                    f"**{comp['name']}** — {comp['score']:.0f}/{comp['max']}"
                    f"<br><span style='color:{color};font-size:0.75rem'>"
                    f"{comp['desc']}</span>",
                    unsafe_allow_html=True,
                )
            st.markdown("---")
            st.metric("VIX aktuell", f"{vix:.2f}")
    else:
        st.warning("Sentiment-Daten nicht verfügbar.")

    st.markdown("---")

    # Watchlist-Vorschau
    st.markdown("##### 📋 Watchlist-Vorschau")
    tickers = get_ticker_list()
    if tickers:
        display_map = get_display_map()
        tickers_str = ", ".join(tickers)
        with st.spinner("Lade Daten …"):
            df = cached_multi(tickers_str)
        if df is not None and not df.empty:
            if "Ticker" in df.columns:
                df["Ticker"] = df["Ticker"].map(lambda t: display_map.get(t, t))
            st.dataframe(
                df.style.format({
                    "Kurs (€)": _fmt_euro,
                    "Veränderung %": _fmt_pct,
                    "RSI (14)": _fmt_rsi,
                }).map(_color_change, subset=["Veränderung %"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Keine gültigen Ticker gefunden.")
    else:
        st.info("Füge Ticker über die Sidebar hinzu, um Daten zu sehen.")
