"""
controllers/sidebar.py — Sidebar-Logik: Navigation und Watchlist-Verwaltung.
"""

import os
import streamlit as st
from services.watchlist import load_watchlist, add_to_watchlist, remove_from_watchlist, resolve_ticker


def display_sidebar() -> str:
    """Rendert die Sidebar und gibt die ausgewählte Seite zurück."""
    with st.sidebar:
        st.markdown(
            "<div class='analyzer-logo'>"
            "<span class='logo-icon'>📊</span> Analyzer"
            "<span class='logo-sub'>Macro Dashboard</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        # ── Seiten-Synchronisierung mit URL Parametern ──
        pages = [
            "Startseite",
            "Gesamtwirtschaft",
            "Watchlist",
            "Analyse",
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

        # ── Watchlist verwalten ──────────────────────────────────────
        st.markdown("##### ⚡ Watchlist")

        add_query = st.text_input(
            "Ticker oder Firmenname",
            placeholder="Hier Namen eingeben",
            key="wl_add_input",
        )
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
            st.markdown("---")
            for item in wl_items:
                col_name, col_del = st.columns([4, 1])
                display_name = item.get("display", item["ticker"])
                with col_name:
                    st.markdown(f"**{display_name}**"
                                f"<br><span style='color:#64748b;font-size:0.75rem'>"
                                f"{item['name']}</span>",
                                unsafe_allow_html=True)
                with col_del:
                    if st.button("✕", key=f"del_{item['ticker']}",
                                 help=f"{display_name} entfernen"):
                        remove_from_watchlist(item["ticker"])
                        st.rerun()
        else:
            st.caption("Noch keine Ticker gespeichert.")

        st.markdown("---")
        st.caption("Daten via Yahoo Finance · Cache 5 Min")

        if st.button("🔄 Alle Daten Aktualisieren", key="sidebar_refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔴 System Beenden", key="sidebar_quit", type="primary", use_container_width=True):
            os._exit(0)

    return page
