"""
views/pages/home.py — Das Unified Dashboard (Cockpit).

Die Kommandozentrale: Bündelt das Wichtigste aus allen Phasen auf einen Blick.
"""

import streamlit as st
from datetime import datetime

from data_cache import cached_vix, cached_sp500, cached_gold, cached_multi, _fmt_euro, _fmt_pct, _fmt_rsi, _color_change
from indicators import calc_fear_greed_components, fear_greed_label
from charts import plot_fear_greed_gauge
from services.watchlist import get_ticker_list, get_display_map, calc_portfolio_summary
from models.alerts import AlertStore
from models.journal import JournalStore
from services.economic_calendar import get_upcoming_events


def page_market():
    st.markdown("## 🕹️ Cockpit")
    st.caption("Dein High-Win-Rate Handelszentrum. Alle Systeme online.")

    # -----------------------------------------------------------------------
    # 1. Top Row: Quick Metrics 
    # -----------------------------------------------------------------------
    st.markdown("#### ⚡ System-Status")
    
    # Daten für Top-Widget besorgen
    # 1. Portfolio
    prices = {}
    try:
        from services.cache import cached_multi
        df_prices = cached_multi(",".join(get_ticker_list()) if get_ticker_list() else "AAPL")
        if df_prices is not None and not df_prices.empty:
            for idx, row in df_prices.iterrows():
                prices[row["Ticker"]] = row["Kurs (€)"]
    except Exception:
        pass
        
    portfolio = calc_portfolio_summary(prices)
    
    # 2. Alerts
    unack_alerts = AlertStore.get_triggered_unacknowledged()
    active_alerts = AlertStore.get_active()
    
    # 3. Macro Event
    upcoming_macro = None
    try:
        macro_events = get_upcoming_events()
        if macro_events:
            upcoming_macro = macro_events[0]
    except Exception:
        pass
        
    # 4. Journal Stats
    j_stats = JournalStore.get_statistics()
    
    # Widgets rendern
    w1, w2, w3, w4 = st.columns(4)
    
    with w1:
        with st.container(border=True):
            st.metric("Portfolio-Wert", f"{portfolio.get('total_value_eur', 0):,.2f} €", 
                      f"{portfolio.get('total_pnl_eur', 0):+,.2f} € Netto", 
                      delta_color="normal")
            
    with w2:
        with st.container(border=True):
            if unack_alerts:
                st.error(f"🚨 {len(unack_alerts)} Alarme feuerbereit!")
            else:
                st.metric("Signal-Wachhunde", f"{len(active_alerts)} aktiv", 
                          "Keine Auslösungen", delta_color="off")
                          
    with w3:
        with st.container(border=True):
            if upcoming_macro:
                label = upcoming_macro.name
                date_str = upcoming_macro.countdown_label
                st.metric("Nächstes Top-Event", label[:18] + ("..." if len(label)>18 else ""), 
                          date_str, delta_color="off")
            else:
                st.metric("Makro-Kalender", "Ruhig", "Keine Events", delta_color="off")
                
    with w4:
        with st.container(border=True):
            if j_stats and j_stats.get('total_closed', 0) > 0:
                st.metric("Eigene Trefferquote", f"{j_stats.get('win_rate', 0):.1f} %", 
                          f"aus {j_stats.get('total_closed')} Trades", delta_color="normal")
            else:
                st.metric("Trade-Journal", "Inaktiv", "Keine Historie", delta_color="off")


    st.markdown("---")

    # -----------------------------------------------------------------------
    # 2. Middle Row: Markt-Sentiment & AI Hit-Rate
    # -----------------------------------------------------------------------
    st.markdown("#### 🌡️ Markt-Metriken")
    c_left, c_right = st.columns([1, 1])
    
    with c_left:
        with st.container(border=True):
            vix = cached_vix()
            sp500 = cached_sp500()
            gold = cached_gold()
            if vix is not None and sp500 is not None:
                fg_data = calc_fear_greed_components(vix, sp500, gold)
                fg = fg_data["total"]
                lbl = fear_greed_label(fg)
                st.plotly_chart(plot_fear_greed_gauge(fg, lbl), use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Sentiment-Daten laden...")

    with c_right:
        with st.container(border=True):
            from services.cache import cached_hit_rate
            hit_rate = cached_hit_rate(90)
            if hit_rate and hit_rate.get("total", 0) > 0:
                st.markdown("**🎯 Maschinelle Signal-Trefferquote**")
                st.caption("Wie gut performt unser Confidence-Score aktuell (90T)?")
                
                evaluated = hit_rate.get("evaluated", 0)
                overall = hit_rate.get("overall_hit_rate")
                buy_rate = hit_rate.get("buy_hit_rate")
                
                if evaluated >= 5:
                    sc1, sc2 = st.columns(2)
                    sc1.metric("Trefferquote Gesamt", f"{overall:.1f}%")
                    sc2.metric("Nur Kaufsignale", f"{buy_rate:.1f}%")
                    st.caption(f"{evaluated} verifizierte Signale (>{7} Tage alt).")
                else:
                    st.info(f"Sammle Daten: {evaluated}/5 evaluierten Signalen.")
            else:
                 st.info("Noch keine algorithmischen Signale gesammelt.")

    st.markdown("---")

    # -----------------------------------------------------------------------
    # 3. Bottom Row: Watchlist Flow
    # -----------------------------------------------------------------------
    st.markdown("##### 📋 Watchlist Flow")
    tickers = get_ticker_list()
    if tickers:
        display_map = get_display_map()
        tickers_str = ", ".join(tickers)
        with st.spinner("Scanne Watchlist..."):
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
        st.info("Deine Watchlist ist leer. Gehe zu 'Analyse' um Ticker hinzuzufügen.")

    st.markdown("---")

    # -----------------------------------------------------------------------
    # 4. Alert Archiv (History)
    # -----------------------------------------------------------------------
    with st.expander("🗄️ Alert-Archiv (Historie)", expanded=False):
        import pandas as pd
        
        ach_alerts = AlertStore.get_acknowledged()
        if ach_alerts:
            # Als Tabelle rendern
            history_data = []
            for a in ach_alerts:
                history_data.append({
                    "Ausgelöst am": a.triggered_at if a.triggered_at else a.created_at,
                    "Ticker": a.ticker,
                    "Bedingung": f"{a.alert_type} ({a.threshold:.2f})",
                    "Kurs bei Trigger": f"{a.trigger_value:.2f}" if a.trigger_value else "Unbekannt"
                })
            df_hist = pd.DataFrame(history_data)
            st.dataframe(df_hist, use_container_width=True, hide_index=True)
            
            # Button zum kompletten Leeren des Archivs
            if st.button("🗑️ Archiv leeren", key="clear_archive_btn"):
                for a in ach_alerts:
                    AlertStore.delete_alert(a.id)
                st.rerun()
        else:
            st.info("Keine alten Alerts im Archiv.")
