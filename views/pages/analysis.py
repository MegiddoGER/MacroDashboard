import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

from services.watchlist import load_watchlist, resolve_ticker
from services.cache import cached_stock_details, cached_correlation, cached_company_news
from views.components.news_list import _render_news_list
from services.fundamental import (
    calc_dcf_valuation, calc_balance_sheet_quality, get_margin_trends,
    get_sector_peers, calc_dividend_analysis, get_insider_institutional,
    get_analyst_consensus
)
from views.components.charts import (
    plot_candlestick, plot_rsi, plot_macd, plot_bollinger, plot_stochastic,
    plot_returns_distribution, plot_timeseries, plot_correlation_matrix,
    plot_liquidity_sweeps, plot_swing_overview, plot_order_flow, plot_financials_chart
)
from services.technical import (
    calc_macd, calc_bollinger, calc_stochastic, calc_atr, detect_liquidity_sweeps,
    calc_swing_signals, calc_order_flow, calc_technical_summary, calc_position_sizing
)

def page_analysis():
    st.markdown("## Analyse")
    
    # ── State Initialisierung ────────────────────────────────────────
    if "saved_analysis_ticker" not in st.session_state:
        st.session_state.saved_analysis_ticker = ""
    if "saved_analysis_wl_choice" not in st.session_state:
        st.session_state.saved_analysis_wl_choice = "— Manuell eingeben —"
    if "saved_analysis_time_filter" not in st.session_state:
        st.session_state.saved_analysis_time_filter = "1 Jahr"
        
    if "analysis_wl_select" not in st.session_state:
        st.session_state.analysis_wl_select = st.session_state.saved_analysis_wl_choice
        
    if "analysis_ticker_input" not in st.session_state:
        st.session_state.analysis_ticker_input = st.session_state.saved_analysis_ticker
        
    # ── Callbacks zur gegenseitigen State-Aktualisierung ──────────────
    def on_wl_change():
        st.session_state.saved_analysis_wl_choice = st.session_state.analysis_wl_select
        st.session_state.saved_analysis_ticker = ""

    def on_ticker_change():
        st.session_state.saved_analysis_ticker = st.session_state.analysis_ticker_input
        st.session_state.saved_analysis_wl_choice = "— Manuell eingeben —"

    # ── Eingabe: Watchlist-Auswahl ODER manuelle Suche ───────────────
    wl_items = load_watchlist()
    col_btn, col_wl, col_search = st.columns([0.1, 0.45, 0.45], gap="small")

    with col_btn:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("❌", help="Auswahl zurücksetzen", key="reset_analysis", use_container_width=True):
            st.session_state.saved_analysis_wl_choice = "— Manuell eingeben —"
            st.session_state.saved_analysis_ticker = ""
            st.session_state.analysis_wl_select = "— Manuell eingeben —"
            st.session_state.analysis_ticker_input = ""
            st.rerun()

    with col_wl:
        wl_options = ["— Manuell eingeben —"]
        wl_ticker_map = {}
        for item in wl_items:
            disp = item.get("display", item["ticker"])
            label = f"{disp}  ·  {item['name']}"
            wl_options.append(label)
            wl_ticker_map[label] = item["ticker"]
            
        wl_choice = st.selectbox(
            "⚡ Watchlist",
            options=wl_options,
            key="analysis_wl_select",
            on_change=on_wl_change,
            label_visibility="visible"
        )

    with col_search:
        raw_input = st.text_input(
            "Ticker oder Firmenname eingeben",
            placeholder="z.B. SAP, Apple, NVIDIA",
            key="analysis_ticker_input",
            on_change=on_ticker_change,
        ).strip()
    
    st.markdown("---")

    if wl_choice != "— Manuell eingeben —":
        raw_input = wl_ticker_map[wl_choice]

    if not raw_input:
        st.info("Wähle einen Watchlist-Eintrag oder gib ein Symbol / einen Namen ein.")
        return

    with st.spinner(f"Suche **{raw_input}** …"):
        resolved = resolve_ticker(raw_input)
    if resolved:
        ticker = resolved["ticker"]
        display_ticker = resolved.get("display", ticker)
    else:
        ticker = raw_input.upper()
        display_ticker = ticker

    with st.spinner(f"Lade Daten für **{ticker}** …"):
        details = cached_stock_details(ticker)

    if details is None:
        st.error(f"Keine Daten für **{ticker}** gefunden. Prüfe das Symbol.")
        return

    stats = details["stats"]

    # ── Makro-Event Warnung ──────────────────────────────────────────────
    try:
        from services.cache import cached_events_for_ticker
        macro_events = cached_events_for_ticker(ticker, days=7)
        if macro_events:
            from services.economic_calendar import get_impact_color, get_country_flag
            for ev in macro_events:
                impact_color = get_impact_color(ev.impact)
                flag = get_country_flag(ev.country)
                date_str = ev.date.strftime("%d.%m.%Y")
                time_str = f" um {ev.time_cet} CET" if ev.time_cet else ""
                st.markdown(
                    f"<div style='"
                    f"background:linear-gradient(90deg, {impact_color}22 0%, #0f172a 100%);"
                    f"border-left:4px solid {impact_color};"
                    f"border-radius:6px;"
                    f"padding:10px 16px;"
                    f"margin-bottom:8px;"
                    f"'>"
                    f"<span style='font-size:0.9rem;'>"
                    f"⚠️ {flag} <b>{ev.name}</b> — "
                    f"{ev.countdown_label} ({date_str}{time_str})"
                    f"</span>"
                    f"<br><span style='color:#94a3b8;font-size:0.78rem;'>"
                    f"{ev.description}"
                    f"</span></div>",
                    unsafe_allow_html=True,
                )
    except Exception:
        pass  # Kalender ist optional — Analyse soll nie daran scheitern

    # ── Time Filter Selection ──
    st.markdown("### Zeitraum auswählen")
    time_filter = st.pills(
        "Zeitraum",
        ["1 Tag", "1 Woche", "1 Monat", "YTD", "1 Jahr", "5 Jahre", "Gesamt"],
        default=st.session_state.saved_analysis_time_filter,
        key="time_filter_pills",
        label_visibility="collapsed"
    )
    
    if time_filter:
        st.session_state.saved_analysis_time_filter = time_filter
    else:
        time_filter = st.session_state.saved_analysis_time_filter
    
    hist_map = {
        "1 Tag": details.get("hist_1d", details["hist_1y"]),
        "1 Woche": details.get("hist_1w", details["hist_1y"]),
        "1 Monat": details.get("hist_1m", details["hist_1y"]),
        "YTD": details.get("hist_ytd", details["hist_1y"]),
        "1 Jahr": details["hist_1y"],
        "5 Jahre": details.get("hist_5y", details["hist_1y"]),
        "Gesamt": details.get("hist_max", details["hist_5y"]),
    }
    
    selected_hist = hist_map.get(time_filter, details["hist_1y"])
    
    from datetime import datetime
    today = datetime.now()
    if time_filter == "1 Tag" and today.weekday() >= 5:
        st.info("ℹ️ **Es ist Wochenende.** Der 1-Tages-Graph zeigt die Intraday-Daten des letzten Handelstages (Freitag).")
    
    hist = details["hist_1y"]
    close = hist["Close"]

    # ── Header-Metriken ──────────────────────────────────────────────────
    st.markdown(f"### {stats['name']}  ·  `{display_ticker}`")
    if stats["sector"] != "—":
        st.caption(f"Sektor: {stats['sector']}")

    tab_overview, tab_financials = st.tabs(["Übersicht", "Finanzdaten"])

    with tab_overview:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Aktueller Kurs", f"{stats['current_price']:,.2f} €")
        c2.metric("52W Hoch", f"{stats['high_52w']:,.2f} €")
        c3.metric("52W Tief", f"{stats['low_52w']:,.2f} €")
        c4.metric(
            "Volatilität (ann.)", 
            f"{stats['volatility']:.1f} %",
            help="Annualisierte historische Volatilität. Misst die durchschnittliche Schwankungsbreite der Aktie über ein Jahr. Höhere Werte bedeuten höheres Risiko/größere Preisschwankungen."
        )

        c5, c6, c7, c8 = st.columns(4)
        c5.metric(
            "RSI (14)", 
            f"{stats['rsi']:.1f}" if stats["rsi"] else "—",
            help="Relative Strength Index (14 Tage). Ein Momentum-Indikator, der die Geschwindigkeit und Veränderung von Kursbewegungen misst. Werte > 70 gelten als überkauft, < 30 als überverkauft."
        )
        c6.metric(
            "SMA 20", 
            f"{stats['sma_20']:,.2f} €" if stats["sma_20"] else "—",
            help="Simple Moving Average (20 Tage). Der einfache gleitende Durchschnitt der letzten 20 Handelstage. Dient zur Identifikation des kurzfristigen Trends."
        )
        c7.metric(
            "SMA 50", 
            f"{stats['sma_50']:,.2f} €" if stats["sma_50"] else "—",
            help="Simple Moving Average (50 Tage). Zeigt den mittelfristigen Trend an."
        )
        c8.metric(
            "SMA 200", 
            f"{stats['sma_200']:,.2f} €" if stats["sma_200"] else "—",
            help="Simple Moving Average (200 Tage). Einer der wichtigsten Indikatoren für den langfristigen Trend. Liegt der Kurs darüber, herrscht ein Aufwärtstrend."
        )

        c9, c10, c11, c12 = st.columns(4)
        c9.metric(
            "KGV (P/E)", 
            f"{stats['pe_ratio']:.1f}" if stats["pe_ratio"] else "—",
            help="Kurs-Gewinn-Verhältnis (Price-to-Earnings). Setzt den Kurs der Aktie in Relation zum Gewinn je Aktie (EPS). Ein niedriges KGV kann auf eine Unterbewertung hinweisen, variiert jedoch stark nach Sektor."
        )
        if stats["dividend_yield"]:
            c10.metric("Dividendenrendite", f"{stats['dividend_yield']*100:.2f} %")
        else:
            c10.metric("Dividendenrendite", "—")
            
        atr = calc_atr(hist["High"], hist["Low"], hist["Close"], 14)
        atr_val = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else None
        c11.metric(
            "ATR (14)", 
            f"{atr_val:.2f} €" if atr_val else "—",
            help="Average True Range (14 Tage). Misst die absolute Volatilität in Euro. Gibt an, um wie viel Euro die Aktie im Durchschnitt pro Tag schwankt. Hilft bei der Festlegung von Stop-Loss-Leveln."
        )
        if stats["avg_volume"]:
            vol = stats["avg_volume"]
            if vol >= 1e9: vol_str = f"{vol:,} Stück (Mrd.)"
            elif vol >= 1e6: vol_str = f"{vol:,} Stück (Mio.)"
            else: vol_str = f"{vol:,} Stück"
            c12.metric("Ø Volumen", vol_str, help="Durchschnittliches tägliches Handelsvolumen.")
        else:
            c12.metric("Ø Volumen", "—")

        if stats["market_cap"]:
            cap = stats["market_cap"]
            if cap >= 1e12: cap_str = f"{cap/1e12:.2f} Bio. €"
            elif cap >= 1e9: cap_str = f"{cap/1e9:.2f} Mrd. €"
            elif cap >= 1e6: cap_str = f"{cap/1e6:.1f} Mio. €"
            else: cap_str = f"{cap:,.0f} €"
            st.caption(f"Marktkapitalisierung: **{cap_str}**")

        earnings_raw = stats.get("earnings_date")
        if earnings_raw:
            try:
                from datetime import datetime
                ed = datetime.fromisoformat(str(earnings_raw).split(" ")[0])
                earnings_str = ed.strftime("%d.%m.%Y")
            except Exception:
                earnings_str = str(earnings_raw)
            st.caption(f"📅 Nächste Quartalszahlen: **{earnings_str}**")

    with tab_financials:
        fin_data = details.get("financials", [])
        if not fin_data:
            st.info("Für diese Aktie sind momentan keine detaillierten Finanzdaten verfügbar.")
        else:
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

    st.markdown("---")

    tab_chart, tab_rsi, tab_macd, tab_boll, tab_stoch, tab_returns, tab_5y, tab_corr = st.tabs([
        "📊 Kurs & SMAs", "📉 RSI", "📀 MACD", "🌐 Bollinger",
        "📈 Stochastic", "🎲 Renditen", "🗓️ 5 Jahre", "🔗 Korrelation"
    ])

    with tab_chart:
        st.plotly_chart(
            plot_candlestick(
                selected_hist, f"{ticker} — Candlestick ({time_filter})",
                sma_20=details["sma_20"],
                sma_50=details["sma_50"],
                sma_200=details["sma_200"],
            ),
            use_container_width=True, config={"scrollZoom": True, "displayModeBar": True},
        )
        st.caption("SMA 20 (gelb) = kurzfristig · SMA 50 (blau) = mittelfristig · SMA 200 (violett) = langfristig")

    with tab_rsi:
        rsi_series = details["rsi_series"]
        if rsi_series is not None:
            st.plotly_chart(plot_rsi(rsi_series, f"RSI (14) — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
            rsi_val = stats["rsi"]
            if rsi_val:
                if rsi_val > 70: st.warning(f"RSI bei **{rsi_val:.1f}** → Überkauft — möglicher Rücksetzer")
                elif rsi_val < 30: st.success(f"RSI bei **{rsi_val:.1f}** → Überverkauft — mögliche Erholung")
                else: st.info(f"RSI bei **{rsi_val:.1f}** → Neutraler Bereich")
            st.caption("RSI > 70 = überkauft (Verkaufssignal) · RSI < 30 = überverkauft (Kaufsignal)")

    with tab_macd:
        macd_line, signal_line, histogram = calc_macd(close)
        st.plotly_chart(plot_macd(macd_line, signal_line, histogram, f"MACD — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        last_macd = float(macd_line.dropna().iloc[-1]) if not macd_line.dropna().empty else 0
        last_signal = float(signal_line.dropna().iloc[-1]) if not signal_line.dropna().empty else 0
        if last_macd > last_signal: st.success("✅ MACD über Signal-Linie → Bullishes Momentum")
        else: st.warning("⚠️ MACD unter Signal-Linie → Bearishes Momentum")
        st.caption("MACD = Differenz zweier EMAs. Kreuzt die MACD-Linie die Signal-Linie von unten → Kaufsignal.")

    with tab_boll:
        upper, middle, lower = calc_bollinger(close)
        st.plotly_chart(plot_bollinger(close, upper, middle, lower, f"Bollinger Bänder — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        last_close = float(close.iloc[-1])
        last_upper = float(upper.dropna().iloc[-1]) if not upper.dropna().empty else 0
        last_lower = float(lower.dropna().iloc[-1]) if not lower.dropna().empty else 0
        if last_close >= last_upper: st.warning("Kurs am oberen Band → möglicherweise überkauft")
        elif last_close <= last_lower: st.success("Kurs am unteren Band → möglicherweise überverkauft")
        else: st.info("Kurs innerhalb der Bänder → normale Volatilität")
        st.caption("Bollinger Bänder = SMA 20 ± 2 Standardabweichungen. Berührung am Band signalisiert Extrembereiche.")

    with tab_stoch:
        k_line, d_line = calc_stochastic(hist["High"], hist["Low"], hist["Close"])
        st.plotly_chart(plot_stochastic(k_line, d_line, f"Stochastic Oscillator — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        last_k = float(k_line.dropna().iloc[-1]) if not k_line.dropna().empty else 50
        if last_k > 80: st.warning(f"%K bei **{last_k:.0f}** → Überkauft-Zone")
        elif last_k < 20: st.success(f"%K bei **{last_k:.0f}** → Überverkauft-Zone")
        else: st.info(f"%K bei **{last_k:.0f}** → Neutraler Bereich")
        st.caption("%K > 80 = überkauft · %K < 20 = überverkauft. Kreuzung von %K und %D gibt Handelssignale.")

    with tab_returns:
        if details["returns"] is not None and not details["returns"].empty:
            rets = details["returns"]
            st.plotly_chart(plot_returns_distribution(rets, f"Tägliche Renditen — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Ø Tagesrendite", f"{rets.mean()*100:.3f} %")
            rc2.metric("Max Gewinn", f"{rets.max()*100:+.2f} %")
            rc3.metric("Max Verlust", f"{rets.min()*100:+.2f} %")
            rc4.metric("Sharpe (ann.)", f"{(rets.mean()/rets.std()*np.sqrt(252)):.2f}" if rets.std() > 0 else "—")
            st.caption("Sharpe Ratio = risikobereinigte Rendite. > 1 = gut, > 2 = sehr gut, < 0 = negativ.")

    with tab_5y:
        hist_5y = details["hist_5y"]
        if hist_5y is not None and not hist_5y.empty:
            st.plotly_chart(plot_timeseries(hist_5y, f"{ticker} — 5-Jahres-Übersicht", color="#a855f7", height=400), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        else:
            st.info("5-Jahres-Daten nicht verfügbar.")

    with tab_corr:
        st.markdown("##### Korrelation mit anderen Assets")
        st.caption("Wie stark bewegt sich diese Aktie im Gleichschritt mit anderen Assets? Werte nahe +1 = starker Gleichlauf, nahe -1 = gegenläufig, nahe 0 = unabhängig.")

        st.markdown("**Vergleichsaktie hinzufügen**")
        corr_col_input, corr_col_period = st.columns([3, 1])

        with corr_col_input:
            corr_extra = st.text_input("Ticker oder Firmenname", placeholder="z.B. MSFT, BMW, Tesla …", key="corr_extra_ticker").strip()

        with corr_col_period:
            corr_period = st.selectbox(
                "Zeitraum", ["3mo", "6mo", "1y", "2y"],
                index=2, key="corr_period",
                format_func=lambda x: {"3mo": "3 Monate", "6mo": "6 Monate", "1y": "1 Jahr", "2y": "2 Jahre"}[x],
            )

        corr_tickers = [ticker]
        corr_labels = [display_ticker]

        if corr_extra:
            resolved_extra = resolve_ticker(corr_extra)
            if resolved_extra:
                extra_t = resolved_extra["ticker"]
                extra_l = resolved_extra.get("display", extra_t)
            else:
                extra_t = corr_extra.upper()
                extra_l = extra_t
            if extra_t != ticker:
                corr_tickers.append(extra_t)
                corr_labels.append(extra_l)

        st.markdown("**Benchmarks einbeziehen**")
        bench_col1, bench_col2, bench_col3, bench_col4 = st.columns(4)
        benchmarks = {}
        with bench_col1:
            if st.checkbox("S&P 500", value=True, key="corr_sp500"): benchmarks["^GSPC"] = "S&P 500"
        with bench_col2:
            if st.checkbox("DAX", value=True, key="corr_dax"): benchmarks["^GDAXI"] = "DAX"
        with bench_col3:
            if st.checkbox("Gold", value=True, key="corr_gold"): benchmarks["GC=F"] = "Gold"
        with bench_col4:
            if st.checkbox("Bitcoin", value=False, key="corr_btc"): benchmarks["BTC-USD"] = "Bitcoin"

        for bt, bl in benchmarks.items():
            if bt not in corr_tickers:
                corr_tickers.append(bt)
                corr_labels.append(bl)

        if len(corr_tickers) < 2:
            st.info("Füge mindestens eine Vergleichsaktie hinzu oder aktiviere Benchmarks.")
        else:
            tickers_str = ",".join(corr_tickers)
            labels_str = ",".join(corr_labels)
            with st.spinner("Berechne Korrelationen …"):
                corr_df = cached_correlation(tickers_str, labels_str, corr_period)

            if corr_df is not None:
                st.plotly_chart(plot_correlation_matrix(corr_df, f"Korrelationsmatrix — {display_ticker} ({corr_period})"), use_container_width=True)
            else:
                st.warning("Korrelationsdaten nicht verfügbar (zu wenig Datenpunkte).")

    # ── Strategische Entscheidungen ────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎯 Strategische Entscheidungen")
    st.caption("Automatische Analyse-Signale für drei Handelsansätze — basierend auf den aktuellen Kursdaten.")

    yfin_sector = stats["sector"].lower() if stats["sector"] and stats["sector"] != "—" else ""
    yfin_industry = details.get("info", {}).get("industry", "").lower()
    
    sector_cat = "none"
    tab_name = "📊 Quant-Analyse"
    
    if "financial" in yfin_sector or "insurance" in yfin_sector:
        sector_cat = "finanzen"
        tab_name = "🏦 Excess Returns (Finanzen)"
    elif "technology" in yfin_sector or "software" in yfin_sector:
        sector_cat = "tech"
        tab_name = "💻 Rule of 40 (Tech/SaaS)"
    elif "semiconductor" in yfin_industry or "hardware" in yfin_industry:
        sector_cat = "hardware"
        tab_name = "🔌 EV/EBITDA-Zyklik (Hardware)"
    elif "healthcare" in yfin_sector or "biotech" in yfin_sector or "pharm" in yfin_sector:
        sector_cat = "pharma"
        tab_name = "🧬 rNPV Proxy (Pharma)"
    elif "energy" in yfin_sector or "oil" in yfin_sector:
        sector_cat = "energie"
        tab_name = "🛢️ EV/DACF (Energie)"
    elif "communication" in yfin_sector or "telecom" in yfin_sector:
        sector_cat = "telekom"
        tab_name = "📡 ARPU-Adj. EV/EBITDA (Telekom)"
    elif "industrial" in yfin_sector or "transportation" in yfin_sector or "consumer cyclical" in yfin_sector:
        if "aerospace" in yfin_industry or "defense" in yfin_industry:
            sector_cat = "defense"
            tab_name = "🛡️ EV/EBITDA & Marge (Rüstung/Luftfahrt)"
        elif "auto" in yfin_industry:
            sector_cat = "auto"
            tab_name = "🚗 Asset Turnover (Automobil)"
        elif "machinery" in yfin_industry or "construction" in yfin_industry or "building" in yfin_industry:
            sector_cat = "maschinenbau"
            tab_name = "🏗️ Zyklus-Proxy (Maschinen-/Bauwesen)"
        elif "freight" in yfin_industry or "logistic" in yfin_industry or "airline" in yfin_industry or "railroad" in yfin_industry or "shipping" in yfin_industry or "transport" in yfin_industry:
            sector_cat = "logistik"
            tab_name = "🚢 EV/EBITDAR (Logistik)"
        else:
            sector_cat = "industrie"
            tab_name = "🏭 Asset-Based (Allg. Industrie)"
    else:
        sector_cat = "csvs"
        tab_name = "🏛️ CSVS (Dividenden & Buchwert)"

    tab_liq, tab_swing, tab_flow, tab_quant, tab_smc, tab_options = st.tabs([
        "🔄 Liquidity Sweep", "📈 Swing Trading", "📊 Order Flow", tab_name, "🧲 SMC (Makro)", "📋 Options Flow"
    ])

    with tab_liq:
        sweeps = detect_liquidity_sweeps(hist["High"], hist["Low"], close)
        if sweeps:
            st.plotly_chart(plot_liquidity_sweeps(hist, sweeps, f"Liquidity Sweeps — {display_ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
            bull = [s for s in sweeps if s["type"] == "bullish"]
            bear = [s for s in sweeps if s["type"] == "bearish"]
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Erkannte Sweeps", len(sweeps))
            sc2.metric("🟢 Bullish", len(bull))
            sc3.metric("🔴 Bearish", len(bear))

            latest = sweeps[-1]
            if latest["type"] == "bullish":
                st.success(f"✅ Letzter Sweep: **Bullish** am {latest['sweep_date'].strftime('%d.%m.%Y') if hasattr(latest['sweep_date'], 'strftime') else latest['sweep_date']} bei **{latest['level']:,.2f} €** — Liquidität wurde nach unten abgegriffen und zurückgewonnen.")
            else:
                st.warning(f"⚠️ Letzter Sweep: **Bearish** am {latest['sweep_date'].strftime('%d.%m.%Y') if hasattr(latest['sweep_date'], 'strftime') else latest['sweep_date']} bei **{latest['level']:,.2f} €** — Liquidität wurde nach oben abgegriffen und zurückgewiesen.")
            st.caption("Liquidity Sweeps entstehen, wenn institutionelle Trader gezielt Stop-Loss-Orders an Swing-Hochs/-Tiefs auslösen. Ein Bullish Sweep (grün) deutet auf Akkumulation hin, ein Bearish Sweep (rot) auf Distribution.")
        else:
            st.info("Keine Liquidity Sweeps im aktuellen Zeitraum erkannt. Das deutet auf einen stabilen Kursverlauf ohne signifikante Stop-Hunt-Muster hin.")

    with tab_smc:
        from smc.indicators import analyze_smc
        from smc.charts import plot_smc
        
        # Weekly + Monthly-Daten als Higher-Timeframes für MTF-Confluence
        htf_weekly = details.get("hist_max")
        htf_monthly = details.get("hist_monthly")
        smc_data = analyze_smc(hist, htf_df=htf_weekly, monthly_df=htf_monthly)
        if smc_data and "fvgs" in smc_data:
            st.plotly_chart(plot_smc(hist, smc_data, f"SMC & Liquiditätszonen — {display_ticker}"), use_container_width=True)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Offene Bullish FVGs (Support)", smc_data["stats"].get("unmitigated_bullish", 0))
            c2.metric("Offene Bearish FVGs (Resistance)", smc_data["stats"].get("unmitigated_bearish", 0))
            val_eqh = smc_data["stats"].get("nearest_eqh")
            if val_eqh: c3.metric("Nächstes EQH (Magnet ⬆️)", f"{val_eqh:,.2f}")
            else: c3.metric("Nächstes EQH (Magnet ⬆️)", "—")
            val_eql = smc_data["stats"].get("nearest_eql")
            if val_eql: c4.metric("Nächstes EQL (Magnet ⬇️)", f"{val_eql:,.2f}")
            else: c4.metric("Nächstes EQL (Magnet ⬇️)", "—")

            # MTF-Confluence Metriken
            confluence = smc_data.get("confluence_score", 0)
            confluence_max = smc_data.get("confluence_max", 5)
            htf_trend = smc_data.get("htf_trend", "neutral")
            htf_bias = smc_data.get("htf_fvg_bias", "neutral")
            trend_icons = {"bullish": "🟢 Aufwärts", "bearish": "🔴 Abwärts", "neutral": "➖ Neutral"}
            
            st.markdown("---")
            st.markdown("##### 🔗 Multi-Timeframe Confluence (Daily · Weekly · Monthly)")

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Confluence-Score", f"{confluence}/{confluence_max}",
                       help="0 = keine Bestätigung, 5 = volle 3-Tier MTF-Confluence (Daily/Weekly/Monthly).")
            mc2.metric("Wochentrend (HTF)", trend_icons.get(htf_trend, "—"))
            mc3.metric("HTF FVG-Bias", trend_icons.get(htf_bias, "—"))

            # ── MTF Alignment Matrix ─────────────────────────────────
            mtf_matrix = smc_data.get("mtf_matrix")
            if mtf_matrix:
                st.markdown("##### 📊 MTF-Alignment-Matrix")
                st.caption("Zeigt Trend, FVG-Bias und Struktur über drei Zeitebenen. "
                          "Volle Alignment (alle grün) = höchste Überzeugung.")

                signal_colors = {
                    "bullish": "#22c55e",
                    "bearish": "#ef4444",
                    "neutral": "#64748b",
                }
                signal_labels = {
                    "bullish": "▲ Bullish",
                    "bearish": "▼ Bearish",
                    "neutral": "— Neutral",
                }

                # Matrix als HTML-Tabelle
                matrix_html = """
                <table style="width:100%; border-collapse:collapse; font-size:0.85rem; margin:8px 0;">
                    <thead>
                        <tr style="border-bottom:2px solid #334155;">
                            <th style="text-align:left;padding:8px;color:#94a3b8;font-weight:500;">Timeframe</th>
                """
                for cat in mtf_matrix["categories"]:
                    matrix_html += f'<th style="text-align:center;padding:8px;color:#94a3b8;font-weight:500;">{cat}</th>'
                matrix_html += "</tr></thead><tbody>"

                for tf in mtf_matrix["timeframes"]:
                    tf_icon = {"Monthly": "📅", "Weekly": "📆", "Daily": "📊"}.get(tf, "")
                    matrix_html += f'<tr style="border-bottom:1px solid #1e293b;"><td style="padding:8px;font-weight:600;color:#e2e8f0;">{tf_icon} {tf}</td>'
                    for cat in mtf_matrix["categories"]:
                        val = mtf_matrix["data"].get(tf, {}).get(cat, "neutral")
                        color = signal_colors.get(val, "#64748b")
                        label = signal_labels.get(val, "—")
                        matrix_html += (
                            f'<td style="text-align:center;padding:8px;">'
                            f'<span style="color:{color};font-weight:600;">{label}</span></td>'
                        )
                    matrix_html += "</tr>"

                matrix_html += "</tbody></table>"
                st.markdown(matrix_html, unsafe_allow_html=True)

                # Zusammenfassende Bewertung
                data = mtf_matrix["data"]
                all_trends = [data[tf]["Trend"] for tf in mtf_matrix["timeframes"]]
                all_fvg = [data[tf]["FVG Bias"] for tf in mtf_matrix["timeframes"]]

                trends_aligned = len(set(all_trends)) == 1 and all_trends[0] != "neutral"
                fvg_aligned = len(set(all_fvg)) == 1 and all_fvg[0] != "neutral"

                if trends_aligned and fvg_aligned:
                    direction = "bullish" if all_trends[0] == "bullish" else "bearish"
                    if direction == "bullish":
                        st.success("✅ **Perfekte MTF-Confluence:** Alle drei Zeitebenen (Monthly/Weekly/Daily) "
                                  "zeigen übereinstimmend bullishe Trends und FVG-Bias — stärkste Überzeugung für Long-Setups.")
                    else:
                        st.error("🔴 **Perfekte MTF-Confluence (bearish):** Alle drei Zeitebenen "
                                "zeigen übereinstimmend bearishe Signale — stärkste Überzeugung für Short/Hedge-Setups.")
                elif confluence >= 3:
                    st.success("✅ Starke Multi-Timeframe Confluence: Mehrere Zeitebenen bestätigen sich gegenseitig.")
                elif confluence >= 1:
                    st.warning("⚠️ Teilweise Confluence: Nur partielles Alignment zwischen den Zeitebenen.")
                else:
                    st.info("ℹ️ Keine Confluence: Die Zeitebenen sind nicht aufeinander abgestimmt — erhöhte Vorsicht.")
            else:
                if confluence >= 2:
                    st.success("✅ Starke Multi-Timeframe Confluence: Tages- und Wochensignale bestätigen sich gegenseitig.")
                elif confluence == 1:
                    st.warning("⚠️ Teilweise Confluence: Nur partielles Alignment zwischen Tages- und Wochenstruktur.")
                else:
                    st.info("ℹ️ Keine Confluence: Tages- und Wochensignale sind nicht aufeinander abgestimmt — erhöhte Vorsicht.")
        else:
            st.info("Nicht genügend Daten für SMC Analyse (mind. 20 Kerzen benötigt).")

    with tab_swing:
        swing = calc_swing_signals(hist["High"], hist["Low"], close, hist["Volume"])
        if swing:
            st.plotly_chart(plot_swing_overview(hist, swing, f"Swing Trading — {display_ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
            sw1, sw2, sw3 = st.columns(3)
            sw1.metric("Trendstärke (ADX)", f"{swing['adx']:.1f}" if swing['adx'] else "—", delta=swing["trend_strength"])
            sw2.metric("SMA-Cross", swing["cross_label"])
            sw3.metric("Richtung", swing["direction"])

            st.markdown("**Pivot-Levels (klassisch)**")
            pc1, pc2, pc3, pc4, pc5 = st.columns(5)
            pc1.metric("S2", f"{swing['s2']:,.2f} €")
            pc2.metric("S1", f"{swing['s1']:,.2f} €")
            pc3.metric("Pivot", f"{swing['pivot']:,.2f} €")
            pc4.metric("R1", f"{swing['r1']:,.2f} €")
            pc5.metric("R2", f"{swing['r2']:,.2f} €")

            if swing["stop_loss"] and swing["take_profit"]:
                st.markdown("**Risk / Reward Vorschlag** (Basis: 1.5× ATR Stop, 2.5× ATR Target)")
                rr1, rr2, rr3 = st.columns(3)
                rr1.metric("Stop Loss", f"{swing['stop_loss']:,.2f} €")
                rr2.metric("Take Profit", f"{swing['take_profit']:,.2f} €")
                rr3.metric("R:R Verhältnis", f"1:{swing['rr_ratio']:.1f}")

            if swing["cross_status"] == "bullish" and swing["direction"] == "aufwärts":
                st.success("✅ Bullishes Setup — Golden Cross + Kurs über SMA 20")
            elif swing["cross_status"] == "bearish" and swing["direction"] == "abwärts":
                st.warning("⚠️ Bearishes Setup — Death Cross + Kurs unter SMA 20")
            else:
                st.info("🟡 Gemischte Signale — keine klare Richtung")
            st.caption("ADX > 25 = starker Trend · ADX < 20 = seitwärts. Golden Cross = SMA 20 kreuzt SMA 50 von unten (bullish). Pivot-Points zeigen kurzfristige Support/Resistance-Zonen.")
        else:
            st.info("Nicht genügend Daten für die Swing-Trading-Analyse (min. 50 Tage).")

    with tab_flow:
        flow = calc_order_flow(hist["High"], hist["Low"], close, hist["Volume"])
        if flow:
            st.plotly_chart(plot_order_flow(hist, flow, f"Order Flow — {display_ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
            of1, of2, of3 = st.columns(3)
            of1.metric("VWAP Signal", flow["vwap_signal"].upper())
            of1.caption(flow["vwap_desc"])
            of2.metric("OBV Trend", flow["obv_signal"].upper())
            of2.caption(flow["obv_desc"])
            of3.metric("Point of Control", f"{flow['poc_price']:,.2f} €")
            of3.caption(f"Vol.-Spikes (20T): {flow['n_spikes_recent']}")

            bullish_count = sum(1 for s in [flow["vwap_signal"], flow["obv_signal"]] if s == "bullish")
            if bullish_count == 2: st.success("✅ Starker Kaufdruck — VWAP und OBV bestätigen bullishes Momentum")
            elif bullish_count == 0: st.warning("⚠️ Starker Verkaufsdruck — VWAP und OBV signalisieren Distribution")
            else: st.info("🟡 Gemischte Signale — kein eindeutiger Orderflow erkennbar")
            st.caption("VWAP = volumengewichteter Durchschnittspreis (Kurs darüber = Käufer dominieren). OBV = kumuliertes Volumen nach Kursrichtung (steigend = Akkumulation). POC = Point of Control (Preis mit dem höchsten gehandelten Volumen).")
        else:
            st.info("Nicht genügend Daten für die Order-Flow-Analyse (min. 20 Tage).")

    with tab_quant:
        st.markdown(f"#### {tab_name}")
        info_data = details.get("info", {})
        
        if sector_cat == "finanzen":
            st.caption("Excess Returns Model — misst die echte Kapitalrentabilität und identifiziert Bewertungsausschläge bei Zinszyklen.")
            from services.valuation import calc_excess_returns
            res = calc_excess_returns(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("Return on Equity (ROE)", f"{res['roe']*100:.1f} %")
            col2.metric("Cost of Equity (CAPM)", f"{res['cost_of_equity']*100:.1f} %")
            col3.metric("Excess Return Margin", f"{res['excess_return_margin']*100:.1f} %")
            if res['is_undervalued']: st.success("✅ **Unterbewertet:** Das ROE übersteigt die berechneten Kapitalkosten.")
            else: st.warning("⚠️ **Vorsicht:** Das ROE ist niedriger als die Kapitalkosten (Wertvernichtung).")
            st.markdown(f"**Weitere Parameter:**<br>Beta: {res['beta']:.2f} · Book Value: {res['book_value']:.2f} (Excess Value: {res['excess_return_value']:.2f}) · *Stable EPS*: N/A", unsafe_allow_html=True)
            
        elif sector_cat == "tech":
            st.caption("Rule of 40 & LTV/CAC-Framework — quantifiziert die Qualität des Wachstums vs. 'Value Traps'.")
            from services.valuation import calc_rule_of_40
            res = calc_rule_of_40(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("Revenue Growth", f"{res['revenue_growth']*100:.1f} %")
            col2.metric("FCF Margin", f"{res['fcf_margin']*100:.1f} %")
            col3.metric("Rule of 40 Score", f"{res['rule_of_40_score']:.1f}")
            if res['is_healthy']: st.success(f"✅ **Gesundes Wachstum:** Score ist >= 40 ({res['rule_of_40_score']:.1f}).")
            else: st.warning(f"⚠️ **Risiko:** Score ist < 40 ({res['rule_of_40_score']:.1f}).")
            st.markdown(f"**Weitere Parameter:**<br>LTV / CAC ratio: N/A", unsafe_allow_html=True)

        elif sector_cat == "hardware":
            st.caption("Vorlaufende EV/EBITDA-Zyklik & Book-to-Bill — antizipiert zyklische Cashflow-Revisionen.")
            from services.valuation import calc_hardware_cycle
            res = calc_hardware_cycle(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("EV / EBITDA", f"{res['ev_ebitda']:.1f}")
            col2.metric("Price to Book (Floor)", f"{res['price_to_book']:.1f}")
            col3.metric("Inventory Turnover", f"{res['inventory_turnover']:.1f}")
            if res['is_value_trap_warning']: st.warning("⚠️ **Value Trap Warnung:** Niedriges EV/EBITDA bei hohem P/B könnte ein Zyklus-Hoch signalisieren.")
            else: st.info("ℹ️ Keine akute 'Value Trap' auf Basis der aktuellen EV/EBITDA-Relation erkannt.")
            st.markdown(f"**Weitere Parameter:**<br>Book-to-Bill Ratio: {res['book_to_bill']}", unsafe_allow_html=True)

        elif sector_cat == "pharma":
            st.caption("rNPV (Risk-Adjusted Net Present Value) — isoliert das binäre technologische Risiko von Marktrisiko.")
            from services.valuation import calc_rnpv_proxy
            res = calc_rnpv_proxy(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("Enterprise Value", f"{res['ev']:,.0f} €" if res['ev'] else "N/A")
            col2.metric("Total Revenue", f"{res['revenue']:,.0f} €" if res['revenue'] else "N/A")
            col3.metric("EV to Sales", f"{res['ev_to_sales']:.1f}")
            st.info("ℹ️ Für eine echte rNPV-Kalkulation werden Pipeline-Daten (PTRS) benötigt.")
            st.markdown(f"**Weitere Parameter:**<br>Klinische Erfolgsraten (PTRS): {res['ptrs']}<br>rNPV Target: {res['rnpv']}", unsafe_allow_html=True)

        elif sector_cat == "energie":
            st.caption("EV / DACF (Debt-Adjusted Cash Flow) — bereinigt unterschiedliche Verschuldungsgrade für Peer-Vergleiche.")
            from services.valuation import calc_ev_dacf
            res = calc_ev_dacf(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("Enterprise Value", f"{res['ev']:,.0f} €" if res['ev'] else "N/A")
            col2.metric("Operating Cashflow", f"{res['operating_cashflow']:,.0f} €" if res['operating_cashflow'] else "N/A")
            col3.metric("EV / OCF (Proxy DACF)", f"{res['ev_to_ocf']:.1f}")
            if res['is_attractive']: st.success("✅ **Attraktiv:** EV/OCF ist auf einem niedrigen Niveau (< 8).")
            else: st.warning("⚠️ EV/OCF deutet nicht auf eine starke Unterbewertung hin oder Daten fehlen.")
            st.markdown(f"**Weitere Parameter:**<br>Reserven in BOE: {res['reserves_boe']}", unsafe_allow_html=True)

        elif sector_cat == "telekom":
            st.caption("ARPU-adjustiertes EV/EBITDA — blendet die Kosten der Kundenbindung aus & signalisiert Pricing-Power.")
            from services.valuation import calc_telecom_metrics
            res = calc_telecom_metrics(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("EV / EBITDA", f"{res['ev_ebitda']:.1f}")
            col2.metric("Dividend Yield", f"{res['dividend_yield']*100:.1f} %")
            col3.metric("Pricing-Power Indikation", "N/A")
            if res['is_cash_cow']: st.success("✅ Cash-Cow-Charakteristika: Solide Dividende & niedriges EV/EBITDA.")
            else: st.info("ℹ️ Werte für Cash-Cow (Dividende >4%, EV/EBITDA <10) nicht vollständig erfüllt.")
            st.markdown(f"**Weitere Parameter:**<br>Infrastruktur-Prämien: N/A<br>ARPU: {res['arpu']} · Subscriber Churn: {res['churn_rate']}", unsafe_allow_html=True)

        elif sector_cat == "logistik":
            st.caption("EV / EBITDAR — Leasing vs. Flottenbesitz verzerrt die Bilanz; diese Metrik neutralisiert dies.")
            from services.valuation import calc_logistics_metrics
            res = calc_logistics_metrics(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("EV / EBITDA", f"{res['ev_ebitda']:.1f}")
            col2.metric("EBITDA Margin", f"{res['ebitda_margin']*100:.1f} %")
            col3.metric("EV / EBITDAR", f"{res['ebitdar_proxy']}")
            st.info("ℹ️ EV/EBITDA als Proxy gewählt, detaillierte Rent-Adjustments erfordern Jahresbericht-Daten (10-K).")
            st.markdown(f"**Weitere Parameter:**<br>Load Factor / Tonnage: {res['load_factor']}", unsafe_allow_html=True)

        elif sector_cat == "defense":
            st.caption("Verteidigung & Luftfahrt — Hohe Visibilität durch Regierungsverträge; Stabilität der operativen Marge ist entscheidend.")
            from services.valuation import calc_defense_metrics
            res = calc_defense_metrics(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("EV / EBITDA", f"{res['ev_ebitda']:.1f}")
            col2.metric("Operative Marge", f"{res['operating_margin']*100:.1f} %")
            col3.metric("Order Backlog / Rev", res['backlog_to_revenue'])
            if res['is_highly_profitable']: st.success("✅ **Starkes Profil:** Solide Marge (>10%) bei fairem Multiple (<15x).")
            else: st.info("ℹ️ Eher neutrales oder teures Bewertungsprofil für Rüstung/Luftfahrt.")
            
        elif sector_cat == "auto":
            st.caption("Automobilindustrie — Kapitalintensiv; Effizienz bei der Nutzung der Assets (Fabriken etc.) und ROIC treiben die langfristige Bewertung.")
            from services.valuation import calc_auto_metrics
            res = calc_auto_metrics(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("Asset Turnover", f"{res['asset_turnover']:.2f}x")
            col2.metric("P/E (KGV)", f"{res['pe_ratio']:.1f}" if res['pe_ratio'] > 0 else "N/A")
            col3.metric("ROA (Proxy)", f"{res['roa_proxy_roic']*100:.1f} %")
            if res['is_efficient_allocator']: st.success("✅ **Effizienter Hersteller:** Dreht Assets schnell (>0.5x), macht Gewinn und ist günstig bewertet (KGV < 15).")
            else: st.info("ℹ️ Keine herausragende Kapitaleffizienz / Bewertung erkennbar.")

        elif sector_cat == "maschinenbau":
            st.caption("Maschinen- und Bauwesen — Starke Zykliker; Ein niedriges EV/EBITDA bei gleichzeitig hohem Buchwert-Premium kann auf nahende Zyklus-Spitzen hindeuten (Value Trap).")
            from services.valuation import calc_machinery_metrics
            res = calc_machinery_metrics(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("EV / EBITDA", f"{res['ev_ebitda']:.1f}")
            col2.metric("Price to Book", f"{res['price_to_book']:.1f}")
            col3.metric("ROA", f"{res['roa']*100:.1f} %")
            if res['is_value_trap_warning']: st.warning("⚠️ **Value Trap Warnung:** EV/EBITDA ist sehr niedrig (<8), aber KVB sehr hoch (>4). Der Markt preist womöglich nahende Gewinnrückgänge ein!")
            else: st.info("ℹ️ Keine direkte Warnung bzgl. des Zyklus-Tops erkennbar.")

        elif sector_cat == "industrie":
            st.caption("Asset-Based & EWEBIT — Hidden Champions outperformen den Markt durch systematisch höhere ROA.")
            from services.valuation import calc_hgb_proxy
            res = calc_hgb_proxy(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("Return on Assets (ROA)", f"{res['roa']*100:.1f} %")
            col2.metric("Price to Book", f"{res['price_to_book']:.1f}")
            col3.metric("Stille Reserven", "N/A")
            if res['is_hidden_champion']: st.success("✅ **Hidden Champion Profil:** ROA ist > 5% bei einem adäquaten Buchwert-Multiple.")
            else: st.info("ℹ️ Werte deuten auf kein explizites Outperformance-Setup aus der reinen Asset-Perspektive hin.")

        elif sector_cat == "csvs":
            st.caption("Chinese-Style Valuation System (CSVS) — targetiert die systematische Unterbewertung von kritischer Struktur bei hohem Dividenden-Fokus.")
            from services.valuation import calc_csvs
            res = calc_csvs(info_data)
            col1, col2, col3 = st.columns(3)
            col1.metric("Dividend Yield", f"{res['dividend_yield']*100:.1f} %")
            col2.metric("Price to Book", f"{res['price_to_book']:.1f}")
            col3.metric("Strategic Score", res['strategic_importance'])
            if res['is_undervalued_soe']: st.success("✅ **CSVS Unterbewertung:** Hohe Dividende (>5%) und niedriges P/B (<1) bei (potenziell) kritischer Infrastruktur.")
            else: st.info("ℹ️ Kein klassisches CSVS-Value-Play basierend auf P/B und Dividende.")

    with tab_options:
        st.markdown("#### 📋 Options Flow & Open Interest")
        st.caption("Options-Daten als Sentiment-Indikator: Put/Call Ratio, Max Pain, Implied vs. Historical Volatility.")

        with st.spinner("Lade Options-Daten …"):
            from services.cache import cached_options_overview
            opts = cached_options_overview(ticker)

        if opts is None:
            st.info("Keine Options-Daten verfügbar für diesen Ticker. "
                    "Options-Daten sind primär für US-Aktien zugänglich.")
        else:
            # Verfallstermin-Info
            st.markdown(f"**Verfallstermin:** `{opts.expiry_date}` "
                        f"({len(opts.available_expiries)} Termine verfügbar)")

            # ── Metriken-Übersicht ──
            oc1, oc2, oc3, oc4 = st.columns(4)

            # Put/Call Ratio
            with oc1:
                pc_val = f"{opts.pc_ratio_volume:.2f}" if opts.pc_ratio_volume else "—"
                sentiment_icon = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}.get(opts.pc_sentiment, "—")
                st.metric("P/C Ratio (Vol.)",
                          pc_val,
                          delta=f"{sentiment_icon} {opts.pc_sentiment}",
                          delta_color="off",
                          help="Put/Call Volume Ratio. >1.2 = Bearish (mehr Puts), <0.7 = Bullish (mehr Calls).")

            # Max Pain
            with oc2:
                mp_val = f"{opts.max_pain:,.2f} €" if opts.max_pain else "—"
                mp_delta = f"{opts.max_pain_distance_pct:+.1f} % vom Kurs" if opts.max_pain_distance_pct is not None else ""
                st.metric("Max Pain",
                          mp_val,
                          delta=mp_delta,
                          delta_color="off",
                          help="Preis bei dem die meisten Optionen wertlos verfallen. Kurse tendieren an Verfall dorthin.")

            # IV
            with oc3:
                iv_val = f"{opts.implied_vol:.1f} %" if opts.implied_vol else "—"
                st.metric("Implied Volatility",
                          iv_val,
                          help="Durchschnittliche ATM Implied Volatility. Misst die erwartete Schwankung.")

            # HV
            with oc4:
                hv_val = f"{opts.historical_vol:.1f} %" if opts.historical_vol else "—"
                iv_signal = opts.iv_hv_signal or ""
                signal_icon = {"IV Premium": "⬆️", "IV Discount": "⬇️", "Fair": "↔️"}.get(iv_signal, "")
                st.metric("Historical Volatility",
                          hv_val,
                          delta=f"{signal_icon} {iv_signal} (IV/HV: {opts.iv_hv_ratio:.2f})" if opts.iv_hv_ratio else "",
                          delta_color="off",
                          help="30-Tage historische Volatilität (annualisiert). Vergleich mit IV zeigt Über/Unterbewertung der Optionsprämie.")

            # Put/Call Beschreibung
            if opts.pc_description:
                if opts.pc_sentiment == "Bullish":
                    st.success(f"✅ {opts.pc_description}")
                elif opts.pc_sentiment == "Bearish":
                    st.warning(f"⚠️ {opts.pc_description}")
                else:
                    st.info(f"ℹ️ {opts.pc_description}")

            # IV vs HV Signal
            if opts.iv_hv_signal == "IV Premium":
                st.warning("⚠️ **IV Premium:** Optionsprämien sind überdurchschnittlich hoch — "
                          "der Markt erwartet stärkere Kursbewegungen als historisch üblich. "
                          "Oft vor Earnings oder Events.")
            elif opts.iv_hv_signal == "IV Discount":
                st.success("✅ **IV Discount:** Optionsprämien sind günstiger als üblich — "
                          "keine außergewöhnliche Volatilitätserwartung eingepreist.")

            # ── Top Strikes nach OI ──
            st.markdown("---")
            st.markdown("##### Top Strikes nach Open Interest")

            top_col1, top_col2 = st.columns(2)
            with top_col1:
                st.markdown("**🟢 Top Calls (Resistance / Targets)**")
                if opts.top_call_strikes:
                    for i, s in enumerate(opts.top_call_strikes, 1):
                        st.markdown(
                            f"<div style='background:#1e293b;padding:6px 12px;border-radius:6px;"
                            f"border-left:3px solid #22c55e;margin-bottom:4px;font-size:0.85rem;'>"
                            f"<b>${s['strike']:,.0f}</b> · "
                            f"OI: {s['open_interest']:,} · "
                            f"Vol: {s['volume']:,} · "
                            f"IV: {s['iv']:.0f}%"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("Keine Call-OI-Daten verfügbar.")

            with top_col2:
                st.markdown("**🔴 Top Puts (Support / Hedges)**")
                if opts.top_put_strikes:
                    for i, s in enumerate(opts.top_put_strikes, 1):
                        st.markdown(
                            f"<div style='background:#1e293b;padding:6px 12px;border-radius:6px;"
                            f"border-left:3px solid #ef4444;margin-bottom:4px;font-size:0.85rem;'>"
                            f"<b>${s['strike']:,.0f}</b> · "
                            f"OI: {s['open_interest']:,} · "
                            f"Vol: {s['volume']:,} · "
                            f"IV: {s['iv']:.0f}%"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("Keine Put-OI-Daten verfügbar.")

            # ── Unusual Activity ──
            if opts.unusual_calls or opts.unusual_puts:
                st.markdown("---")
                st.markdown("##### 🔥 Ungewöhnliche Options-Aktivität")
                st.caption("Strikes mit Volume > 5× Open Interest — möglicher Hinweis auf große Block-Trades.")

                for item in opts.unusual_calls + opts.unusual_puts:
                    tag = "CALL" if item["type"] == "call" else "PUT"
                    tag_color = "#22c55e" if item["type"] == "call" else "#ef4444"
                    dist = f" ({item['distance_pct']:+.1f}% vom Kurs)" if item.get("distance_pct") is not None else ""
                    st.markdown(
                        f"<div style='background:#1e293b;padding:8px 14px;border-radius:6px;"
                        f"margin-bottom:4px;font-size:0.85rem;'>"
                        f"<span style='background:{tag_color};color:#fff;padding:2px 8px;border-radius:4px;"
                        f"font-weight:600;font-size:0.75rem;'>{tag}</span> "
                        f"<b>${item['strike']:,.0f}</b>{dist} · "
                        f"Vol: <b>{item['volume']:,}</b> vs OI: {item['open_interest']:,} "
                        f"({item['vol_oi_ratio']:.0f}x)"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            st.caption("Put/Call Ratio: <0.7 = bullish, 0.7-1.2 = neutral, >1.2 = bearish. "
                       "Max Pain: Preislevel bei dem am meisten Optionen wertlos verfallen — "
                       "der Kurs tendiert am Verfallstag oft in diese Richtung.")

    # ── Block 4: Innerer Wert (DCF) ────────────────────────────────────
    st.markdown("---")
    st.markdown("### 💰 Innerer Wert (DCF-Modell)")
    st.caption("Vereinfachtes Discounted-Cashflow-Modell — schätzt den fairen Wert basierend auf prognostizierten Free Cashflows.")

    info_data = details.get("info", {})
    dcf = calc_dcf_valuation(info_data)
    if dcf:
        dc1, dc2, dc3, dc4 = st.columns(4)
        dc1.metric("Fair Value (DCF)", f"{dcf['fair_value']:,.2f} €")
        dc2.metric("Aktueller Kurs", f"{dcf['current_price']:,.2f} €")
        delta_color = "normal" if dcf['upside_pct'] > 0 else "inverse"
        dc3.metric("Upside / Downside", f"{dcf['upside_pct']:+.1f} %", delta=f"{dcf['upside_pct']:+.1f} %", delta_color=delta_color)
        dc4.metric("WACC", f"{dcf['wacc']:.1f} %")

        if dcf['margin_of_safety']:
            st.success(f"✅ **Margin of Safety vorhanden:** Fair Value ({dcf['fair_value']:,.2f} €) liegt > 20% über dem aktuellen Kurs.")
        elif dcf['upside_pct'] > 0:
            st.info(f"ℹ️ Leichtes Upside-Potenzial ({dcf['upside_pct']:+.1f} %), aber noch keine volle Margin of Safety.")
        else:
            st.warning(f"⚠️ Aktie erscheint überbewertet ({dcf['upside_pct']:+.1f} % vs. DCF Fair Value).")

        def _fmt_big(val):
            if val >= 1e12: return f"{val/1e12:.1f} Bio."
            if val >= 1e9: return f"{val/1e9:.1f} Mrd."
            if val >= 1e6: return f"{val/1e6:.1f} Mio."
            return f"{val:,.0f}"

        st.caption(f"Annahmen: Wachstum {dcf['growth_used']:.1f}% (abflachend) · WACC {dcf['wacc']:.1f}% (EK-Anteil {dcf.get('equity_weight', 70):.0f}%) · Terminal Growth {dcf.get('terminal_growth_used', 2.5):.1f}% · FCF Basis: {_fmt_big(dcf['fcf'])} €")
    else:
        st.info("ℹ️ DCF-Berechnung nicht möglich (kein positiver Free Cashflow oder fehlende Daten).")

    # ── Block 5: Bilanzqualität ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏦 Bilanzqualität & Verschuldung")

    balance = calc_balance_sheet_quality(info_data)
    if balance:
        st.markdown(f"**Bewertung: {balance['label']}**")
        bc1, bc2, bc3, bc4 = st.columns(4)
        bc1.metric("Debt / Equity", f"{balance['debt_to_equity']:.1f} %" if balance['debt_to_equity'] else "—",
                   help="Gesamtverschuldung / Eigenkapital. < 50% = konservativ, > 150% = aggressiv.")
        bc2.metric("Current Ratio", f"{balance['current_ratio']:.2f}" if balance['current_ratio'] else "—",
                   help="Kurzfristige Vermögenswerte / kurzfristige Verbindlichkeiten. > 1.5 = solide Liquidität.")
        bc3.metric("Net Debt / EBITDA", f"{balance['net_debt_ebitda']:.1f}x" if balance['net_debt_ebitda'] is not None else "—",
                   help="Nettoverschuldung / EBITDA. < 2x = komfortabel, > 4x = hohe Belastung.")

        def _fmt_balance(val):
            if abs(val) >= 1e9: return f"{val/1e9:.1f} Mrd. €"
            if abs(val) >= 1e6: return f"{val/1e6:.1f} Mio. €"
            return f"{val:,.0f} €"

        bc4.metric("Cash-Position", _fmt_balance(balance['total_cash']))

        for w in balance.get('warnings', []):
            st.warning(f"⚠️ {w}")
    else:
        st.info("ℹ️ Bilanzkennzahlen nicht verfügbar.")

    # ── Block 6: Margen- & Cashflow-Trends ──────────────────────────────
    st.markdown("---")
    st.markdown("### 📈 Margen- & Cashflow-Trends")

    with st.spinner("Lade Margen-Daten …"):
        margins = get_margin_trends(ticker)

    if margins and len(margins) >= 2:
        import plotly.graph_objects as go
        fig_m = go.Figure()
        years = [str(m['year']) for m in margins]

        for name, key, color in [
            ("Bruttomarge", "gross_margin", "#22c55e"),
            ("EBITDA-Marge", "ebitda_margin", "#3b82f6"),
            ("Nettomarge", "net_margin", "#a855f7"),
        ]:
            vals = [m.get(key) for m in margins]
            if any(v is not None for v in vals):
                fig_m.add_trace(go.Scatter(x=years, y=vals, name=name, mode="lines+markers", line=dict(color=color, width=2)))

        fig_m.update_layout(
            template="plotly_dark", height=350,
            yaxis_title="Marge (%)", xaxis_title="Jahr",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(l=40, r=20, t=30, b=40),
        )
        st.plotly_chart(fig_m, use_container_width=True, config={"displayModeBar": False})

        # FCF Tabelle
        fcf_data = [{"Jahr": str(m['year']), "FCF": f"{m['fcf']:,.0f} €" if m.get('fcf') else "—"} for m in margins]
        if any(m.get('fcf') for m in margins):
            st.markdown("**Free Cashflow pro Jahr**")
            st.dataframe(pd.DataFrame(fcf_data), use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Nicht genügend Finanzdaten für Margen-Trends verfügbar.")

    # ── Block 7: Peer-Vergleich ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🏭 Peer-Vergleich (Sektor)")
    st.caption("Vergleich mit Unternehmen aus der gleichen Branche (S&P 500 Universum).")

    yfin_sector_raw = info_data.get("sector", "")
    yfin_industry_raw = info_data.get("industry", "")

    with st.spinner("Lade Peer-Vergleich …"):
        peers = get_sector_peers(ticker, yfin_sector_raw, yfin_industry_raw)

    if peers is not None and not peers.empty:
        def _highlight_self(row):
            if row["Ticker"].upper() == ticker.upper():
                return ["background-color: rgba(59, 130, 246, 0.2)"] * len(row)
            return [""] * len(row)
        st.dataframe(peers.style.apply(_highlight_self, axis=1), use_container_width=True, hide_index=True)
        st.caption(f"Die hervorgehobene Zeile zeigt {display_ticker}.")
    else:
        st.info("ℹ️ Peer-Vergleich nicht verfügbar (Branche nicht im S&P 500 gefunden oder keine Daten).")

    # ── Block 8: Dividendenanalyse ───────────────────────────────────────
    st.markdown("---")
    st.markdown("### 💎 Dividendenanalyse")

    with st.spinner("Lade Dividendendaten …"):
        div_data = calc_dividend_analysis(ticker)

    if div_data:
        if div_data['has_dividends']:
            dv1, dv2, dv3, dv4 = st.columns(4)
            dv1.metric("Aktuelle Rendite", f"{div_data['current_yield']:.2f} %")
            dv2.metric("Payout Ratio", f"{div_data['payout_ratio']:.1f} %",
                       help="Anteil des Gewinns, der als Dividende ausgeschüttet wird. < 60% = nachhaltig.")
            dv3.metric("Wachstum (CAGR)", f"{div_data['growth_rate']:.1f} %" if div_data['growth_rate'] else "—")
            dv4.metric("Streak (Jahre ↑)", f"{div_data['streak']} Jahre" if div_data['streak'] > 0 else "—")

            if div_data['annual_dividends']:
                import plotly.graph_objects as go
                div_years = [str(d['year']) for d in div_data['annual_dividends']]
                div_amounts = [d['amount'] for d in div_data['annual_dividends']]
                fig_div = go.Figure(go.Bar(x=div_years, y=div_amounts, marker_color="#22c55e"))
                fig_div.update_layout(
                    template="plotly_dark", height=300,
                    yaxis_title="Dividende (€)", xaxis_title="Jahr",
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                st.plotly_chart(fig_div, use_container_width=True, config={"displayModeBar": False})

            if div_data['payout_ratio'] > 80:
                st.warning("⚠️ Hohe Ausschüttungsquote (> 80%). Die Dividende könnte langfristig nicht nachhaltig sein.")
            elif div_data['streak'] >= 10:
                st.success(f"✅ Dividendenaristokrat: {div_data['streak']} Jahre in Folge erhöht!")
        else:
            st.info("ℹ️ Dieses Unternehmen zahlt aktuell keine Dividende.")
    else:
        st.info("ℹ️ Dividendendaten nicht verfügbar.")

    # ── Block 9: Insider & Institutionelle ────────────────────────────────
    st.markdown("---")
    st.markdown("### 👔 Insider & Institutionelle Investoren")

    with st.spinner("Lade Insider-Daten …"):
        insider = get_insider_institutional(ticker)

    if insider:
        tab_insider, tab_inst = st.tabs(["🔑 Insider-Transaktionen", "🏛️ Top Institutionelle"])

        with tab_insider:
            if insider['has_insider_data']:
                st.dataframe(insider['insider_df'], use_container_width=True, hide_index=True)
                ic1, ic2 = st.columns(2)
                ic1.metric("Insider Käufe", insider['net_buys'])
                ic2.metric("Insider Verkäufe", insider['net_sells'])
                if insider['net_buys'] > insider['net_sells']:
                    st.success("✅ Netto-Käufe: Insider kaufen mehr als sie verkaufen — bullisches Signal.")
                elif insider['net_sells'] > insider['net_buys']:
                    st.warning("⚠️ Netto-Verkäufe: Insider verkaufen mehr. Kann verschiedene Gründe haben (Steuerplanung, Diversifikation).")
            else:
                st.info("ℹ️ Keine Insider-Transaktionen verfügbar (nur für US-Aktien via SEC-Filings).")

        with tab_inst:
            if insider['has_institutional_data']:
                st.dataframe(insider['institutional_df'], use_container_width=True, hide_index=True)
            else:
                st.info("ℹ️ Keine institutionellen Daten verfügbar.")
    else:
        st.info("ℹ️ Insider- und institutionelle Daten konnten nicht geladen werden.")

    # ── Block 10: Analysten-Konsens ──────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎯 Analysten-Konsens")

    with st.spinner("Lade Analysten-Daten …"):
        analyst = get_analyst_consensus(ticker)

    if analyst and analyst.get('target_mean'):
        ac1, ac2, ac3, ac4 = st.columns(4)
        ac1.metric("Konsens-Kursziel", f"{analyst['target_mean']:,.2f} €")
        ac2.metric("Spanne", f"{analyst['target_low']:,.2f} — {analyst['target_high']:,.2f} €" if analyst['target_low'] and analyst['target_high'] else "—")
        if analyst['upside_pct']:
            delta_color = "normal" if analyst['upside_pct'] > 0 else "inverse"
            ac3.metric("Potenzial", f"{analyst['upside_pct']:+.1f} %", delta=f"{analyst['upside_pct']:+.1f} %", delta_color=delta_color)
        else:
            ac3.metric("Potenzial", "—")

        rec_display = {
            "strongBuy": "⬆️ Strong Buy", "buy": "🟢 Buy", "hold": "🟡 Hold",
            "sell": "🔴 Sell", "strongSell": "⬇️ Strong Sell"
        }
        ac4.metric("Empfehlung", rec_display.get(analyst['recommendation'], analyst['recommendation']))

        if analyst['num_analysts']:
            st.caption(f"Basierend auf {analyst['num_analysts']} Analysten. Konsensus-Score: {analyst['recommendation_mean']}/5 (1 = Strong Buy, 5 = Sell).")
    else:
        st.info("ℹ️ Keine Analysten-Daten verfügbar.")

    # ── Block 11: Earnings Surprise History ──────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Earnings Surprise History")
    st.caption("Historische EPS-Überraschungen und Post-Earnings-Drift — zeigt, wie der Markt auf Quartalsergebnisse reagiert hat.")

    with st.spinner("Lade Earnings-Daten …"):
        from services.earnings import get_earnings_history
        earnings_profile = get_earnings_history(ticker)

    if earnings_profile and earnings_profile.events:
        ep = earnings_profile

        # Nächstes Earnings-Datum
        if ep.next_earnings_date:
            try:
                next_ed = ep.next_earnings_date
                if hasattr(next_ed, 'tzinfo') and next_ed.tzinfo:
                    from datetime import timezone
                    next_ed = next_ed.replace(tzinfo=None)
                days_until = (next_ed - datetime.now()).days
                if days_until >= 0:
                    st.info(f"📅 **Nächste Quartalszahlen:** {next_ed.strftime('%d.%m.%Y')} (in {days_until} Tagen)")
                else:
                    st.caption(f"📅 Letzte gemeldete Earnings: {next_ed.strftime('%d.%m.%Y')}")
            except Exception:
                pass

        # Statistik-Header
        ec1, ec2, ec3, ec4, ec5 = st.columns(5)
        ec1.metric("Quarters", f"{ep.total_quarters}")
        ec2.metric("Beats 🟢", f"{ep.beats}", delta=f"{ep.beat_rate:.0f}%", delta_color="off")
        ec3.metric("Misses 🔴", f"{ep.misses}")
        ec4.metric("Ø Surprise", f"{ep.avg_surprise_pct:+.1f}%")
        ec5.metric("Ø Drift (1T)", f"{ep.avg_drift_1d:+.2f}%" if ep.avg_drift_1d is not None else "—")

        # Tabs: Chart + Drift + Tabelle
        tab_eps_chart, tab_drift, tab_history = st.tabs([
            "📊 EPS Chart", "📈 Post-Earnings Drift", "📋 Historie"
        ])

        with tab_eps_chart:
            # EPS Actual vs. Estimate Bar-Chart
            import plotly.graph_objects as go

            # Chronologisch sortieren (älteste zuerst für Chart)
            chart_events = sorted(ep.events, key=lambda e: e.date)
            # Max 12 Quarters für Lesbarkeit
            chart_events = chart_events[-12:]

            quarters = [e.quarter for e in chart_events]
            actuals = [e.eps_actual for e in chart_events]
            estimates = [e.eps_estimate for e in chart_events]

            fig_eps = go.Figure()

            # Estimate Bars (hinterlegt)
            fig_eps.add_trace(go.Bar(
                x=quarters, y=estimates,
                name="EPS Estimate",
                marker_color="rgba(100, 200, 255, 0.4)",
                marker_line_color="#64C8FF",
                marker_line_width=1,
            ))

            # Actual Bars (vorne) mit Farbcodierung
            bar_colors = []
            for e in chart_events:
                if e.result == "Beat":
                    bar_colors.append("#22c55e")
                elif e.result == "Miss":
                    bar_colors.append("#ef4444")
                else:
                    bar_colors.append("#eab308")

            fig_eps.add_trace(go.Bar(
                x=quarters, y=actuals,
                name="EPS Actual",
                marker_color=bar_colors,
                marker_line_width=0,
            ))

            fig_eps.update_layout(
                template="plotly_dark",
                height=380,
                barmode="group",
                yaxis_title="EPS ($)",
                xaxis_title="Quartal",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=50, r=20, t=30, b=50),
                xaxis_tickangle=-45,
            )
            st.plotly_chart(fig_eps, use_container_width=True, config={"displayModeBar": False})

            # Surprise-Summary
            if ep.beat_rate >= 75:
                st.success(f"✅ **Starker Earnings-Track-Record:** {ep.beat_rate:.0f}% der Quartale geschlagen (Beat-Rate).")
            elif ep.beat_rate >= 50:
                st.info(f"ℹ️ **Solider Track-Record:** {ep.beat_rate:.0f}% Beat-Rate über {ep.total_quarters} Quartale.")
            else:
                st.warning(f"⚠️ **Schwacher Track-Record:** Nur {ep.beat_rate:.0f}% Beat-Rate — häufig unter den Erwartungen.")

        with tab_drift:
            st.markdown("##### Kursreaktion nach Earnings-Veröffentlichung")
            st.caption("Zeigt, wie sich der Kurs 1, 5 und 20 Handelstage nach der Earnings-Veröffentlichung entwickelt hat.")

            # Drift-Durchschnitt nach Ergebnis
            drift_col1, drift_col2, drift_col3 = st.columns(3)

            with drift_col1:
                st.markdown("**Ø Drift nach Beat**")
                if ep.avg_beat_drift_1d is not None:
                    color = "#22c55e" if ep.avg_beat_drift_1d >= 0 else "#ef4444"
                    st.markdown(f"<span style='font-size:1.5rem;color:{color};font-weight:bold'>{ep.avg_beat_drift_1d:+.2f}%</span> (1 Tag)", unsafe_allow_html=True)
                else:
                    st.write("—")

            with drift_col2:
                st.markdown("**Ø Drift nach Miss**")
                if ep.avg_miss_drift_1d is not None:
                    color = "#22c55e" if ep.avg_miss_drift_1d >= 0 else "#ef4444"
                    st.markdown(f"<span style='font-size:1.5rem;color:{color};font-weight:bold'>{ep.avg_miss_drift_1d:+.2f}%</span> (1 Tag)", unsafe_allow_html=True)
                else:
                    st.write("—")

            with drift_col3:
                st.markdown("**Ø Drift (gesamt)**")
                vals = []
                for label, val in [("1T", ep.avg_drift_1d), ("5T", ep.avg_drift_5d), ("20T", ep.avg_drift_20d)]:
                    if val is not None:
                        color = "#22c55e" if val >= 0 else "#ef4444"
                        vals.append(f"{label}: <span style='color:{color};font-weight:bold'>{val:+.2f}%</span>")
                if vals:
                    st.markdown("<br>".join(vals), unsafe_allow_html=True)
                else:
                    st.write("—")

            # Drift-Chart: Scatter mit 1d/5d/20d
            drift_events = sorted(
                [e for e in ep.events if e.drift_1d is not None],
                key=lambda e: e.date
            )[-12:]

            if drift_events:
                fig_drift = go.Figure()

                d_quarters = [e.quarter for e in drift_events]
                d_colors = ["#22c55e" if e.result == "Beat" else "#ef4444" if e.result == "Miss" else "#eab308" for e in drift_events]

                for days_label, get_val, color in [
                    ("1 Tag", lambda e: e.drift_1d, "#64C8FF"),
                    ("5 Tage", lambda e: e.drift_5d, "#a855f7"),
                    ("20 Tage", lambda e: e.drift_20d, "#f97316"),
                ]:
                    vals = [get_val(e) for e in drift_events]
                    fig_drift.add_trace(go.Scatter(
                        x=d_quarters, y=vals,
                        name=days_label,
                        mode="lines+markers",
                        line=dict(color=color, width=2),
                        marker=dict(size=8),
                    ))

                # Nulllinie
                fig_drift.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")

                fig_drift.update_layout(
                    template="plotly_dark",
                    height=350,
                    yaxis_title="Kursänderung (%)",
                    xaxis_title="Quartal",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    margin=dict(l=50, r=20, t=30, b=50),
                    xaxis_tickangle=-45,
                )
                st.plotly_chart(fig_drift, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Nicht genügend Drift-Daten verfügbar.")

        with tab_history:
            st.markdown("##### Vollständige Earnings-Historie")

            history_rows = []
            for e in ep.events:
                surprise_str = f"{e.surprise_pct:+.1f}%" if e.surprise_pct is not None else "—"
                result_icon = "🟢" if e.result == "Beat" else "🔴" if e.result == "Miss" else "🟡"

                history_rows.append({
                    "": result_icon,
                    "Quartal": e.quarter,
                    "Datum": e.date.strftime("%d.%m.%Y") if hasattr(e.date, 'strftime') else str(e.date)[:10],
                    "EPS Actual": f"${e.eps_actual:.2f}" if e.eps_actual is not None else "—",
                    "EPS Estimate": f"${e.eps_estimate:.2f}" if e.eps_estimate is not None else "—",
                    "Surprise": surprise_str,
                    "Ergebnis": e.result,
                    "Drift 1T": f"{e.drift_1d:+.2f}%" if e.drift_1d is not None else "—",
                    "Drift 5T": f"{e.drift_5d:+.2f}%" if e.drift_5d is not None else "—",
                    "Drift 20T": f"{e.drift_20d:+.2f}%" if e.drift_20d is not None else "—",
                    "Kurs": f"${e.price_at_earnings:,.2f}" if e.price_at_earnings else "—",
                })

            df_earnings = pd.DataFrame(history_rows)
            st.dataframe(
                df_earnings,
                use_container_width=True,
                hide_index=True,
                height=min(400, 35 * len(history_rows) + 38),
            )

        st.caption("⚠️ Post-Earnings Drift basiert auf historischen Schlusskursen. Die tatsächliche Kursreaktion am Earnings-Tag kann durch After-Hours-Handel abweichen.")
    else:
        st.info("ℹ️ Keine Earnings-Daten für dieses Unternehmen verfügbar (nur bei US-Aktien mit ausreichender Historie).")

    # ── Zusammenfassung (Gesamtbewertung) ─────────────────────────────
    st.markdown("---")
    st.markdown("### 📝 Zusammenfassung")
    st.caption("Gewichtete Momentaufnahme — Trend (30%), Volumen (25%), Fundamentaldaten (30%), Oszillatoren (15%).")

    with st.spinner("Erstelle Zusammenfassung …"):
        sum_data = calc_technical_summary(stats, hist, info=details.get("info", {}), ticker=ticker)

    confidence = sum_data.get('confidence', 50)
    score_label = sum_data['score_label']
    confidence_label = sum_data.get('confidence_label', '')

    col_conf, col_text = st.columns([1, 3])
    with col_conf:
        # Farbe basierend auf Confidence
        if confidence >= 60:
            conf_color = "#22c55e"
        elif confidence >= 45:
            conf_color = "#eab308"
        else:
            conf_color = "#ef4444"
        st.markdown(f"<div style='text-align:center;'><span style='font-size:3rem;font-weight:bold;color:{conf_color};'>{confidence:.0f}</span><br><span style='color:#aaa;font-size:0.85rem;'>/ 100 Confidence</span></div>", unsafe_allow_html=True)

    with col_text:
        st.markdown(f"#### Momentaufnahme: **{score_label}**")
        st.caption(f"{confidence_label} — Gewichtete Auswertung aus Trend, Volumen, Fundamentaldaten und Oszillatoren.")

    # ── Explizite Kaufempfehlung ──────────────────────────────────────
    if confidence >= 70:
        st.success(f"🟢 **Kaufempfehlung — KAUFEN** | Confidence {confidence:.0f}/100: Technisch und fundamental überzeugendes Setup. Risk/Reward spricht für einen Einstieg.")
    elif confidence >= 55:
        st.warning(f"🟡 **Kaufempfehlung — HALTEN / BEOBACHTEN** | Confidence {confidence:.0f}/100: Gemischte Signale. Auf Bestätigung (z.B. Pullback an Support) warten.")
    elif confidence >= 40:
        st.info(f"➖ **Kaufempfehlung — NEUTRAL** | Confidence {confidence:.0f}/100: Kein klares Setup. Abseits bleiben oder nur mit kleiner Position.")
    else:
        st.error(f"🔴 **Kaufempfehlung — NICHT KAUFEN / VERKAUFEN** | Confidence {confidence:.0f}/100: Technisch und/oder fundamental kritisches Bild. Bestehende Positionen absichern.")

    # Kategorie-Breakdown
    cat_scores = sum_data.get('cat_scores', {})
    cat_max = sum_data.get('cat_max', {})
    weights = sum_data.get('weights', {})
    cat_labels = {"trend": "📊 Trend (30%)", "volume": "📈 Volumen (25%)", 
                  "fundamental": "🏦 Fund. (20%)", "sentiment": "📰 NLP (15%)", 
                  "oscillator": "⚡ Osz. (10%)"}
    
    cols = st.columns(5)
    for col_ui, (cat, label) in zip(cols, cat_labels.items()):
        mx = cat_max.get(cat, 1) or 1
        val = cat_scores.get(cat, 0)
        pct = round((val / mx + 1) / 2 * 100)
        pct = max(0, min(100, pct))
        col_ui.metric(label, f"{pct}%", delta=f"{val:+}/{mx}", delta_color="off")

    st.markdown("##### 📌 Synthese & Interpretation")
    st.info(f"**Makro-Bild (Trend):** {sum_data['macro']}")
    st.info(f"**Mikro-Bild (Momentum):** {sum_data['micro']}")
    st.success(f"**Actionable Insight:** {sum_data['actionable']}")

    st.markdown("##### 🔍 Indikatoren-Checkliste")
    if sum_data["checklist"]:
        df_check = pd.DataFrame(sum_data["checklist"])
        st.dataframe(df_check, use_container_width=True, hide_index=True)

    # ── Historische Signale für diesen Ticker ──────────────────────────
    from models.signal import SignalStore
    from services.signal_history import update_stale_signals
    
    # Im Hintergrund alte Signale bewerten
    try:
        update_stale_signals()
    except Exception:
        pass
        
    hist_signals = SignalStore.get_all(ticker=ticker, limit=5)
    if hist_signals:
        st.markdown("##### 📡 Signal-Historie (Letzte 5)")
        st.caption("Das Dashboard speichert automatisch Bewertungssignale, um die eigene Trefferquote zu messen.")
        
        hist_rows = []
        for s in hist_signals:
            try:
                date_str = datetime.fromisoformat(s.timestamp).strftime("%d.%m.%Y %H:%M")
            except:
                date_str = s.timestamp
                
            outcome = "⏳ Ausstehend"
            if s.was_successful is True:
                outcome = "✅ Gewonnen"
            elif s.was_successful is False:
                outcome = "❌ Verloren"
                
            hist_rows.append({
                "Datum": date_str,
                "Signal": "KAUFEN 🟢" if s.signal_type == "buy" else ("VERKAUFEN 🔴" if s.signal_type == "sell" else "NEUTRAL 🟡"),
                "Score": f"{s.confidence:.0f}",
                "Kurs (damals)": f"{s.price_at_signal:,.2f} €",
                "Ergebnis (1M)": outcome,
            })
            
        st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)

    # ── Position Sizing (Kelly + ATR) ─────────────────────────────────
    st.markdown("---")
    st.markdown("### 📐 Position Sizing (Kelly + ATR)")
    st.caption("Bestimmt, wie viele Aktien du kaufen solltest — basierend auf deinem Gesamtkapital, dem aktuellen Kurs (= Entry) und der Volatilität (ATR).")

    atr_series = calc_atr(hist["High"], hist["Low"], hist["Close"], 14)
    atr_current = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else None

    if atr_current:
        ps_col1, ps_col2 = st.columns([1, 1])
        with ps_col1:
            portfolio_val = st.number_input(
                "💰 Portfoliowert (€)", min_value=100, max_value=100_000_000,
                value=10000, step=1000, key="portfolio_value_input"
            )
        with ps_col2:
            max_risk = st.slider(
                "⚠️ Max. Verlust pro Trade (% vom Portfolio)",
                min_value=0.5, max_value=5.0,
                value=2.0, step=0.5, key="max_risk_slider",
                help="Wie viel % deines Gesamtportfolios du maximal bei EINEM Trade verlieren willst, wenn der Stop-Loss greift. Beispiel: 2% von 10.000€ = max. 200€ Verlust."
            )

        ps = calc_position_sizing(
            current_price=stats['current_price'],
            atr_val=atr_current,
            portfolio_value=portfolio_val,
            max_risk_pct=max_risk / 100
        )
        if ps:
            # Zeile 1: Entry + Stückzahl + Positionswert + Risiko
            ps0, ps1, ps2, ps3 = st.columns(4)
            ps0.metric("Entry (Aktueller Kurs)", f"{stats['current_price']:,.2f} €")
            ps1.metric("Empfohlene Stückzahl", f"{ps['shares']} Stück")
            ps2.metric("Positionswert", f"{ps['position_value']:,.2f} €", delta=f"{ps['position_pct']:.1f}% des Portfolios", delta_color="off")
            ps3.metric("Max. Verlust bei Stop", f"{ps['risk_eur']:,.2f} €", delta=f"{max_risk:.1f}% vom Portfolio", delta_color="off")

            # Zeile 2: Stop + TP + Kelly
            ps5, ps6, ps7, ps8 = st.columns(4)
            ps5.metric("Stop-Loss", f"{ps['stop_loss']:,.2f} €", delta=f"-{ps['stop_distance']:,.2f} (1.5× ATR)", delta_color="off")
            ps6.metric("Take-Profit", f"{ps['take_profit']:,.2f} €", delta=f"+{2.5 * atr_current:,.2f} (2.5× ATR)", delta_color="off")
            ps7.metric("Kelly-Anteil", f"{ps['kelly_fraction_pct']:.1f}%", help="Kelly Criterion: Mathematisch optimaler Portfolioanteil für maximales Compounding.")
            ps8.metric("Kelly-Stückzahl", f"{ps['kelly_shares']} Stück", help="Optimale Stückzahl nach Kelly-Formel (gekappt bei 25% des Portfolios).")

            st.markdown("""<div style='background:rgba(59,130,246,0.08);border-left:3px solid #3b82f6;padding:10px 14px;border-radius:6px;margin-top:8px;font-size:0.88rem;'>
<b>So liest du das:</b><br>
• <b>Entry</b> = Aktueller Kurs der Aktie (dein Einstiegspunkt)<br>
• <b>Stop-Loss</b> = 1,5× ATR unter dem Entry — wird der Kurs bis hierhin fallen, verkaufst du automatisch, um deinen Verlust zu begrenzen<br>
• <b>Take-Profit</b> = 2,5× ATR über dem Entry — hier nimmst du Gewinn mit (R:R ≈ 1:1,67)<br>
• <b>Max. Verlust bei Stop</b> = Der Euro-Betrag, den du bei <i>diesem</i> Trade maximal verlierst (gesteuert durch den Slider)<br>
• <b>Kelly-Anteil</b> = Die mathematisch optimale Positionsgröße für maximalen Vermögenszuwachs (Compounding). Wird bei 25% gekappt, um Überexposition zu vermeiden.
</div>""", unsafe_allow_html=True)
    else:
        st.info("Nicht genügend Daten für die Position-Sizing-Berechnung (ATR nicht verfügbar).")

    st.caption("⚠️ **Hinweis:** Dies ist eine algorithmische Momentaufnahme basierend auf technischen Indikatoren und fundamentalen Kennzahlen. Sie dient als Entscheidungshilfe, nicht als Anlageberatung.")

    st.markdown("---")
    st.markdown(f"### 📰 Nachrichten zu {stats['name']}")
    with st.spinner("Lade Nachrichten …"):
        company_news = cached_company_news(ticker)
    if company_news:
        _render_news_list(company_news)
        st.caption("Quelle: Yahoo Finance (Reuters, Bloomberg, etc.)")
    else:
        st.info(f"Keine Nachrichten für {display_ticker} verfügbar.")
