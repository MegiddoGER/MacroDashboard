"""
views/pages/backtesting.py — Strategy Backtesting Engine Dashboard.

Ermöglicht das Validieren von Trading-Strategien gegen die historische
Kursentwicklung — für US-, DAX-, MDAX-, SDAX- und internationale Xetra-Werte.
"""

import csv
import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

from services.cache import cached_stock_history
from services.watchlist import resolve_ticker
from services.backtesting import BacktestEngine


# ---------------------------------------------------------------------------
# Markt-Presets: Ticker-Listen nach Markt/Index
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_XETRA_CSV = os.path.join(_DATA_DIR, "xetra_stocks.csv")

_MARKET_CACHE: dict[str, list[dict]] | None = None


def _load_market_presets() -> dict[str, list[dict]]:
    """Lädt Ticker-Presets aus der Xetra-CSV, gruppiert nach Index."""
    global _MARKET_CACHE
    if _MARKET_CACHE is not None:
        return _MARKET_CACHE

    presets = {
        "US (Top 30)": [
            {"ticker": "AAPL", "name": "Apple Inc."},
            {"ticker": "MSFT", "name": "Microsoft Corp."},
            {"ticker": "AMZN", "name": "Amazon.com Inc."},
            {"ticker": "GOOGL", "name": "Alphabet Inc."},
            {"ticker": "META", "name": "Meta Platforms Inc."},
            {"ticker": "NVDA", "name": "NVIDIA Corp."},
            {"ticker": "TSLA", "name": "Tesla Inc."},
            {"ticker": "JPM", "name": "JPMorgan Chase & Co."},
            {"ticker": "V", "name": "Visa Inc."},
            {"ticker": "JNJ", "name": "Johnson & Johnson"},
            {"ticker": "WMT", "name": "Walmart Inc."},
            {"ticker": "PG", "name": "Procter & Gamble Co."},
            {"ticker": "MA", "name": "Mastercard Inc."},
            {"ticker": "UNH", "name": "UnitedHealth Group"},
            {"ticker": "HD", "name": "Home Depot Inc."},
            {"ticker": "DIS", "name": "Walt Disney Co."},
            {"ticker": "NFLX", "name": "Netflix Inc."},
            {"ticker": "KO", "name": "Coca-Cola Co."},
            {"ticker": "PEP", "name": "PepsiCo Inc."},
            {"ticker": "MCD", "name": "McDonald's Corp."},
            {"ticker": "COST", "name": "Costco Wholesale Corp."},
            {"ticker": "ABBV", "name": "AbbVie Inc."},
            {"ticker": "CRM", "name": "Salesforce Inc."},
            {"ticker": "AMD", "name": "Advanced Micro Devices"},
            {"ticker": "INTC", "name": "Intel Corp."},
            {"ticker": "BA", "name": "Boeing Co."},
            {"ticker": "GS", "name": "Goldman Sachs Group"},
            {"ticker": "CAT", "name": "Caterpillar Inc."},
            {"ticker": "XOM", "name": "Exxon Mobil Corp."},
            {"ticker": "CVX", "name": "Chevron Corp."},
        ],
    }

    # Xetra-CSV laden und nach Index gruppieren
    if os.path.exists(_XETRA_CSV):
        try:
            with open(_XETRA_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                seen = {}  # ticker -> True, für Deduplizierung
                for row in reader:
                    ticker = row.get("Kürzel", "").strip()
                    name = row.get("Name", "").strip()
                    index = row.get("Index", "").strip()
                    if not ticker or not name or not index:
                        continue

                    # Index-Key für Gruppierung
                    key = index
                    if key == "XETRA International":
                        key = "Xetra International"

                    if key not in presets:
                        presets[key] = []

                    # Deduplizierung (manche Ticker sind in mehreren Indizes)
                    dedup_key = f"{key}:{ticker}"
                    if dedup_key not in seen:
                        presets[key].append({"ticker": ticker, "name": name})
                        seen[dedup_key] = True
        except Exception:
            pass

    _MARKET_CACHE = presets
    return presets


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def page_backtesting():
    st.markdown("## 📈 Strategy Backtesting Engine")
    st.caption("Validiere algorithmische Strategien mit realen Marktdaten (inklusive Gebühren & Slippage).")
    
    presets = _load_market_presets()

    # -----------------------------------------------------------------------
    # Parameter Formular
    # -----------------------------------------------------------------------
    with st.expander("⚙️ Backtest Konfiguration", expanded=True):

        # ── Markt & Ticker-Auswahl ────────────────────────────────
        st.markdown("###### 🌍 Markt & Ticker")
        mk_c1, mk_c2 = st.columns([1, 2])

        market_names = list(presets.keys())
        selected_market = mk_c1.selectbox(
            "Markt / Index",
            market_names,
            key="bt_market",
            help="Wähle einen Markt, um vorgefertigte Ticker anzuzeigen.",
        )

        # Dropdown mit Ticker-Presets + Custom-Option
        market_tickers = presets.get(selected_market, [])
        ticker_labels = [f"{t['ticker']}  ·  {t['name']}" for t in market_tickers]
        ticker_labels.append("✏️ Custom Ticker eingeben")

        selected_label = mk_c2.selectbox(
            "Ticker auswählen",
            ticker_labels,
            key="bt_ticker_select",
        )

        # Custom-Ticker Input oder ausgewählter Preset-Ticker
        if selected_label == "✏️ Custom Ticker eingeben":
            input_ticker = st.text_input(
                "Ticker Symbol", "SAP.DE", key="bt_ticker_custom",
                help="Beliebigen Ticker eingeben (z.B. SAP.DE, AAPL, RHM.DE)",
            ).upper()
        else:
            # Ticker aus dem Label extrahieren
            input_ticker = selected_label.split("·")[0].strip()

        # ── Strategie & Zeitraum ──────────────────────────────────
        st.markdown("###### 📊 Strategie & Zeitraum")
        f_c1, f_c2 = st.columns(2)
        
        strategies = {
            "RSI_Mean_Reversion": "RSI Mean Reversion (Oszillator)",
            "SMA_Cross_Trend": "SMA Golden Cross (Trendfolge)",
            "MACD_Momentum": "MACD Crossover (Momentum)",
            "Bollinger_Breakout": "Bollinger Bands Breakout (Volatilität)",
            "SMC_FVG_Bounce": "Smart Money Concept: FVG Bounce (Proxy)"
        }
        
        strat_key = f_c1.selectbox(
            "Handelsstrategie",
            options=list(strategies.keys()),
            format_func=lambda x: strategies[x],
        )
        period = f_c2.selectbox("Zeitraum", ["1y", "2y", "5y", "max"], index=2)
        
        # ── Kosten & Parameter ────────────────────────────────────
        st.markdown("###### 💰 Kosten & Parameter")
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
        
        with st.spinner(f"Lade historische Daten für {ticker} ({period})..."):
            hist = cached_stock_history(ticker, period)
            
        if hist is None or hist.empty or len(hist) < 200:
            st.error(f"Nicht genug historische Daten für {ticker} verfügbar. "
                     f"Versuche einen längeren Zeitraum oder anderen Ticker. "
                     f"(Benötigt min. 200 Handelstage für SMA-200.)")
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
        display_name = input_ticker.replace(".DE", "") if input_ticker.endswith(".DE") else input_ticker
        st.markdown(f"#### 📊 Resultate: {strategies[strat_key]} auf **{display_name}** ({ticker})")
        
        # ── Row 1: Kern-Metriken ──────────────────────────────────
        m1, m2, m3, m4, m5 = st.columns(5)
        
        m1.metric("Endkapital", f"€ {metrics['final_capital']:,.2f}", 
                  f"Start: € {init_capital:,.2f}", delta_color="off")
                  
        total_ret = metrics['total_return_pct']
        bench_ret = metrics['benchmark_return_pct']
        diff = metrics['outperformance']
        
        m2.metric("Rendite (Netto)", f"{total_ret:+.2f} %", 
                  f"{diff:+.2f} % vs Buy&Hold", delta_color="normal" if diff > 0 else "inverse")
                  
        m3.metric("Win-Rate", f"{metrics['win_rate']:.1f} %", 
                  f"{metrics['total_trades']} Trades total", delta_color="off")
                  
        profit_factor = metrics['profit_factor']
        pf_label = "Exzellent" if profit_factor > 2.0 else ("Gut" if profit_factor > 1.2 else "Schwach")
        m4.metric("Profit-Faktor", f"{profit_factor:.2f}",
                  pf_label,
                  delta_color="normal" if profit_factor > 1.5 else ("inverse" if profit_factor < 1.0 else "off"))
                  
        dd = metrics['max_drawdown_pct']
        m5.metric("Max Drawdown", f"{dd:.1f} %", 
                  help="Maximaler prozentualer Verlust von einem Höchststand.")

        # ── Row 2: Risikoadjustierte Metriken ─────────────────────
        r1, r2, r3, r4, r5 = st.columns(5)

        sharpe = metrics.get("sharpe_ratio")
        r1.metric("Sharpe Ratio",
                  f"{sharpe:.2f}" if sharpe is not None else "—",
                  help="Rendite pro Risikoeinheit. >1 = gut, >2 = sehr gut, <0 = negativ")

        sortino = metrics.get("sortino_ratio")
        r2.metric("Sortino Ratio",
                  f"{sortino:.2f}" if sortino is not None else "—",
                  help="Wie Sharpe, aber nur Downside-Risiko. Besser für asymmetrische Returns.")

        r3.metric("Ann. Rendite", f"{metrics['annualized_return_pct']:+.1f} %",
                  help="Annualisierte Rendite (252 Handelstage/Jahr)")

        r4.metric("Volatilität", f"{metrics['volatility_pct']:.1f} %",
                  help="Annualisierte Standardabweichung der täglichen Returns")

        calmar = metrics.get("calmar_ratio")
        r5.metric("Calmar Ratio",
                  f"{calmar:.2f}" if calmar is not None else "—",
                  help="Ann. Rendite / Max Drawdown. >1 = gut, >3 = hervorragend")

        # ── Row 3: Trade-Details ──────────────────────────────────
        t1, t2, t3, t4 = st.columns(4)

        t1.metric("Bester Trade", f"{metrics['best_trade_pct']:+.1f} %")
        t2.metric("Schlechtester", f"{metrics['worst_trade_pct']:+.1f} %")
        t3.metric("∅ Haltedauer", f"{metrics['avg_holding_days']:.0f} Tage")
        t4.metric("⌀ Win / ⌀ Loss",
                  f"{metrics['avg_win_pct']:+.1f}% / {metrics['avg_loss_pct']:+.1f}%")

        st.caption(f"🛡️ Gebühren gezahlt: **€ {metrics['commission_paid']:,.2f}** | "
                   f"Angenommene Slippage: **{slippage}%** | Zeitraum: {period}")
        
        # ── Tabs: Charts / Drawdown / Trade Log ───────────────────
        tab_chart, tab_dd, tab_trades = st.tabs([
            "📉 Equity-Kurve", "📊 Drawdown-Analyse", "📓 Trade Log"
        ])
        
        # Equity-Kurve
        with tab_chart:
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=equity_df.index, y=equity_df["Equity"],
                mode="lines", name="Strategie (Netto)",
                line=dict(color="#22c55e", width=2),
                fill="tozeroy", fillcolor="rgba(34,197,94,0.08)",
            ))
            
            fig.add_trace(go.Scatter(
                x=equity_df.index, y=equity_df["Benchmark"],
                mode="lines", name="Buy & Hold (Brutto)",
                line=dict(color="#94a3b8", width=1, dash="dot"),
            ))
            
            fig.update_layout(
                title=f"Portfolio-Entwicklung: {display_name}",
                yaxis_title="Portfolio Wert (€)",
                xaxis_title="Datum",
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                hovermode="x unified",
                height=400,
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
            )
            
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Drawdown-Chart
        with tab_dd:
            if "Drawdown" in equity_df.columns:
                fig_dd = go.Figure()
                fig_dd.add_trace(go.Scatter(
                    x=equity_df.index,
                    y=equity_df["Drawdown"],
                    fill="tozeroy",
                    fillcolor="rgba(239, 68, 68, 0.2)",
                    line=dict(color="#ef4444", width=2),
                    name="Drawdown %",
                ))
                fig_dd.update_layout(
                    title="Drawdown vom Höchststand",
                    yaxis_title="Drawdown (%)",
                    xaxis_title="Datum",
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    hovermode="x unified",
                    height=300,
                )
                st.plotly_chart(fig_dd, use_container_width=True, config={"displayModeBar": False})

                # Drawdown-Statistiken
                dd_vals = equity_df["Drawdown"].values
                dd1, dd2, dd3 = st.columns(3)
                dd1.metric("Max Drawdown", f"{np.min(dd_vals):.1f} %")
                dd2.metric("∅ Drawdown", f"{np.mean(dd_vals[dd_vals < 0]):.1f} %"
                           if np.any(dd_vals < 0) else "0.0 %")
                # Wie lange war der Drawdown > 5%?
                severe_dd_days = np.sum(dd_vals < -5)
                dd3.metric("Tage unter −5%", f"{severe_dd_days}",
                           help="Anzahl Handelstage mit einem Drawdown von über 5%")
            else:
                st.info("Keine Drawdown-Daten verfügbar.")

        # Trade Log
        with tab_trades:
            if not trades:
                st.info("Diese Strategie hat im gewählten Zeitraum keine Trades ausgelöst.")
            else:
                df_trades = pd.DataFrame(trades)
                df_trades.index += 1  # 1-indexed
                
                # Haltedauer berechnen
                df_trades["holding_days"] = df_trades.apply(
                    lambda r: (datetime.strptime(r["exit_date"], "%Y-%m-%d") -
                               datetime.strptime(r["entry_date"], "%Y-%m-%d")).days,
                    axis=1,
                )

                st_df = df_trades.style.format({
                    "entry_price": "€ {:.2f}",
                    "exit_price": "€ {:.2f}",
                    "shares": "{:.2f}",
                    "pnl_eur": "€ {:+.2f}",
                    "pnl_pct": "{:+.2f} %",
                    "holding_days": "{:.0f} d",
                }).map(
                    lambda val: "color: #22c55e;" if isinstance(val, (int, float)) and val > 0
                    else ("color: #ef4444;" if isinstance(val, (int, float)) and val < 0 else ""),
                    subset=["pnl_eur", "pnl_pct"],
                )
                
                st.dataframe(st_df, use_container_width=True)
