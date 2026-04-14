"""
views/pages/analysis.py — Orchestrierung der Analyse-Seite.

Delegiert die Darstellung an Module in views/sections/:
- analysis_overview:     Metriken-Header (Kurs, SMAs, Fundamentals)
- analysis_financials:   Gemeldete Quartalszahlen
- analysis_charts:       8 Tech-Chart-Tabs (Candlestick, RSI, MACD, ...)
- analysis_smc:          Liquidity Sweeps, SMC, Swing, Order Flow
- analysis_valuation:    Quant, Options Flow, DCF, Bilanz, Margen
- analysis_fundamentals: Peers, Dividende, Insider, Analysten, Earnings
- analysis_summary:      Gesamtbewertung, Signal-Historie, Position Sizing, News
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from services.watchlist import load_watchlist, resolve_ticker
from services.cache import cached_stock_details

# Section-Module
from views.sections.analysis_overview import render_overview
from views.sections.analysis_financials import render_financials
from views.sections.analysis_charts import render_charts
from views.sections.analysis_smc import render_smc
from views.sections.analysis_valuation import render_valuation
from views.sections.analysis_fundamentals import render_fundamentals
from views.sections.analysis_summary import render_summary


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
    
    today = datetime.now()
    if time_filter == "1 Tag" and today.weekday() >= 5:
        st.info("ℹ️ **Es ist Wochenende.** Der 1-Tages-Graph zeigt die Intraday-Daten des letzten Handelstages (Freitag).")
    
    hist = details["hist_1y"]
    close = hist["Close"]

    # ── Header-Metriken ──────────────────────────────────────────────────
    st.markdown(f"### {stats['name']}  ·  `{display_ticker}`")
    if stats["sector"] != "—":
        st.caption(f"Sektor: {stats['sector']}")

    # ════════════════════════════════════════════════════════════════════
    # Delegierte Section-Renders
    # ════════════════════════════════════════════════════════════════════

    # 1. Übersicht + Finanzdaten (Tabs)
    tab_overview, tab_financials = st.tabs(["Übersicht", "Finanzdaten"])
    with tab_overview:
        render_overview(stats, hist, close, ticker, display_ticker)
    with tab_financials:
        render_financials(details, ticker)

    st.markdown("---")

    # 2. Technische Charts (8 Tabs)
    render_charts(hist, close, selected_hist, ticker, display_ticker, details, stats, time_filter)

    # 3. Strategische Entscheidungen
    st.markdown("---")
    st.markdown("### 🎯 Strategische Entscheidungen")
    st.caption("Automatische Analyse-Signale für drei Handelsansätze — basierend auf den aktuellen Kursdaten.")

    # 4. SMC-Block (Liquidity, SMC Macro, Swing, Order Flow)
    render_smc(hist, close, ticker, display_ticker, details)

    # 5. Bewertung (Quant + Options + DCF + Bilanz + Margen)
    render_valuation(details, hist, ticker, display_ticker, stats)

    # 6. Fundamentaldaten (Peers, Dividende, Insider, Analysten, Earnings)
    render_fundamentals(details, ticker, display_ticker)

    # 7. Zusammenfassung (Scoring, Signale, Position Sizing, News)
    render_summary(stats, hist, close, ticker, display_ticker, details)
