"""
views/pages/screener.py — Screener-Seite (UI).

Scannt S&P 500 Aktien, filtert nach Kriterien und zeigt Ergebnisse
als interaktive Tabelle an.
"""

import streamlit as st
import pandas as pd
from services.screener import PRESETS, scan_sp500


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _score_emoji(confidence: float) -> str:
    """Gibt passendes Emoji für einen Confidence-Score zurück."""
    if confidence >= 75:
        return "🟢"
    elif confidence >= 60:
        return "↗️"
    elif confidence >= 45:
        return "➖"
    elif confidence >= 30:
        return "↘️"
    else:
        return "🔴"


def _signal_type(confidence: float) -> str:
    """Leitet Signal-Typ aus Confidence ab."""
    if confidence >= 65:
        return "Buy"
    elif confidence <= 35:
        return "Sell"
    return "Hold"


def _format_rsi(val) -> str:
    """Formatiert RSI-Wert mit Farbhinweis."""
    if val is None or pd.isna(val):
        return "—"
    v = float(val)
    if v > 70:
        return f"🔴 {v:.1f}"
    elif v < 30:
        return f"🟢 {v:.1f}"
    return f"{v:.1f}"


def _color_confidence(val):
    """Stylt Confidence-Zelle."""
    try:
        v = float(val)
        if v >= 70:
            return "color: #00d4aa; font-weight: bold"
        elif v >= 55:
            return "color: #64C8FF"
        elif v >= 40:
            return "color: #a0a0a0"
        elif v >= 25:
            return "color: #FFB347"
        else:
            return "color: #ff6b6b; font-weight: bold"
    except (ValueError, TypeError):
        return ""


# ---------------------------------------------------------------------------
# Hauptseite
# ---------------------------------------------------------------------------

