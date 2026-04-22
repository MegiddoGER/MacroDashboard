"""Fundamentals-Section: Peer-Vergleich, Dividende, Insider, Analysten-Konsens, Earnings History."""
import streamlit as st
import pandas as pd
from datetime import datetime

from services.fundamental import (
    get_sector_peers, calc_dividend_analysis, get_insider_institutional,
    get_analyst_consensus
)


def render_fundamentals(details: dict, ticker: str, display_ticker: str):
    """Rendert Peer-Vergleich, Dividende, Insider, Analysten und Earnings-History."""
    info_data = details.get("info", {})

    # ── Peer-Vergleich ──
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

    # ── Dividendenanalyse ──
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

    # ── Insider & Institutionelle ──
    st.markdown("---")
    st.markdown("### 👔 Insider & Institutionelle Investoren")

    with st.spinner("Lade Insider-Daten …"):
        insider = get_insider_institutional(ticker)

    if insider:
        tab_insider, tab_inst = st.tabs(["🔑 Insider-Transaktionen", "🏛️ Top Institutionelle"])

        with tab_insider:
            # ── Aggregierte Statistik (letzte 6 Monate) ──
            if insider['has_summary']:
                st.caption("📊 Aggregierte Insider-Aktivität der letzten 6 Monate (SEC-Meldungen)")
                ic1, ic2, ic3, ic4 = st.columns(4)
                ic1.metric("Käufe (Transaktionen)", insider['purchases_count'])
                ic2.metric("Verkäufe (Transaktionen)", insider['sales_count'])

                # Net Shares mit Delta-Farbcodierung
                net_s = insider['net_shares']
                if net_s > 0:
                    ic3.metric("Netto-Aktien", f"{net_s:,}".replace(",", "."),
                               delta=f"+{net_s:,}".replace(",", "."), delta_color="normal")
                elif net_s < 0:
                    ic3.metric("Netto-Aktien", f"{net_s:,}".replace(",", "."),
                               delta=f"{net_s:,}".replace(",", "."), delta_color="inverse")
                else:
                    ic3.metric("Netto-Aktien", "0")

                if insider['insider_pct']:
                    ic4.metric("Insider-Anteil", f"{insider['insider_pct']:.2f} %",
                               help="Prozent aller ausstehenden Aktien im Besitz von Insidern.")
                else:
                    ic4.metric("Insider-Anteil", "—")

                # Signal-Interpretation
                if insider['purchases_count'] > insider['sales_count'] and net_s > 0:
                    st.success("✅ **Netto-Käufe:** Insider kaufen mehr als sie verkaufen — bullisches Vertrauenssignal.")
                elif insider['sales_count'] > insider['purchases_count'] and net_s < 0:
                    st.warning("⚠️ **Netto-Verkäufe:** Insider verkaufen mehr. "
                               "Kann verschiedene Gründe haben (Steuerplanung, Diversifikation, Vesting-Verkäufe).")
                else:
                    st.info("ℹ️ **Ausgeglichen:** Keine eindeutige Tendenz bei den Insider-Transaktionen.")
            else:
                if insider['insider_pct']:
                    st.metric("Insider-Anteil", f"{insider['insider_pct']:.2f} %")
                st.info("ℹ️ Keine aggregierten Insider-Statistiken verfügbar (nur für US-Aktien via SEC-Filings).")

            # ── Detail-Tabelle der letzten Transaktionen ──
            if insider['has_insider_data']:
                with st.expander("📋 Letzte Insider-Transaktionen (Detail)", expanded=False):
                    st.dataframe(insider['insider_df'], use_container_width=True, hide_index=True)
            else:
                st.caption("Keine Detail-Transaktionen verfügbar.")

        with tab_inst:
            if insider['has_institutional_data']:
                if insider['institutional_pct']:
                    st.metric("Institutioneller Anteil", f"{insider['institutional_pct']:.1f} %",
                              help="Prozent aller ausstehenden Aktien im Besitz institutioneller Investoren (Fonds, ETFs, etc.).")
                st.dataframe(insider['institutional_df'], use_container_width=True, hide_index=True)
            else:
                st.info("ℹ️ Keine institutionellen Daten verfügbar.")
    else:
        st.info("ℹ️ Insider- und institutionelle Daten konnten nicht geladen werden.")

    # ── Analysten-Konsens ──
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

    # ── Earnings Surprise History ──
    st.markdown("---")
    st.markdown("### 📊 Earnings Surprise History")
    st.caption("Historische EPS-Überraschungen und Post-Earnings-Drift — zeigt, wie der Markt auf Quartalsergebnisse reagiert hat.")

    with st.spinner("Lade Earnings-Daten …"):
        from services.earnings import get_earnings_history
        earnings_profile = get_earnings_history(ticker)

    if earnings_profile and earnings_profile.events:
        ep = earnings_profile

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

        ec1, ec2, ec3, ec4, ec5 = st.columns(5)
        ec1.metric("Quarters", f"{ep.total_quarters}")
        ec2.metric("Beats 🟢", f"{ep.beats}", delta=f"{ep.beat_rate:.0f}%", delta_color="off")
        ec3.metric("Misses 🔴", f"{ep.misses}")
        ec4.metric("Ø Surprise", f"{ep.avg_surprise_pct:+.1f}%")
        ec5.metric("Ø Drift (1T)", f"{ep.avg_drift_1d:+.2f}%" if ep.avg_drift_1d is not None else "—")

        tab_eps_chart, tab_drift, tab_history = st.tabs([
            "📊 EPS Chart", "📈 Post-Earnings Drift", "📋 Historie"
        ])

        with tab_eps_chart:
            import plotly.graph_objects as go
            chart_events = sorted(ep.events, key=lambda e: e.date)[-12:]
            quarters = [e.quarter for e in chart_events]
            actuals = [e.eps_actual for e in chart_events]
            estimates = [e.eps_estimate for e in chart_events]

            fig_eps = go.Figure()
            fig_eps.add_trace(go.Bar(
                x=quarters, y=estimates, name="EPS Estimate",
                marker_color="rgba(100, 200, 255, 0.4)",
                marker_line_color="#64C8FF", marker_line_width=1,
            ))

            bar_colors = []
            for e in chart_events:
                if e.result == "Beat": bar_colors.append("#22c55e")
                elif e.result == "Miss": bar_colors.append("#ef4444")
                else: bar_colors.append("#eab308")

            fig_eps.add_trace(go.Bar(
                x=quarters, y=actuals, name="EPS Actual",
                marker_color=bar_colors, marker_line_width=0,
            ))

            fig_eps.update_layout(
                template="plotly_dark", height=380, barmode="group",
                yaxis_title="EPS ($)", xaxis_title="Quartal",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=50, r=20, t=30, b=50), xaxis_tickangle=-45,
            )
            st.plotly_chart(fig_eps, use_container_width=True, config={"displayModeBar": False})

            if ep.beat_rate >= 75:
                st.success(f"✅ **Starker Earnings-Track-Record:** {ep.beat_rate:.0f}% der Quartale geschlagen (Beat-Rate).")
            elif ep.beat_rate >= 50:
                st.info(f"ℹ️ **Solider Track-Record:** {ep.beat_rate:.0f}% Beat-Rate über {ep.total_quarters} Quartale.")
            else:
                st.warning(f"⚠️ **Schwacher Track-Record:** Nur {ep.beat_rate:.0f}% Beat-Rate — häufig unter den Erwartungen.")

        with tab_drift:
            st.markdown("##### Kursreaktion nach Earnings-Veröffentlichung")
            st.caption("Zeigt, wie sich der Kurs 1, 5 und 20 Handelstage nach der Earnings-Veröffentlichung entwickelt hat.")

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

            drift_events = sorted(
                [e for e in ep.events if e.drift_1d is not None],
                key=lambda e: e.date
            )[-12:]

            if drift_events:
                import plotly.graph_objects as go
                fig_drift = go.Figure()
                d_quarters = [e.quarter for e in drift_events]

                for days_label, get_val, color in [
                    ("1 Tag", lambda e: e.drift_1d, "#64C8FF"),
                    ("5 Tage", lambda e: e.drift_5d, "#a855f7"),
                    ("20 Tage", lambda e: e.drift_20d, "#f97316"),
                ]:
                    vals = [get_val(e) for e in drift_events]
                    fig_drift.add_trace(go.Scatter(
                        x=d_quarters, y=vals, name=days_label,
                        mode="lines+markers", line=dict(color=color, width=2), marker=dict(size=8),
                    ))

                fig_drift.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
                fig_drift.update_layout(
                    template="plotly_dark", height=350,
                    yaxis_title="Kursänderung (%)", xaxis_title="Quartal",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    margin=dict(l=50, r=20, t=30, b=50), xaxis_tickangle=-45,
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
                df_earnings, use_container_width=True, hide_index=True,
                height=min(400, 35 * len(history_rows) + 38),
            )

        st.caption("⚠️ Post-Earnings Drift basiert auf historischen Schlusskursen. Die tatsächliche Kursreaktion am Earnings-Tag kann durch After-Hours-Handel abweichen.")
    else:
        st.info("ℹ️ Keine Earnings-Daten für dieses Unternehmen verfügbar (nur bei US-Aktien mit ausreichender Historie).")
