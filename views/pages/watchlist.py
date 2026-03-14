import streamlit as st
import pandas as pd
from data_cache import cached_multi, cached_earnings, _fmt_euro, _fmt_pct, _fmt_rsi, _color_change
from watchlist import load_watchlist, get_display_map, update_status

def page_watchlist():
    st.markdown("## Watchlist")
    wl_items = load_watchlist()
    if not wl_items:
        st.info("👈 Füge Ticker über die Sidebar hinzu.")
        return

    display_map = get_display_map()

    # ── Daten-Tabellen nach Status ───────────────────────────────────
    invested = [i for i in wl_items if i.get("status") == "Investiert"]
    watching = [i for i in wl_items if i.get("status", "Beobachtet") == "Beobachtet"]

    filter_choice = st.radio(
        "Anzeigen", ["Alle", "Investiert", "Beobachtet"],
        horizontal=True, label_visibility="collapsed",
    )

    def _render_group(title, items, color):
        if not items:
            return
        tickers = [i["ticker"] for i in items]
        display_names = [display_map.get(t, t) for t in tickers]
        st.markdown(f"### <span style='color:{color}'>●</span> {title} "
                    f"({len(items)})", unsafe_allow_html=True)
        st.caption(f"{', '.join(display_names)}")

        tickers_str = ", ".join(tickers)
        with st.spinner("Lade Marktdaten …"):
            df = cached_multi(tickers_str)
        if df is not None and not df.empty and "Ticker" in df.columns:
            df["Ticker"] = df["Ticker"].map(lambda t: display_map.get(t, t))
        if df is not None and not df.empty:
            st.dataframe(
                df.style.format({
                    "Kurs (€)": _fmt_euro,
                    "Veränderung %": _fmt_pct,
                    "RSI (14)": _fmt_rsi,
                }).map(_color_change, subset=["Veränderung %"]),
                use_container_width=True,
                hide_index=True,
            )

    if filter_choice in ("Alle", "Investiert"):
        _render_group("💰 Investiert", invested, "#00d4aa")
    if filter_choice in ("Alle", "Beobachtet"):
        _render_group("👁 Beobachtet", watching, "#64748b")

    if not invested and not watching:
        st.info("Keine Einträge gefunden.")
        return

    # ── Status-Verwaltung ──────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Status verwalten")

    status_options_map = {}
    for item in wl_items:
        disp = item.get("display", item["ticker"])
        label = f"{disp}  ·  {item['name']}"
        status_options_map[label] = item

    selected_label = st.selectbox(
        "Aktie auswählen",
        list(status_options_map.keys()),
        key="status_manage_select",
    )

    if selected_label:
        selected_item = status_options_map[selected_label]
        current = selected_item.get("status", "Beobachtet")
        options = ["Beobachtet", "Investiert"]
        idx = options.index(current) if current in options else 0
        new_status = st.selectbox(
            "Status",
            options,
            index=idx,
            key="status_manage_value",
        )
        if new_status != current:
            update_status(selected_item["ticker"], new_status)
            st.rerun()

    # ── Quartalstermine ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📅 Nächste Quartalszahlen")
    st.caption("Earnings-Termine aller Watchlist-Aktien — sortiert nach Datum.")

    all_tickers = [i["ticker"] for i in wl_items]
    name_map = {i["ticker"]: i.get("name", i["ticker"]) for i in wl_items}
    tickers_str = ",".join(all_tickers)
    names_str = ",".join(f"{t}={n}" for t, n in name_map.items())

    with st.spinner("Lade Quartalstermine …"):
        earn_df = cached_earnings(tickers_str, names_str)

    if earn_df is not None and not earn_df.empty:
        earn_df["Ticker"] = earn_df["Ticker"].map(lambda t: display_map.get(t, t))
        earn_df["Quartalszahlen"] = earn_df["Quartalszahlen"].apply(
            lambda d: d.strftime("%d.%m.%Y") if d is not None and hasattr(d, 'strftime') else "—"
        )
        st.dataframe(
            earn_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                "Name": st.column_config.TextColumn("Unternehmen", width="large"),
                "Quartalszahlen": st.column_config.TextColumn("📅 Nächste Quartalszahlen", width="medium"),
            },
        )
        st.caption(
            "⚠️ Termine sind geschätzte Daten von Yahoo Finance und können "
            "von anderen Quellen (z.\u202fB. finanzen.net) leicht abweichen."
        )
    else:
        st.info("Keine Earnings-Termine verfügbar.")
