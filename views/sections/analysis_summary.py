"""Summary-Section: Gesamtbewertung, Signal-Historie, Position Sizing, News."""
import streamlit as st
import pandas as pd
from datetime import datetime

from services.technical import calc_technical_summary, calc_atr, calc_position_sizing
from services.cache import cached_company_news
from views.components.news_list import _render_news_list


def render_summary(stats: dict, hist: pd.DataFrame, close: pd.Series,
                   ticker: str, display_ticker: str, details: dict):
    """Rendert die Zusammenfassung mit Scoring, Signal-Historie, Position Sizing und News."""
    st.markdown("---")
    st.markdown("### 📝 Zusammenfassung")
    st.caption("Gewichtete Momentaufnahme — Trend (30%), Volumen (25%), Fundamentaldaten (30%), Oszillatoren (15%).")

    with st.spinner("Erstelle Zusammenfassung …"):
        sum_data = calc_technical_summary(stats, hist, info=details.get("info", {}), ticker=ticker)

    confidence = sum_data.get('confidence', 50)
    score_label = sum_data['score_label']
    confidence_label = sum_data.get('confidence_label', '')

    col_conf, col_text = st.columns([1, 3])
    with col_conf:
        if confidence >= 60:
            conf_color = "#22c55e"
        elif confidence >= 45:
            conf_color = "#eab308"
        else:
            conf_color = "#ef4444"
        st.markdown(f"<div style='text-align:center;'><span style='font-size:3rem;font-weight:bold;color:{conf_color};'>{confidence:.0f}</span><br><span style='color:#aaa;font-size:0.85rem;'>/ 100 Confidence</span></div>", unsafe_allow_html=True)

    with col_text:
        st.markdown(f"#### Momentaufnahme: **{score_label}**")
        st.caption(f"{confidence_label} — Gewichtete Auswertung aus Trend, Volumen, Fundamentaldaten und Oszillatoren.")

    # ── Explizite Kaufempfehlung (kompakt) ──
    if confidence >= 70:
        st.success(f"🟢 **KAUFEN** | {confidence:.0f}/100 — Technisch & fundamental intakt, R:R positiv.")
    elif confidence >= 55:
        st.warning(f"🟡 **HALTEN** | {confidence:.0f}/100 — Gemischte Signale, auf Bestätigung warten.")
    elif confidence >= 40:
        st.info(f"➖ **NEUTRAL** | {confidence:.0f}/100 — Kein klares Setup, abseits bleiben.")
    else:
        st.error(f"🔴 **NICHT KAUFEN** | {confidence:.0f}/100 — Technisch/fundamental kritisch.")

    # Kategorie-Breakdown
    cat_scores = sum_data.get('cat_scores', {})
    cat_max = sum_data.get('cat_max', {})
    weights = sum_data.get('weights', {})
    cat_labels = {"trend": "📊 Trend (30%)", "volume": "📈 Volumen (25%)", 
                  "fundamental": "🏦 Fund. (20%)", "sentiment": "📰 NLP (15%)", 
                  "oscillator": "⚡ Osz. (10%)"}
    
    cols = st.columns(5)
    for col_ui, (cat, label) in zip(cols, cat_labels.items()):
        mx = cat_max.get(cat, 1) or 1
        val = cat_scores.get(cat, 0)
        pct = round((val / mx + 1) / 2 * 100)
        pct = max(0, min(100, pct))
        col_ui.metric(label, f"{pct}%", delta=f"{val:+}/{mx}", delta_color="off")

    # ── Synthese (strukturierte Bullet-Liste statt 3 Info-Boxen) ──
    st.markdown("##### 📌 Synthese")
    st.markdown(
        f"- 📊 **Trend:** {sum_data['macro']}\n"
        f"- ⚡ **Momentum:** {sum_data['micro']}\n"
        f"- 💡 **Handlung:** {sum_data['actionable']}"
    )

    # ── Indikatoren-Checkliste (nach Kategorie gruppiert) ──
    st.markdown("##### 🔍 Indikatoren-Checkliste")
    if sum_data["checklist"]:
        # Kategorie-Zuordnung der Indikatoren
        _CATEGORY_MAP = {
            "ADX": "Technisch", "Trend (SMAs)": "Technisch", "MACD": "Technisch",
            "RSI (14)": "Technisch", "Bollinger Bänder": "Technisch",
            "OBV Trend": "Volumen & Struktur", "VWAP (Wochen/Monats)": "Volumen & Struktur",
            "Volumen-Cluster (POC)": "Volumen & Struktur",
            "FVG (Fair Value Gap)": "Volumen & Struktur",
            "Equal Highs (EQH)": "Volumen & Struktur", "Equal Lows (EQL)": "Volumen & Struktur",
            "DCF Fair Value": "Fundamental", "Bilanzqualität": "Fundamental",
            "Insider-Sentiment": "Fundamental", "Analysten-Konsens": "Fundamental",
            "Dividende": "Fundamental",
            "News Sentiment": "Sentiment",
        }
        _CAT_ORDER = ["Technisch", "Volumen & Struktur", "Fundamental", "Sentiment"]
        _CAT_ICONS = {
            "Technisch": "🔬", "Volumen & Struktur": "📊",
            "Fundamental": "🏦", "Sentiment": "📰",
        }

        # Gruppieren
        grouped = {}
        uncategorized = []
        for item in sum_data["checklist"]:
            cat = _CATEGORY_MAP.get(item.get("Indikator", ""), None)
            if cat:
                grouped.setdefault(cat, []).append(item)
            else:
                uncategorized.append(item)

        for cat in _CAT_ORDER:
            items = grouped.get(cat, [])
            if not items:
                continue
            icon = _CAT_ICONS.get(cat, "")
            st.markdown(f"**{icon} {cat}**")
            df_cat = pd.DataFrame(items)
            # Spalten sauber anordnen
            display_cols = [c for c in ["Indikator", "Wert", "Signal", "Beitrag"] if c in df_cat.columns]
            st.dataframe(
                df_cat[display_cols], use_container_width=True, hide_index=True,
                height=min(250, 35 * len(items) + 38),
            )

        if uncategorized:
            st.markdown("**Sonstige**")
            st.dataframe(pd.DataFrame(uncategorized), use_container_width=True, hide_index=True)

    # ── Historische Signale ──
    from models.signal import SignalStore
    from services.signal_history import update_stale_signals
    
    try:
        update_stale_signals()
    except Exception:
        pass
        
    hist_signals = SignalStore.get_all(ticker=ticker, limit=5)
    if hist_signals:
        st.markdown("##### 📡 Signal-Historie (Letzte 5)")
        st.caption("Das Dashboard speichert automatisch Bewertungssignale, um die eigene Trefferquote zu messen.")
        
        hist_rows = []
        for s in hist_signals:
            try:
                date_str = datetime.fromisoformat(s.timestamp).strftime("%d.%m.%Y %H:%M")
            except:
                date_str = s.timestamp
                
            outcome = "⏳ Ausstehend"
            if s.was_successful is True:
                outcome = "✅ Gewonnen"
            elif s.was_successful is False:
                outcome = "❌ Verloren"
                
            hist_rows.append({
                "Datum": date_str,
                "Signal": "KAUFEN 🟢" if s.signal_type == "buy" else ("VERKAUFEN 🔴" if s.signal_type == "sell" else "NEUTRAL 🟡"),
                "Score": f"{s.confidence:.0f}",
                "Kurs (damals)": f"{s.price_at_signal:,.2f} €",
                "Ergebnis (1M)": outcome,
            })
            
        st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)

    # ── Position Sizing ──
    st.markdown("---")
    st.markdown("### 📐 Position Sizing (Kelly + ATR)")
    st.caption("Bestimmt, wie viele Aktien du kaufen solltest — basierend auf deinem Gesamtkapital, dem aktuellen Kurs (= Entry) und der Volatilität (ATR).")

    atr_series = calc_atr(hist["High"], hist["Low"], hist["Close"], 14)
    atr_current = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else None

    if atr_current:
        ps_col1, ps_col2 = st.columns([1, 1])
        with ps_col1:
            portfolio_val = st.number_input(
                "💰 Portfoliowert (€)", min_value=100, max_value=100_000_000,
                value=10000, step=1000, key="portfolio_value_input"
            )
        with ps_col2:
            max_risk = st.slider(
                "⚠️ Max. Verlust pro Trade (% vom Portfolio)",
                min_value=0.5, max_value=5.0,
                value=2.0, step=0.5, key="max_risk_slider",
                help="Wie viel % deines Gesamtportfolios du maximal bei EINEM Trade verlieren willst, wenn der Stop-Loss greift. Beispiel: 2% von 10.000€ = max. 200€ Verlust."
            )

        ps = calc_position_sizing(
            current_price=stats['current_price'],
            atr_val=atr_current,
            portfolio_value=portfolio_val,
            max_risk_pct=max_risk / 100
        )
        if ps:
            ps0, ps1, ps2, ps3 = st.columns(4)
            ps0.metric("Entry (Aktueller Kurs)", f"{stats['current_price']:,.2f} €")
            ps1.metric("Empfohlene Stückzahl", f"{ps['shares']} Stück")
            ps2.metric("Positionswert", f"{ps['position_value']:,.2f} €", delta=f"{ps['position_pct']:.1f}% des Portfolios", delta_color="off")
            ps3.metric("Max. Verlust bei Stop", f"{ps['risk_eur']:,.2f} €", delta=f"{max_risk:.1f}% vom Portfolio", delta_color="off")

            ps5, ps6, ps7, ps8 = st.columns(4)
            ps5.metric("Stop-Loss", f"{ps['stop_loss']:,.2f} €", delta=f"-{ps['stop_distance']:,.2f} (1.5× ATR)", delta_color="off")
            ps6.metric("Take-Profit", f"{ps['take_profit']:,.2f} €", delta=f"+{2.5 * atr_current:,.2f} (2.5× ATR)", delta_color="off")
            ps7.metric("Kelly-Anteil", f"{ps['kelly_fraction_pct']:.1f}%", help="Kelly Criterion: Mathematisch optimaler Portfolioanteil für maximales Compounding.")
            ps8.metric("Kelly-Stückzahl", f"{ps['kelly_shares']} Stück", help="Optimale Stückzahl nach Kelly-Formel (gekappt bei 25% des Portfolios).")

            st.markdown("""<div style='background:rgba(59,130,246,0.08);border-left:3px solid #3b82f6;padding:10px 14px;border-radius:6px;margin-top:8px;font-size:0.88rem;'>
<b>So liest du das:</b><br>
• <b>Entry</b> = Aktueller Kurs der Aktie (dein Einstiegspunkt)<br>
• <b>Stop-Loss</b> = 1,5× ATR unter dem Entry — wird der Kurs bis hierhin fallen, verkaufst du automatisch, um deinen Verlust zu begrenzen<br>
• <b>Take-Profit</b> = 2,5× ATR über dem Entry — hier nimmst du Gewinn mit (R:R ≈ 1:1,67)<br>
• <b>Max. Verlust bei Stop</b> = Der Euro-Betrag, den du bei <i>diesem</i> Trade maximal verlierst (gesteuert durch den Slider)<br>
• <b>Kelly-Anteil</b> = Die mathematisch optimale Positionsgröße für maximalen Vermögenszuwachs (Compounding). Wird bei 25% gekappt, um Überexposition zu vermeiden.
</div>""", unsafe_allow_html=True)
    else:
        st.info("Nicht genügend Daten für die Position-Sizing-Berechnung (ATR nicht verfügbar).")

    st.caption("⚠️ **Hinweis:** Dies ist eine algorithmische Momentaufnahme basierend auf technischen Indikatoren und fundamentalen Kennzahlen. Sie dient als Entscheidungshilfe, nicht als Anlageberatung.")

    # ── News ──
    st.markdown("---")
    st.markdown(f"### 📰 Nachrichten zu {stats['name']}")
    with st.spinner("Lade Nachrichten …"):
        company_news = cached_company_news(ticker)
    if company_news:
        _render_news_list(company_news)
        st.caption("Quelle: Yahoo Finance (Reuters, Bloomberg, etc.)")
    else:
        st.info(f"Keine Nachrichten für {display_ticker} verfügbar.")
