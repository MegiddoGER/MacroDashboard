"""
views/pages/backtesting.py — Strategy Backtesting Engine Dashboard.

Ermöglicht das Validieren von Trading-Strategien gegen die historische Kursentwicklung.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

from services.cache import cached_stock_history
from services.watchlist import resolve_ticker
from services.backtesting import BacktestEngine


def page_backtesting():
    st.markdown("## 📈 Strategy Backtesting Engine")
    st.caption("Validiere algorithmische Strategien mit realen Marktdaten (inklusive Gebühren & Slippage).")
    
    # -----------------------------------------------------------------------
    # Parameter Formular
    # -----------------------------------------------------------------------
    with st.expander("⚙️ Backtest Konfiguration", expanded=True):
        f_c1, f_c2, f_c3 = st.columns(3)
        input_ticker = f_c1.text_input("Ticker Symbol", "AAPL", key="bt_ticker").upper()
        
        strategies = {
            "RSI_Mean_Reversion": "RSI Mean Reversion (Oszillator)",
            "SMA_Cross_Trend": "SMA Golden Cross (Trendfolge)",
            "MACD_Momentum": "MACD Crossover (Momentum)",
            "Bollinger_Breakout": "Bollinger Bands Breakout (Volatilität)",
            "SMC_FVG_Bounce": "Smart Money Concept: FVG Bounce (Proxy)"
        }
        
        strat_key = f_c2.selectbox("Handelsstrategie", options=list(strategies.keys()), format_func=lambda x: strategies[x])
        period = f_c3.selectbox("Zeitraum", ["1y", "2y", "5y", "max"], index=2)
        
        st.markdown("###### Kosten & Parameter")
        p_c1, p_c2, p_c3 = st.columns(3)
        init_capital = p_c1.number_input("Startkapital (€)", value=10000.0, step=1000.0)
        
        cost_models = {
            "Trade Republic / Scalable": 1.0,
            "Interactive Brokers": 2.5,
            "Comdirect / Consors": 9.90,
            "Kostenlos (Theoretisch)": 0.0
        }
        
        selected_model = p_c2.selectbox("Ordergebühr (Broker)", list(cost_models.keys()))
        commission = cost_models[selected_model]
        
        slippage = p_c3.number_input("Slippage (%)", value=0.1, step=0.05, format="%.2f",
             help="Kursverschlechterung durch Lücke zwischen Signal und Ausführung (Ask/Bid Spread).")
             
        run_btn = st.button("🚀 Backtest Starten", type="primary", use_container_width=True)

    st.markdown("---")

    # -----------------------------------------------------------------------
    # Backtest Ausführung
    # -----------------------------------------------------------------------
    if run_btn:
        resolved = resolve_ticker(input_ticker)
        ticker = resolved["ticker"] if resolved else input_ticker
        
        with st.spinner(f"Lade feingranulare Kaskaden-Daten für {ticker} ({period})..."):
            hist = cached_stock_history(ticker, period)
            
        if hist is None or hist.empty or len(hist) < 200:
            st.error(f"Nicht genug historische Daten für {ticker} verfügbar. Versuche einen längeren Zeitraum oder anderen Ticker.")
            return
            
        with st.spinner("Berechne vektorisierten Backtest..."):
            engine = BacktestEngine(hist, init_capital, commission, slippage)
            try:
                equity_df, trades, metrics = engine.run_strategy(strat_key)
            except ValueError as e:
                st.error(str(e))
                return

        # -------------------------------------------------------------------
        # Ergebnisse
        # -------------------------------------------------------------------
        st.markdown(f"#### 📊 Resultate: {strategies[strat_key]} auf **{ticker}**")
        
        # Dashboard Metriken
        m1, m2, m3, m4, m5 = st.columns(5)
        
        m1.metric("Endkapital", f"€ {metrics['final_capital']:,.2f}", 
                  f"Start: € {init_capital:,.2f}", delta_color="off")
                  
        total_ret = metrics['total_return_pct']
        bench_ret = metrics['benchmark_return_pct']
        diff = total_ret - bench_ret
        
        m2.metric("Rendite (Netto)", f"{total_ret:+.2f} %", 
                  f"{diff:+.2f} % vs Buy&Hold", delta_color="normal" if diff > 0 else "inverse")
                  
        m3.metric("Win-Rate", f"{metrics['win_rate']:.1f} %", 
                  f"{metrics['total_trades']} Trades total", delta_color="off")
                  
        profit_factor = metrics['profit_factor']
        m4.metric("Profit-Faktor", f"{profit_factor:.2f}",
                  "Zählt als exzellent" if profit_factor > 2.0 else ("Gut" if profit_factor > 1.2 else "Schwach"), 
                  delta_color="normal" if profit_factor > 1.5 else ("inverse" if profit_factor < 1.0 else "off"))
                  
        dd = metrics['max_drawdown_pct']
        m5.metric("Max Drawdown", f"{dd:.1f} %", 
                  help="Maximaler prozentualer Verlust von einem Höchststand.")


        st.caption(f"🛡️ Gebühren gezahlt: **€ {metrics['commission_paid']:,.2f}** | Angenommene Slippage: **{slippage}%** | Zeitraum: {period}")
        
        # Tabs für Charts / raw data
        tab_chart, tab_trades = st.tabs(["📉 Equity-Kurve", "📓 Trade Log"])
        
        # Plotly Chart
        with tab_chart:
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=equity_df.index, y=equity_df["Equity"],
                mode="lines", name="Strategie (Netto)",
                line=dict(color="#22c55e", width=2)
            ))
            
            fig.add_trace(go.Scatter(
                x=equity_df.index, y=equity_df["Benchmark"],
                mode="lines", name="Buy & Hold (Brutto)",
                line=dict(color="#94a3b8", width=1, dash="dot")
            ))
            
            fig.update_layout(
                title=f"Portfolio Entwicklung (Base 100): {ticker}",
                yaxis_title="Portfolio Wert (€)",
                xaxis_title="Datum",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                hovermode="x unified",
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )
            
            st.plotly_chart(fig, use_container_width=True)

        with tab_trades:
            if not trades:
                st.info("Diese Strategie hat im gewählten Zeitraum keine Trades ausgelöst.")
            else:
                df_trades = pd.DataFrame(trades)
                df_trades.index += 1  # 1-indexed
                
                # Formatierung für schöneres Display
                st_df = df_trades.style.format({
                    "entry_price": "€ {:.2f}",
                    "exit_price": "€ {:.2f}",
                    "pnl_eur": "€ {:+.2f}",
                    "pnl_pct": "{:+.2f} %"
                }).map(
                    lambda val: "color: #22c55e;" if val > 0 else "color: #ef4444;", 
                    subset=["pnl_eur", "pnl_pct"]
                )
                
                st.dataframe(st_df, use_container_width=True)
