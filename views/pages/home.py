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

    # ── Signal-Trefferquote (Letzte 90 Tage) ─────────────────────────
    from services.cache import cached_hit_rate
    from services.signal_history import update_stale_signals, cleanup_old_signals

    # Hintergrund-Tasks (nicht blockierend)
    try:
        cleanup_old_signals()
        update_stale_signals()
    except Exception:
        pass

    hit_rate = cached_hit_rate(90)
    if hit_rate and hit_rate.get("total", 0) > 0:
        st.markdown("##### 🎯 Signal-Trefferquote (Letzte 90 Tage)")
        
        evaluated = hit_rate.get("evaluated", 0)
        overall = hit_rate.get("overall_hit_rate")
        buy_rate = hit_rate.get("buy_hit_rate")
        
        if evaluated >= 5:
            hc1, hc2, hc3, hc4 = st.columns(4)
            with hc1:
                st.metric("Trefferquote (Gesamt)", f"{overall:.1f}%" if overall is not None else "—",
                          help="Prozentzahl aller Signale (Kaufen/Verkaufen), die nach 1 Monat im Plus (Kaufen) oder im Minus (Verkaufen) waren.")
            with hc2:
                st.metric("Trefferquote (Käufe)", f"{buy_rate:.1f}%" if buy_rate is not None else "—",
                          help=f"Gewonnene Kaufsignale: {hit_rate.get('buy_wins', 0)} / {hit_rate.get('buy_signals_count', 0)}")
            with hc3:
                st.metric("Evaluierte Signale", f"{evaluated}",
                          help="Anzahl der Signale, deren Zeitablauf > 7 Tage ist (mind. 1W Resultat existiert).")
            with hc4:
                pending = hit_rate.get('total', 0) - evaluated
                st.metric("Ausstehende Signale", f"{pending}",
                          help="Signale, die noch zu frisch für eine Bewertung sind (< 7 Tage).")
        else:
            st.info(f"📊 Sammle noch Daten zur Trefferquote. {evaluated} von 5 nötigen evaluierten Signalen vorhanden.")
            
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
