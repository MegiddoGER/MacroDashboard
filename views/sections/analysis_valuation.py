"""Valuation-Section: Sektor-Quant-Analyse, Options Flow, DCF, Bilanz, Margen."""
import streamlit as st
import pandas as pd

from services.fundamental import (
    calc_dcf_valuation, calc_balance_sheet_quality, get_margin_trends
)


def _determine_sector_category(stats: dict, details: dict) -> tuple[str, str]:
    """Bestimmt die Sektor-Kategorie und den Tab-Namen für die Quant-Analyse."""
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
    
    return sector_cat, tab_name


def _render_quant_tab(sector_cat: str, tab_name: str, info_data: dict):
    """Rendert die sektorspezifische Quant-Analyse im Quant-Tab."""
    st.markdown(f"#### {tab_name}")
    
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


def render_valuation(details: dict, hist: pd.DataFrame, ticker: str, 
                     display_ticker: str, stats: dict):
    """Rendert Quant-Tab, Options Flow, DCF, Bilanz und Margen-Trends."""
    info_data = details.get("info", {})
    
    # Sektor bestimmen
    sector_cat, tab_name = _determine_sector_category(stats, details)
    
    # Quant + Options Tab
    tab_quant, tab_options = st.tabs([tab_name, "📋 Options Flow"])

    with tab_quant:
        _render_quant_tab(sector_cat, tab_name, info_data)

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
            st.markdown(f"**Verfallstermin:** `{opts.expiry_date}` "
                        f"({len(opts.available_expiries)} Termine verfügbar)")

            oc1, oc2, oc3, oc4 = st.columns(4)

            with oc1:
                pc_val = f"{opts.pc_ratio_volume:.2f}" if opts.pc_ratio_volume else "—"
                sentiment_icon = {"Bullish": "🟢", "Bearish": "🔴", "Neutral": "🟡"}.get(opts.pc_sentiment, "—")
                st.metric("P/C Ratio (Vol.)", pc_val, delta=f"{sentiment_icon} {opts.pc_sentiment}", delta_color="off",
                          help="Put/Call Volume Ratio. >1.2 = Bearish (mehr Puts), <0.7 = Bullish (mehr Calls).")

            with oc2:
                mp_val = f"{opts.max_pain:,.2f} €" if opts.max_pain else "—"
                mp_delta = f"{opts.max_pain_distance_pct:+.1f} % vom Kurs" if opts.max_pain_distance_pct is not None else ""
                st.metric("Max Pain", mp_val, delta=mp_delta, delta_color="off",
                          help="Preis bei dem die meisten Optionen wertlos verfallen. Kurse tendieren an Verfall dorthin.")

            with oc3:
                iv_val = f"{opts.implied_vol:.1f} %" if opts.implied_vol else "—"
                st.metric("Implied Volatility", iv_val, help="Durchschnittliche ATM Implied Volatility. Misst die erwartete Schwankung.")

            with oc4:
                hv_val = f"{opts.historical_vol:.1f} %" if opts.historical_vol else "—"
                iv_signal = opts.iv_hv_signal or ""
                signal_icon = {"IV Premium": "⬆️", "IV Discount": "⬇️", "Fair": "↔️"}.get(iv_signal, "")
                st.metric("Historical Volatility", hv_val,
                          delta=f"{signal_icon} {iv_signal} (IV/HV: {opts.iv_hv_ratio:.2f})" if opts.iv_hv_ratio else "",
                          delta_color="off",
                          help="30-Tage historische Volatilität (annualisiert). Vergleich mit IV zeigt Über/Unterbewertung der Optionsprämie.")

            if opts.pc_description:
                if opts.pc_sentiment == "Bullish": st.success(f"✅ {opts.pc_description}")
                elif opts.pc_sentiment == "Bearish": st.warning(f"⚠️ {opts.pc_description}")
                else: st.info(f"ℹ️ {opts.pc_description}")

            if opts.iv_hv_signal == "IV Premium":
                st.warning("⚠️ **IV Premium:** Optionsprämien sind überdurchschnittlich hoch — "
                          "der Markt erwartet stärkere Kursbewegungen als historisch üblich. Oft vor Earnings oder Events.")
            elif opts.iv_hv_signal == "IV Discount":
                st.success("✅ **IV Discount:** Optionsprämien sind günstiger als üblich — "
                          "keine außergewöhnliche Volatilitätserwartung eingepreist.")

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
                            f"<b>${s['strike']:,.0f}</b> · OI: {s['open_interest']:,} · "
                            f"Vol: {s['volume']:,} · IV: {s['iv']:.0f}%</div>",
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
                            f"<b>${s['strike']:,.0f}</b> · OI: {s['open_interest']:,} · "
                            f"Vol: {s['volume']:,} · IV: {s['iv']:.0f}%</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("Keine Put-OI-Daten verfügbar.")

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
                        f"({item['vol_oi_ratio']:.0f}x)</div>",
                        unsafe_allow_html=True,
                    )

            st.caption("Put/Call Ratio: <0.7 = bullish, 0.7-1.2 = neutral, >1.2 = bearish. "
                       "Max Pain: Preislevel bei dem am meisten Optionen wertlos verfallen — "
                       "der Kurs tendiert am Verfallstag oft in diese Richtung.")

    # ── DCF ──
    st.markdown("---")
    st.markdown("### 💰 Innerer Wert (DCF-Modell)")
    st.caption("Vereinfachtes Discounted-Cashflow-Modell — schätzt den fairen Wert basierend auf prognostizierten Free Cashflows.")

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

    # ── Bilanzqualität ──
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

    # ── Margen-Trends ──
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

        fcf_data = [{"Jahr": str(m['year']), "FCF": f"{m['fcf']:,.0f} €" if m.get('fcf') else "—"} for m in margins]
        if any(m.get('fcf') for m in margins):
            st.markdown("**Free Cashflow pro Jahr**")
            st.dataframe(pd.DataFrame(fcf_data), use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Nicht genügend Finanzdaten für Margen-Trends verfügbar.")
