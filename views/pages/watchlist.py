import streamlit as st
import pandas as pd
from datetime import datetime, date
from data_cache import cached_multi, cached_earnings, _fmt_euro, _fmt_pct, _fmt_rsi, _color_change
from watchlist import (
    load_watchlist, get_display_map, update_status,
    add_position, close_position, update_position, delete_position,
    get_open_positions, get_closed_positions,
    calc_position_pnl, calc_portfolio_summary,
)

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

    # ── Portfolio-Übersicht (nur wenn Positionen vorhanden) ─────────
    open_pos = get_open_positions()
    closed_pos = get_closed_positions()

    if open_pos or closed_pos:
        st.markdown("---")
        st.markdown("#### 💼 Portfolio-Übersicht")

        # Aktuelle Kurse für offene Positionen holen
        if open_pos:
            open_tickers = list(set(op["ticker"] for op in open_pos))
            tickers_str_open = ", ".join(open_tickers)
            with st.spinner("Lade aktuelle Kurse …"):
                price_df = cached_multi(tickers_str_open)
            current_prices = {}
            if price_df is not None and not price_df.empty and "Ticker" in price_df.columns:
                for _, row in price_df.iterrows():
                    t = row["Ticker"]
                    current_prices[t] = row.get("Kurs (€)", 0)
        else:
            current_prices = {}

        summary = calc_portfolio_summary(current_prices)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Investiert", f"{summary['total_invested']:,.2f} €")
        with col2:
            st.metric("Aktueller Wert", f"{summary['total_value']:,.2f} €")
        with col3:
            pnl_color = "🟢" if summary["unrealized_pnl"] >= 0 else "🔴"
            st.metric("Unrealisiert",
                       f"{summary['unrealized_pnl']:+,.2f} €",
                       f"{summary['total_pnl_pct']:+.1f}%")
        with col4:
            st.metric("Realisiert", f"{summary['realized_pnl']:+,.2f} €",
                       f"{summary['open_positions_count']} offen / {summary['closed_positions_count']} geschlossen")

    # ── Aktive Positionen Tabelle ─────────────────────────────────
    if open_pos:
        st.markdown("---")
        st.markdown("#### 📊 Aktive Positionen")

        pos_rows = []
        for op in open_pos:
            pos = op["position"]
            price = current_prices.get(op["ticker"])
            pnl = calc_position_pnl(pos, price)
            pos_rows.append({
                "Ticker": display_map.get(op["ticker"], op["ticker"]),
                "Kaufdatum": pos.get("buy_date", "—"),
                "Kaufkurs": pos.get("buy_price", 0),
                "Stück": pos.get("quantity", 0),
                "Aktuell": price if price else 0,
                "P&L €": pnl["pnl_eur"],
                "P&L %": pnl["pnl_pct"],
                "SL": pos.get("stop_loss") or "—",
                "TP": pos.get("take_profit") or "—",
            })

        pos_df = pd.DataFrame(pos_rows)
        st.dataframe(
            pos_df.style.format({
                "Kaufkurs": "{:,.2f} €",
                "Stück": "{:,.2f}",
                "Aktuell": "{:,.2f} €",
                "P&L €": "{:+,.2f} €",
                "P&L %": "{:+.1f}%",
            }).map(lambda v: "color: #00d4aa" if isinstance(v, (int, float)) and v > 0
                   else ("color: #ff6b6b" if isinstance(v, (int, float)) and v < 0 else ""),
                   subset=["P&L €", "P&L %"]),
            use_container_width=True,
            hide_index=True,
        )

    # ── Position kaufen ───────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ➕ Position kaufen")

    buy_options_map = {}
    for item in wl_items:
        disp = item.get("display", item["ticker"])
        label = f"{disp}  ·  {item['name']}"
        buy_options_map[label] = item

    buy_selection = st.selectbox(
        "Aktie für Kauf auswählen",
        list(buy_options_map.keys()),
        key="pos_buy_select",
    )

    if buy_selection:
        buy_item = buy_options_map[buy_selection]

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            buy_price = st.number_input("Kaufkurs (€)", min_value=0.01,
                                         value=100.0, step=0.01, key="pos_buy_price")
        with col_b:
            buy_qty = st.number_input("Stückzahl", min_value=0.0001,
                                      value=1.0, step=1.0, key="pos_buy_qty")
        with col_c:
            buy_date = st.date_input("Kaufdatum", value=date.today(),
                                      key="pos_buy_date")

        col_d, col_e, col_f = st.columns(3)
        with col_d:
            buy_sl = st.number_input("Stop-Loss (€, optional)", min_value=0.0,
                                      value=0.0, step=0.01, key="pos_buy_sl")
        with col_e:
            buy_tp = st.number_input("Take-Profit (€, optional)", min_value=0.0,
                                      value=0.0, step=0.01, key="pos_buy_tp")
        with col_f:
            buy_fees = st.number_input("Gebühren (€)", min_value=0.0,
                                        value=0.0, step=0.01, key="pos_buy_fees")

        buy_notes = st.text_input("Notizen (optional)", key="pos_buy_notes",
                                   placeholder="z.B. RSI überverkauft, FVG Entry")

        invest_total = buy_price * buy_qty + buy_fees
        st.caption(f"💰 Investitionssumme: **{invest_total:,.2f} €** ({buy_qty:,.2f} × {buy_price:,.2f} € + {buy_fees:.2f} € Gebühren)")

        if st.button("🛒 Position eröffnen", key="pos_buy_btn", use_container_width=True):
            result = add_position(
                ticker=buy_item["ticker"],
                buy_price=buy_price,
                quantity=buy_qty,
                buy_date=buy_date.strftime("%Y-%m-%d"),
                stop_loss=buy_sl if buy_sl > 0 else None,
                take_profit=buy_tp if buy_tp > 0 else None,
                fees=buy_fees,
                notes=buy_notes,
            )
            if result:
                st.success(f"✅ Position eröffnet: {buy_qty:,.2f}x {buy_item.get('display', buy_item['ticker'])} @ {buy_price:,.2f} €")
                st.rerun()
            else:
                st.error("❌ Position konnte nicht erstellt werden.")

    # ── Position schließen (Verkauf) ──────────────────────────────
    if open_pos:
        st.markdown("---")
        st.markdown("#### 💰 Position schließen (Verkauf)")

        sell_options = {}
        for op in open_pos:
            pos = op["position"]
            disp = display_map.get(op["ticker"], op["ticker"])
            label = f"{disp} — {pos['quantity']}x @ {pos['buy_price']:.2f} € ({pos['buy_date']})"
            sell_options[label] = (op["ticker"], pos)

        sell_selection = st.selectbox(
            "Position zum Verkauf auswählen",
            list(sell_options.keys()),
            key="pos_sell_select",
        )

        if sell_selection:
            sell_ticker, sell_pos = sell_options[sell_selection]
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                sell_price = st.number_input("Verkaufskurs (€)", min_value=0.01,
                                              value=float(sell_pos.get("buy_price", 100)),
                                              step=0.01, key="pos_sell_price")
            with col_s2:
                sell_date = st.date_input("Verkaufsdatum", value=date.today(),
                                           key="pos_sell_date")
            with col_s3:
                sell_fees = st.number_input("Verkaufsgebühren (€)", min_value=0.0,
                                             value=0.0, step=0.01, key="pos_sell_fees")

            pnl_preview = calc_position_pnl(sell_pos, sell_price)
            pnl_symbol = "🟢" if pnl_preview["pnl_eur"] >= 0 else "🔴"
            st.caption(f"{pnl_symbol} Voraussichtlicher P&L: **{pnl_preview['pnl_eur']:+,.2f} €** ({pnl_preview['pnl_pct']:+.1f}%)")

            if st.button("📤 Position schließen", key="pos_sell_btn", use_container_width=True):
                result = close_position(
                    ticker=sell_ticker,
                    position_id=sell_pos["id"],
                    sell_price=sell_price,
                    sell_date=sell_date.strftime("%Y-%m-%d"),
                    sell_fees=sell_fees,
                )
                if result:
                    st.success(f"✅ Position geschlossen @ {sell_price:,.2f} €")
                    st.rerun()

    # ── Status-Verwaltung ──────────────────────────────────────
    st.markdown("---")
    with st.expander("⚙️ Status manuell verwalten"):
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
