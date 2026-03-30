"""
views/pages/journal.py — Das Trade-Journal (Lernmaschine).

Verwaltung und Auswertung (Post-Trade Review) eigener Trades.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from models.journal import TradeEntry, JournalStore


def page_journal():
    st.markdown("## 📓 Trade-Journal")
    st.caption("Deine Lernmaschine: Tracke deine Trades, bewerte Setups und finde heraus, was für dich funktioniert.")
    
    # Session State fürs Modal-Handling (Schließen eines Trades)
    if "journal_close_id" not in st.session_state:
        st.session_state.journal_close_id = None
        
    trades = JournalStore.get_all()
    open_trades = [t for t in trades if t.status == "Offen"]
    closed_trades = [t for t in trades if t.status != "Offen"]
    
    tab_new, tab_open, tab_closed, tab_stats, tab_ai = st.tabs([
        "➕ Neuer Eintrag", 
        f"📂 Offen ({len(open_trades)})", 
        f"✅ Historie ({len(closed_trades)})", 
        "📈 Setup-Statistiken",
        "🤖 System-Signale (AI)"
    ])
    
    # -----------------------------------------------------------------------
    # Tab 1: Neuer Eintrag
    # -----------------------------------------------------------------------
    with tab_new:
        with st.form("new_trade_form"):
            c1, c2, c3 = st.columns(3)
            ticker = c1.text_input("Ticker", placeholder="z.B. AAPL").upper()
            trade_type = c2.selectbox("Richtung", ["Long", "Short"])
            entry_date = c3.date_input("Kaufdatum")
            
            c4, c5, c6 = st.columns(3)
            entry_price = c4.number_input("Einstiegskurs (€)", min_value=0.01, format="%.2f", step=0.1)
            setup_type = c5.selectbox(
                "Setup-Kategorie", 
                ["SMC (Fair Value Gap)", "Trendfolge (Pullback)", "Breakout", "Mean Reversion (Oversold)", "Earnings Play"]
            )
            conviction = c6.slider("Überzeugung (Conviction)", 1, 5, 3, help="Wie stark war das Setup?")
            
            notes = st.text_area("Kaufgrund / Notes", placeholder="Z.B.: RSI überverkauft, bullische Marktstruktur und starkes OBV...")
            
            submitted = st.form_submit_button("📓 Trade speichern", type="primary")
            
            if submitted:
                if not ticker:
                    st.error("Bitte einen Ticker eingeben.")
                elif entry_price <= 0:
                    st.error("Der Einstiegskurs muss > 0 sein.")
                else:
                    new_trade = TradeEntry(
                        ticker=ticker,
                        trade_type=trade_type,
                        setup_type=setup_type,
                        entry_date=entry_date.strftime("%Y-%m-%d"),
                        entry_price=entry_price,
                        conviction=conviction,
                        entry_notes=notes,
                        status="Offen"
                    )
                    JournalStore.save(new_trade)
                    st.success(f"Trade für {ticker} wurde gespeichert!")
                    st.rerun()

    # -----------------------------------------------------------------------
    # Tab 2: Offene Trades
    # -----------------------------------------------------------------------
    with tab_open:
        if not open_trades:
            st.info("Keine offenen Trades im Journal.")
        else:
            for t in open_trades:
                with st.container(border=True):
                    sc1, sc2, sc3, sc4 = st.columns([1, 1.5, 3, 1])
                    with sc1:
                        st.markdown(f"**{t.ticker}**")
                        color = "#22c55e" if t.trade_type == "Long" else "#ef4444"
                        st.markdown(f"<span style='color:{color}; font-weight:bold;'>{t.trade_type}</span>", unsafe_allow_html=True)
                    with sc2:
                        st.caption(f"Einstieg: {t.entry_price:,.2f} €")
                        st.caption(f"Datum: {t.entry_date}")
                    with sc3:
                        st.caption(f"Setup: **{t.setup_type}** | Conviction: {'⭐' * t.conviction}")
                        if t.entry_notes:
                            st.caption(f"Grund: {t.entry_notes}")
                    with sc4:
                        if st.button("Schließen / Review", key=f"close_btn_{t.id}"):
                            st.session_state.journal_close_id = t.id
                            st.rerun()
                            
    # "Lern-Modal": Wird rendernt wenn ein Trade geschlossen werden soll
    if st.session_state.journal_close_id:
        # Finde den Trade
        close_t = next((t for t in open_trades if t.id == st.session_state.journal_close_id), None)
        if close_t:
            st.markdown("---")
            st.markdown(f"#### 📝 Review für {close_t.ticker} ({close_t.trade_type}) schreiben")
            with st.form("close_trade_form"):
                cc1, cc2 = st.columns(2)
                exit_price = cc1.number_input("Ausstiegskurs (€)", min_value=0.01, format="%.2f", step=0.1)
                exit_date = cc2.date_input("Verkaufsdatum")
                
                # Vorab Berechnung PnL für UI
                if exit_price > 0:
                    delta = exit_price - close_t.entry_price
                    pct = (delta / close_t.entry_price) * 100
                    if close_t.trade_type == "Short":
                        delta = -delta
                        pct = -pct
                else:
                    delta = 0.0
                    pct = 0.0
                
                status_opts = ["Gewonnen", "Verloren", "Break-Even"]
                default_idx = 0 if pct > 0 else (1 if pct < -0.5 else 2)
                status = cc1.selectbox("Ergebnis", status_opts, index=default_idx)
                
                review_notes = st.text_area("Post-Trade Review", placeholder="Was hast du gelernt? Hast du dich an die Regeln gehalten?")
                
                sumbitted_close = st.form_submit_button("✅ Trade abschließen", type="primary")
                cancel_close = st.form_submit_button("Abbrechen")
                
                if sumbitted_close:
                    if exit_price <= 0:
                        st.error("Ausstiegskurs ungültig.")
                    else:
                        calcd_delta = exit_price - close_t.entry_price
                        calcd_pct = (calcd_delta / close_t.entry_price) * 100
                        if close_t.trade_type == "Short":
                            calcd_delta = -calcd_delta
                            calcd_pct = -calcd_pct
                            
                        # Hier nehmen wir PnL in Prozent als Euro-Proxy (da EntryPrice pro Aktie) 
                        # Für echtes Portfolio-Tracking nutzen wir die Watchlist. Hier geht es um Prozent.
                        JournalStore.close_trade(
                            close_t.id, exit_price, exit_date.strftime("%Y-%m-%d"),
                            status, calcd_delta, calcd_pct, review_notes
                        )
                        st.session_state.journal_close_id = None
                        st.success("Trade geschlossen und Review gespeichert!")
                        st.rerun()
                        
                if cancel_close:
                    st.session_state.journal_close_id = None
                    st.rerun()

    # -----------------------------------------------------------------------
    # Tab 3: Historie
    # -----------------------------------------------------------------------
    with tab_closed:
        if not closed_trades:
            st.info("Noch keine geschlossenen Trades.")
        else:
            for t in closed_trades:
                color = "#22c55e" if t.status == "Gewonnen" else ("#ef4444" if t.status == "Verloren" else "#94a3b8")
                with st.container(border=True):
                    rc1, rc2, rc3 = st.columns([1, 2, 3])
                    with rc1:
                        st.markdown(f"**{t.ticker}** ({t.trade_type})")
                        st.markdown(f"<span style='color:{color}; font-weight:bold;'>{t.status}</span>", unsafe_allow_html=True)
                        st.caption(f"{t.pnl_pct:+.1f}%")
                    with rc2:
                        st.caption(f"Entry: {t.entry_date} @ {t.entry_price:,.2f} €")
                        st.caption(f"Exit: {t.exit_date} @ {t.exit_price:,.2f} €")
                    with rc3:
                        st.caption(f"Setup: **{t.setup_type}** | Conviction: {'⭐' * t.conviction}")
                        if t.review_notes:
                            st.info(f"💡 {t.review_notes}")
                    
                    if st.button("🗑️", key=f"del_btn_{t.id}", help="Eintrag löschen"):
                        JournalStore.delete_trade(t.id)
                        st.rerun()

    # -----------------------------------------------------------------------
    # Tab 4: Setup-Statistiken
    # -----------------------------------------------------------------------
    with tab_stats:
        stats = JournalStore.get_statistics()
        if not stats or stats.get("total_closed", 0) == 0:
            st.info("Noch nicht genug geschlossene Trades vorhanden, um Statistiken zu generieren.")
        else:
            st.markdown("### 🏆 Mein Performance-Report")
            st.caption("Finde heraus, bei welchen Strategien du den größten statistischen Vorteil (Edge) hast.")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Geschlossene Trades", stats["total_closed"])
            c2.metric("Win-Rate", f"{stats['win_rate']:.1f}%")
            c3.metric("Gewonnen / Verloren", f"{stats['win_count']} / {stats['loss_count']}")
            c4.metric("Offene Trades", stats["total_open"])
            
            st.markdown("---")
            st.markdown("#### Win-Rate pro Setup-Typ")
            
            # Daten für Plotly aufbereiten
            setup_list = []
            for s_type, s_data in stats["setup_stats"].items():
                setup_list.append({
                    "Setup": s_type,
                    "Total": s_data["total"],
                    "Win Rate (%)": s_data["win_rate"],
                    "Wins": s_data["wins"],
                })
                
            df_stats = pd.DataFrame(setup_list)
            
            if not df_stats.empty:
                import plotly.express as px
                fig = px.bar(
                    df_stats, x="Win Rate (%)", y="Setup", orientation='h',
                    color="Win Rate (%)", color_continuous_scale="RdYlGn",
                    text_auto=True, title="Trefferquote nach Strategie"
                )
                fig.update_layout(
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(range=[0, 100]), yaxis=dict(categoryorder="total ascending")
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                
                st.dataframe(df_stats, use_container_width=True, hide_index=True)


    # -----------------------------------------------------------------------
    # Tab 5: System-Signale (AI)
    # -----------------------------------------------------------------------
    with tab_ai:
        from services.signal_history import calc_calibration_chart, get_signal_statistics
        
        st.markdown("### 🤖 Signal-Performance Deep-Dive")
        st.caption("Auswertung der automatisiert generierten Scoring-Signale (Maschinelle Trefferquote).")
        st.markdown("---")
        
        ai_stats = get_signal_statistics()
        if ai_stats.get("evaluated_signals", 0) == 0:
            st.info("Noch nicht genügend evaluierte Signale vorhanden (braucht min. 7 Tage Historie nach Signal-Generierung).")
        else:
            # Row 1: Metriken
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Evaluierte Signale", ai_stats["evaluated_signals"])
            a2.metric("Ausstehende Signale", ai_stats["pending_signals"])
            a3.metric("∅ Confidence Score", f"{ai_stats['avg_confidence']:.1f}")
            if ai_stats["best_ticker"]:
                a4.metric("Bester Ticker", f"{ai_stats['best_ticker'][0]}", f"{ai_stats['best_ticker'][1]}% Win")
            
            st.markdown("#### 🎯 Score Breakdown (Trefferquote nach Confidence)")
            calib = calc_calibration_chart()
            if calib:
                import plotly.express as px
                df_calib = pd.DataFrame(calib)
                # Filtern wo hit_rate nicht None ist
                df_calib = df_calib.dropna(subset=['hit_rate'])
                
                if not df_calib.empty:
                    fig_cal = px.bar(
                        df_calib, x="bucket", y="hit_rate",
                        color="hit_rate", color_continuous_scale="RdYlGn",
                        text="hit_rate", title="Win-Rate nach Score-Bereichen (%)",
                        labels={"bucket": "Confidence-Score Bereich", "hit_rate": "Win-Rate (%)"}
                    )
                    fig_cal.update_traces(texttemplate='%{text:.1f}%', textposition='auto')
                    fig_cal.update_layout(
                        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        yaxis=dict(range=[0, 100])
                    )
                    st.plotly_chart(fig_cal, use_container_width=True, config={"displayModeBar": False})

            # Row 3: Top/Flop Signale
            st.markdown("#### 🏆 Top & Flop AI-Signale")
            tf1, tf2 = st.columns(2)
            with tf1:
                st.markdown("##### Beste Calls")
                top_sigs = ai_stats.get("top_signals", [])
                for s in top_sigs:
                    c = "🟢" if s['type'] == 'buy' else "🔴"
                    st.success(f"{c} **{s['ticker']}** ({s['type'].upper()} @ {s['confidence']:.0f}%) ➔ **{s['return_pct']:+.1f}%**")
                    
            with tf2:
                st.markdown("##### Schlechteste Calls")
                flop_sigs = ai_stats.get("flop_signals", [])
                for s in flop_sigs:
                    c = "🟢" if s['type'] == 'buy' else "🔴"
                    st.error(f"{c} **{s['ticker']}** ({s['type'].upper()} @ {s['confidence']:.0f}%) ➔ **{s['return_pct']:+.1f}%**")
