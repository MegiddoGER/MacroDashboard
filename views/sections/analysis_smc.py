"""SMC-Section: Liquidity Sweeps, SMC Multi-Timeframe, Swing Trading, Order Flow."""
import streamlit as st
import pandas as pd

from services.technical import detect_liquidity_sweeps, calc_swing_signals, calc_order_flow
from views.components.charts import plot_liquidity_sweeps, plot_swing_overview, plot_order_flow


def render_smc(hist: pd.DataFrame, close: pd.Series,
               ticker: str, display_ticker: str, details: dict):
    """Rendert die Liquidity Sweep, SMC, Swing und Order Flow Tabs."""

    # SMC-Macro Tab braucht HTF-Daten
    from smc.indicators import analyze_smc
    from smc.charts import plot_smc

    tab_liq, tab_smc, tab_swing, tab_flow = st.tabs([
        "🔄 Liquidity Sweep", "🧲 SMC (Makro)", "📈 Swing Trading", "📊 Order Flow"
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
                st.warning(f"⚠️ Letzter Sweep: **Bearish** am {latest['sweep_date'].strftime('%d.%m.%Y') if hasattr(latest['sweep_date'], 'strftime') else latest['sweep_date']} bei **{latest['level']:,.2f} €** — Liquidität wurde nach oben abgegriffen.")
            st.caption("Liquidity Sweeps zeigen, wo Market Maker Stop-Losses ausgelöst haben. Bullish = Preis wurde kurz unter ein Tief gedrückt und hat sich erholt.")
        else:
            st.info("Keine Liquidity Sweeps im aktuellen Zeitraum erkannt.")

    with tab_smc:
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