def page_screener():
    """Rendert die Screener-Seite."""
    st.markdown("## 🔍 Aktien-Screener")
    st.caption(
        "Scannt alle S&P 500 Aktien und bewertet sie nach technischen Kriterien. "
        "Der Quick-Score nutzt Trend-, Volumen- und Oszillator-Indikatoren."
    )

    # ── Preset-Auswahl ────────────────────────────────────────────
    st.markdown("#### 📋 Screener-Typ auswählen")

    preset_options = {
        key: f"{cfg['name']}" for key, cfg in PRESETS.items()
    }

    col_preset, col_desc = st.columns([1, 2])
    with col_preset:
        selected_preset = st.radio(
            "Preset",
            list(preset_options.keys()),
            format_func=lambda k: preset_options[k],
            key="screener_preset",
            label_visibility="collapsed",
        )
    with col_desc:
        preset_info = PRESETS[selected_preset]
        st.info(f"**{preset_info['name']}**\n\n{preset_info['description']}")

        # Zusätzliche Filter
        with st.expander("⚙️ Erweiterte Filter", expanded=False):
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                custom_score_min = st.slider(
                    "Min. Score", 0, 100, 0,
                    key="screener_score_min",
                    help="Nur Aktien mit Score ≥ diesem Wert anzeigen"
                )
            with col_f2:
                custom_rsi_range = st.slider(
                    "RSI Bereich", 0, 100, (0, 100),
                    key="screener_rsi_range",
                    help="RSI-Filter: Nur Aktien im gewählten Bereich"
                )
            with col_f3:
                # Sektor-Filter
                sectors = [
                    "", "Information Technology", "Health Care", "Financials",
                    "Consumer Discretionary", "Communication Services",
                    "Industrials", "Consumer Staples", "Energy",
                    "Utilities", "Real Estate", "Materials",
                ]
                sector_filter = st.selectbox(
                    "Sektor", sectors,
                    format_func=lambda s: "Alle Sektoren" if not s else s,
                    key="screener_sector",
                )

    # ── Scan starten ──────────────────────────────────────────────
    st.markdown("---")

    # Cache-Key für Ergebnisse
    cache_key = f"screener_results_{selected_preset}"

    col_scan, col_clear = st.columns([3, 1])
    with col_scan:
        scan_clicked = st.button(
            "🚀 Scan starten",
            use_container_width=True,
            key="screener_scan_btn",
            type="primary",
        )
    with col_clear:
        if st.button("🗑️ Cache leeren", use_container_width=True,
                      key="screener_clear_btn"):
            for key in list(st.session_state.keys()):
                if key.startswith("screener_results_"):
                    del st.session_state[key]
            st.rerun()

    # ── Scan ausführen ────────────────────────────────────────────
    if scan_clicked:
        progress_bar = st.progress(0, text="Starte Scan...")
        status_text = st.empty()

        def update_progress(progress: float, status: str):
            progress_bar.progress(min(progress, 1.0), text=status)

        with st.spinner("Scanne S&P 500..."):
            # Custom-Filter zusammenbauen
            custom_filters = {}
            if custom_score_min > 0:
                custom_filters["score_min"] = custom_score_min
            if custom_rsi_range != (0, 100):
                custom_filters["rsi_min"] = custom_rsi_range[0]
                custom_filters["rsi_max"] = custom_rsi_range[1]
            if sector_filter:
                custom_filters["sector"] = sector_filter

            results = scan_sp500(
                preset=selected_preset,
                custom_filters=custom_filters if custom_filters else None,
                progress_callback=update_progress,
            )

        progress_bar.empty()
        st.session_state[cache_key] = results

    # ── Ergebnisse anzeigen ───────────────────────────────────────
    results = st.session_state.get(cache_key)

    if results is None:
        st.info("👆 Wähle einen Screener-Typ und klicke **Scan starten**.")
        return

    if not results:
        st.warning("Keine Aktien gefunden, die den Filterkriterien entsprechen.")
        return

    # Statistik-Header
    st.markdown(f"### 📊 Ergebnisse ({len(results)} Aktien)")

    # Schnell-Statistik
    scores = [r["confidence"] for r in results]
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        st.metric("Gefunden", f"{len(results)}")
    with col_s2:
        st.metric("Ø Score", f"{sum(scores) / len(scores):.1f}")
    with col_s3:
        buy_count = sum(1 for s in scores if s >= 65)
        st.metric("Buy-Signale", f"{buy_count}")
    with col_s4:
        sell_count = sum(1 for s in scores if s <= 35)
        st.metric("Sell-Signale", f"{sell_count}")

    st.markdown("---")

    # Ergebnis-Tabelle
    rows = []
    for r in results:
        rows.append({
            "": _score_emoji(r["confidence"]),
            "Ticker": r["ticker"],
            "Name": r["name"],
            "Sektor": r["sector"],
            "Score": r["confidence"],
            "Signal": _signal_type(r["confidence"]),
            "RSI": round(r["rsi"], 1) if r["rsi"] else None,
            "Kurs ($)": r["price"],
            "Trend ▲": "✅" if r["trend_bullish"] else "❌",
            "MACD ▲": "✅" if r["macd_bullish"] else "❌",
            "OBV ▲": "✅" if r["obv_bullish"] else "❌",
        })

    df = pd.DataFrame(rows)

    # Stil anwenden
    styled = df.style.map(
        _color_confidence, subset=["Score"]
    ).format({
        "Score": "{:.1f}",
        "Kurs ($)": "${:,.2f}",
        "RSI": lambda v: _format_rsi(v),
    })

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "": st.column_config.TextColumn("", width="small"),
            "Ticker": st.column_config.TextColumn("Ticker", width="small"),
            "Name": st.column_config.TextColumn("Unternehmen", width="medium"),
            "Sektor": st.column_config.TextColumn("Sektor", width="medium"),
            "Score": st.column_config.NumberColumn("Score", width="small"),
            "Signal": st.column_config.TextColumn("Signal", width="small"),
            "RSI": st.column_config.TextColumn("RSI", width="small"),
            "Kurs ($)": st.column_config.TextColumn("Kurs", width="small"),
            "Trend ▲": st.column_config.TextColumn("Trend", width="small"),
            "MACD ▲": st.column_config.TextColumn("MACD", width="small"),
            "OBV ▲": st.column_config.TextColumn("OBV", width="small"),
        },
    )

    # ── Top/Flop Highlight ────────────────────────────────────────
    if len(results) >= 10:
        st.markdown("---")
        col_top, col_flop = st.columns(2)

        with col_top:
            st.markdown("#### 🏆 Top 5 (höchster Score)")
            for i, r in enumerate(results[:5], 1):
                emoji = _score_emoji(r["confidence"])
                st.markdown(
                    f"**{i}. {emoji} {r['ticker']}** — {r['name']}\n\n"
                    f"Score: **{r['confidence']:.1f}** | "
                    f"RSI: {r['rsi']:.1f if r['rsi'] else '—'} | "
                    f"${r['price']:,.2f}"
                )

        with col_flop:
            st.markdown("#### 📉 Bottom 5 (niedrigster Score)")
            bottom = results[-5:]
            bottom.reverse()
            for i, r in enumerate(bottom, 1):
                emoji = _score_emoji(r["confidence"])
                st.markdown(
                    f"**{i}. {emoji} {r['ticker']}** — {r['name']}\n\n"
                    f"Score: **{r['confidence']:.1f}** | "
                    f"RSI: {r['rsi']:.1f if r['rsi'] else '—'} | "
                    f"${r['price']:,.2f}"
                )

    # Footer
    st.markdown("---")
    st.caption(
        "💡 **Tipp:** Für eine vollständige Analyse mit Fundamentaldaten, "
        "SMC-Signalen und Handlungsempfehlung → wechsle zur **Analyse-Seite** "
        "und gib den gewünschten Ticker ein."
    )
    st.caption(
        "⚠️ Quick-Score basiert nur auf technischen Indikatoren (Trend, "
        "Volumen, Oszillatoren). Fundamentaldaten werden nicht berücksichtigt. "
        "Ergebnisse sind keine Anlageberatung."
    )
