"""
controllers/sidebar.py — Sidebar-Logik: Navigation und Watchlist-Verwaltung.
"""

import os
import streamlit as st
from services.watchlist import load_watchlist, add_to_watchlist, remove_from_watchlist, resolve_ticker


def display_sidebar() -> str:
    """Rendert die Sidebar und gibt die ausgewählte Seite zurück."""
    with st.sidebar:
        # ── Sektion 1: Branding ──────────────────────────────────────────────
        with st.container():
            st.markdown(
                "<div class='analyzer-logo'>"
                "<span class='logo-icon'>📊</span> Analyzer"
                "<span class='logo-sub'>Macro Dashboard</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown("---")

        # ── Sektion 2: Navigation ────────────────────────────────────────────
        with st.container():
            # Seiten-Synchronisierung mit URL Parametern
            pages = [
                "Startseite",
                "Gesamtwirtschaft",
                "Watchlist",
                "Screener",
                "Analyse",
                "Backtesting",
                "Trade-Journal",
                "Sektoren",
                "Analyse-Lexikon",
                "Aktien-Verzeichnis",
            ]
            
            current_page = st.query_params.get("page", "Startseite")
            try:
                default_idx = pages.index(current_page)
            except ValueError:
                default_idx = 0

            def on_page_change():
                st.query_params["page"] = st.session_state.nav_radio

            page = st.radio(
                "Navigation",
                pages,
                index=default_idx,
                key="nav_radio",
                on_change=on_page_change,
                label_visibility="collapsed",
            )
            st.markdown("---")

        # ── Sektion 3: Watchlist Verwaltung ──────────────────────────────────
        with st.container():
            st.markdown("##### ⚡ Watchlist")

            add_query = st.text_input(
                "Ticker oder Firmenname",
                placeholder="Hier Namen eingeben",
                key="wl_add_input",
            )
            
            # Marker für den Hinzufügen-Button
            st.markdown('<span class="marker-btn-add" style="display:none;"></span>', unsafe_allow_html=True)
            if st.button("➕ Hinzufügen", use_container_width=True, key="wl_add_btn"):
                if add_query.strip():
                    with st.spinner("Suche …"):
                        result = resolve_ticker(add_query)
                    if result:
                        add_to_watchlist(result["ticker"], result["name"],
                                         result.get("display", ""))
                        xetra_hint = " (Xetra)" if result["ticker"].endswith(".DE") else ""
                        st.success(f"✅ {result['name']} ({result.get('display', result['ticker'])}){xetra_hint}")
                        st.rerun()
                    else:
                        st.error(f"❌ '{add_query}' nicht gefunden.")

            wl_items = load_watchlist()
            if wl_items:
                # Gruppierung nach Status
                invested = [i for i in wl_items if i.get("status") == "Investiert"]
                watching = [i for i in wl_items if i.get("status", "Beobachtet") != "Investiert"]

                def _render_wl_group(title, icon, items, accent_color, dot_color):
                    if not items:
                        return
                    st.markdown(
                        f"<div class='wl-group-header'>"
                        f"<span class='wl-group-dot' style='background:{dot_color};'></span>"
                        f"<span class='wl-group-title'>{icon} {title}</span>"
                        f"<span class='wl-group-count'>{len(items)}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    for item in items:
                        display_name = item.get("display", item["ticker"])
                        company = item["name"]
                        # Kürze den Firmennamen für die Sidebar
                        if len(company) > 28:
                            company = company[:26] + "…"

                        col_card, col_x = st.columns([5, 1])
                        with col_card:
                            st.markdown(
                                f"<div class='wl-card'>"
                                f"<span class='wl-card-dot' style='background:{accent_color};'></span>"
                                f"<div class='wl-card-info'>"
                                f"<span class='wl-card-ticker'>{display_name}</span>"
                                f"<span class='wl-card-name'>{company}</span>"
                                f"</div>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        with col_x:
                            st.markdown('<span class="marker-btn-delete" style="display:none;"></span>', unsafe_allow_html=True)
                            if st.button("✕", key=f"del_{item['ticker']}",
                                         help=f"{display_name} entfernen"):
                                remove_from_watchlist(item["ticker"])
                                st.rerun()

                st.markdown("---")
                _render_wl_group("Investiert", "💰", invested, "#00d4aa", "#00d4aa")
                _render_wl_group("Beobachtet", "👁", watching, "#64748b", "#475569")

                if not invested and not watching:
                    st.caption("Noch keine Ticker gespeichert.")
            else:
                st.caption("Noch keine Ticker gespeichert.")

        # ── Sektion 3.5: Signal Alerts ─────────────────────────────────────────
        with st.expander("🔔 Signal-Alerts", expanded=False):
            from models.alerts import AlertStore, AlertConfig
            from services.watchlist import get_ticker_list
            
            # Anzeige ausgelöster Alerts
            unack = AlertStore.get_triggered_unacknowledged()
            if unack:
                for a in unack:
                    st.error(f"🚨 **{a.ticker}**: {a.alert_type} ausgelöst bei {a.trigger_value:.2f}!")
                    if st.button("x Gelesen", key=f"ack_alert_{a.id}"):
                        AlertStore.acknowledge_alert(a.id)
                        st.rerun()
                st.markdown("---")
                
            active_alerts = AlertStore.get_active()
            if active_alerts:
                for a in active_alerts:
                    st.caption(f"{a.ticker} | {a.alert_type} | {a.threshold}")
                    if st.button("Löschen", key=f"del_alert_{a.id}", help="Alert löschen"):
                        AlertStore.delete_alert(a.id)
                        st.rerun()
            else:
                st.caption("Keine aktiven Alarme.")

            st.markdown("**Neuer Alarm**")
            # Minimal UI für neue Alarme
            tk_list = get_ticker_list()
            a_ticker = st.selectbox("Ticker", tk_list if tk_list else ["AAPL"])
            a_type = st.selectbox("Typ", ["price_below", "price_above", "rsi_below", "score_above", "score_below"])
            a_thres = st.number_input("Limit-Wert", format="%.2f", step=1.0)
            
            if st.button("Speichern", key="save_alert_btn"):
                if a_ticker:
                    AlertStore.save(AlertConfig(ticker=a_ticker, alert_type=a_type, threshold=a_thres))
                    st.toast(f"✅ Alarm für {a_ticker} ({a_type}) aktiviert!")
                    st.rerun()

        # ── Sektion 4: Footer / Systemsteuerung ──────────────────────────────
        with st.container():
            st.markdown("---")
            st.caption("Daten via Yahoo Finance · Cache 5 Min")

            # Marker für Refresh Button
            st.markdown('<span class="marker-btn-refresh" style="display:none;"></span>', unsafe_allow_html=True)
            if st.button("Alle Daten Aktualisieren", key="sidebar_refresh", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)
            
            # Marker für Quit Button
            st.markdown('<span class="marker-btn-quit" style="display:none;"></span>', unsafe_allow_html=True)
            if st.button("🔴 System Beenden", key="sidebar_quit", type="primary", use_container_width=True):
                os._exit(0)

    return page
