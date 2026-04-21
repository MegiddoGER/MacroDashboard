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
            # ── Kategorisierte Navigation mit Klapp-Animation ──
            _NAV_CATEGORIES = [
                {
                    "id": "dashboard", "icon": "🏠", "label": "Dashboard",
                    "pages": ["Startseite", "Gesamtwirtschaft"],
                },
                {
                    "id": "tools", "icon": "🔬", "label": "Tools",
                    "pages": ["Analyse", "Screener", "Backtesting"],
                },
                {
                    "id": "portfolio", "icon": "📂", "label": "Portfolio",
                    "pages": ["Watchlist", "Trade-Journal"],
                },
                {
                    "id": "resources", "icon": "📚", "label": "Ressourcen",
                    "pages": ["Sektoren", "Analyse-Lexikon", "Aktien-Verzeichnis"],
                },
            ]

            # Session-State: Welche Kategorien sind aufgeklappt?
            if "nav_expanded" not in st.session_state:
                # Beim Start: Kategorie der aktuellen Seite aufklappen
                st.session_state.nav_expanded = set()
                cur = st.query_params.get("page", "Startseite")
                for cat in _NAV_CATEGORIES:
                    if cur in cat["pages"]:
                        st.session_state.nav_expanded.add(cat["id"])
                        break
                else:
                    st.session_state.nav_expanded.add("dashboard")

            current_page = st.query_params.get("page", "Startseite")
            # Sicherstellen, dass die aktive Seite gültig ist
            all_pages = [p for cat in _NAV_CATEGORIES for p in cat["pages"]]
            if current_page not in all_pages:
                current_page = "Startseite"

            # ── CSS: Navigation Styling ──
            st.markdown("""
            <style>
            /* ── Sidebar Nav Buttons: Base Style (secondary = nicht aktiv) ── */
            div[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
                background: transparent !important;
                border: 1px solid rgba(148, 163, 184, 0.08) !important;
                box-shadow: none !important;
                color: #94a3b8 !important;
                font-size: 0.84rem !important;
                font-weight: 400 !important;
                padding: 8px 12px 8px 36px !important;
                text-align: left !important;
                width: 100% !important;
                border-radius: 6px !important;
                transition: all 0.15s ease !important;
                min-height: unset !important;
                cursor: pointer !important;
            }
            div[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
                background: rgba(148, 163, 184, 0.08) !important;
                color: #e2e8f0 !important;
                border-color: rgba(148, 163, 184, 0.15) !important;
            }
            div[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:focus {
                box-shadow: none !important;
                outline: none !important;
            }
            div[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] p {
                margin: 0 !important;
                padding: 0 !important;
            }

            /* ── Active Page: primary type = grüne Akzentlinie ── */
            section[data-testid="stSidebar"] [data-testid="stBaseButton-primaryFormSubmit"],
            section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
            section[data-testid="stSidebar"] button[kind="primary"],
            section[data-testid="stSidebar"] button[kind="primaryFormSubmit"],
            div[data-testid="stSidebar"] div[data-testid="stBaseButton-primary"] button,
            div[data-testid="stSidebar"] div[data-testid="stBaseButton-primaryFormSubmit"] button {
                background: linear-gradient(90deg, rgba(0, 212, 170, 0.15) 0%, transparent 100%) !important;
                background-color: transparent !important;
                color: #00d4aa !important;
                font-weight: 500 !important;
                font-size: 0.84rem !important;
                border: none !important;
                border-left: 3px solid #00d4aa !important;
                padding: 8px 12px 8px 33px !important;
                text-align: left !important;
                width: 100% !important;
                border-radius: 6px !important;
                box-shadow: none !important;
                min-height: unset !important;
                cursor: pointer !important;
            }
            section[data-testid="stSidebar"] [data-testid="stBaseButton-primaryFormSubmit"]:hover,
            section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover,
            div[data-testid="stSidebar"] div[data-testid="stBaseButton-primary"] button:hover,
            div[data-testid="stSidebar"] div[data-testid="stBaseButton-primaryFormSubmit"] button:hover {
                background: linear-gradient(90deg, rgba(0, 212, 170, 0.22) 0%, transparent 100%) !important;
                background-color: transparent !important;
                color: #00ffcc !important;
                border-color: #00d4aa !important;
            }
            section[data-testid="stSidebar"] [data-testid="stBaseButton-primaryFormSubmit"] p,
            section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p,
            div[data-testid="stSidebar"] div[data-testid="stBaseButton-primary"] button p,
            div[data-testid="stSidebar"] div[data-testid="stBaseButton-primaryFormSubmit"] button p {
                margin: 0 !important;
                padding: 0 !important;
                color: #00d4aa !important;
            }
            </style>
            """, unsafe_allow_html=True)

            # ── Render ──
            page = current_page

            for cat in _NAV_CATEGORIES:
                cat_id = cat["id"]
                is_expanded = cat_id in st.session_state.nav_expanded
                has_active = current_page in cat["pages"]

                # Aktive Kategorie immer aufklappen
                if has_active and not is_expanded:
                    st.session_state.nav_expanded.add(cat_id)
                    is_expanded = True

                # Chevron-Symbol
                chevron = "▾" if is_expanded else "▸"

                # Kategorie-Header als Button
                if st.button(
                    f"{cat['icon']}  {cat['label']}   {chevron}",
                    key=f"nav_cat_{cat_id}",
                    use_container_width=True,
                ):
                    if cat_id in st.session_state.nav_expanded:
                        st.session_state.nav_expanded.discard(cat_id)
                    else:
                        st.session_state.nav_expanded.add(cat_id)
                    st.rerun()

                # Seiten-Buttons (nur wenn aufgeklappt)
                if is_expanded:
                    for pg in cat["pages"]:
                        is_active = (pg == current_page)
                        btn_type = "primary" if is_active else "secondary"
                        if st.button(
                            f"    {pg}",
                            key=f"nav_page_{pg}",
                            use_container_width=True,
                            type=btn_type,
                        ):
                            st.query_params["page"] = pg
                            page = pg
                            st.rerun()

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
