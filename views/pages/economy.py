import streamlit as st
from data_cache import cached_history, cached_yield_spread, cached_inflation, cached_regional_news, _render_news_list
from charts import plot_timeseries, plot_yield_spread, plot_inflation
from services.cache import cached_upcoming_events, cached_calendar_summary
from services.economic_calendar import (
    get_impact_color, get_country_flag, get_category_icon,
    IMPACT_BADGES, COUNTRY_FLAGS,
)


# ---------------------------------------------------------------------------
# Wirtschaftskalender — Event-Karten
# ---------------------------------------------------------------------------

def _render_event_card(event):
    """Rendert eine einzelne Event-Karte als styled HTML."""
    impact_color = get_impact_color(event.impact)
    flag = get_country_flag(event.country)
    cat_icon = get_category_icon(event.category)
    date_str = event.date.strftime("%a, %d. %b %Y")
    time_str = f" · {event.time_cet} CET" if event.time_cet else ""

    # Countdown-Styling
    if event.is_today:
        countdown_bg = "#dc2626"
        countdown_color = "#fff"
    elif event.days_until <= 1:
        countdown_bg = "#f59e0b"
        countdown_color = "#000"
    elif event.days_until <= 3:
        countdown_bg = "#3b82f6"
        countdown_color = "#fff"
    else:
        countdown_bg = "#334155"
        countdown_color = "#94a3b8"

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-left: 4px solid {impact_color};
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 10px;
    ">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:1.2rem">{flag}</span>
                <span style="font-size:1.2rem">{cat_icon}</span>
                <span style="font-weight:600; font-size:0.95rem; color:#e2e8f0;">{event.name}</span>
            </div>
            <span style="
                background:{countdown_bg};
                color:{countdown_color};
                padding:3px 10px;
                border-radius:12px;
                font-size:0.75rem;
                font-weight:600;
            ">{event.countdown_label}</span>
        </div>
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#64748b; font-size:0.8rem;">
                {date_str}{time_str}
            </span>
            <span style="
                color:{impact_color};
                font-size:0.72rem;
                font-weight:500;
            ">{IMPACT_BADGES.get(event.impact, '')}</span>
        </div>
        <div style="color:#94a3b8; font-size:0.78rem; margin-top:6px; line-height:1.4;">
            {event.description}
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_calendar_section():
    """Rendert die Wirtschaftskalender-Section."""
    st.markdown("### 📅 Wirtschaftskalender")
    st.markdown("<span style='color:#94a3b8;font-size:0.85rem'>"
                "Anstehende Makro-Events mit Impact-Rating. "
                "High-Impact Events (🔴) bewegen Märkte signifikant — "
                "erhöhte Volatilität im Vorfeld einkalkulieren.</span>",
                unsafe_allow_html=True)

    # ── Zusammenfassung ──────────────────────────────────────────────
    summary = cached_calendar_summary()
    if summary:
        cols = st.columns(4)
        with cols[0]:
            st.metric("Events (14 Tage)", summary.get("total", 0))
        with cols[1]:
            st.metric("🔴 High Impact", summary.get("high_count", 0))
        with cols[2]:
            st.metric("🟠 Medium Impact", summary.get("medium_count", 0))
        with cols[3]:
            next_ev = summary.get("next_high_event")
            if next_ev:
                st.metric("Nächstes High-Event",
                          next_ev.countdown_label,
                          delta=next_ev.name,
                          delta_color="off")
            else:
                st.metric("Nächstes High-Event", "—")

    # ── Filter-Tabs ──────────────────────────────────────────────────
    tab_all, tab_us, tab_eu, tab_de = st.tabs([
        "📋 Alle Events",
        "🇺🇸 USA",
        "🇪🇺 Eurozone",
        "🇩🇪 Deutschland",
    ])

    country_filters = [
        (tab_all, "", "📋 Alle Events"),
        (tab_us, "US", "🇺🇸 USA"),
        (tab_eu, "EU", "🇪🇺 Eurozone"),
        (tab_de, "DE", "🇩🇪 Deutschland"),
    ]

    for tab, country_code, label in country_filters:
        with tab:
            events = cached_upcoming_events(days=14, country=country_code)
            if events:
                # High-Impact zuerst, dann Medium
                high_events = [e for e in events if e.impact == "high"]
                medium_events = [e for e in events if e.impact == "medium"]
                low_events = [e for e in events if e.impact == "low"]

                if high_events:
                    for event in high_events:
                        _render_event_card(event)

                if medium_events:
                    with st.expander(
                            f"🟠 Medium Impact ({len(medium_events)} Events)",
                            expanded=False):
                        for event in medium_events:
                            _render_event_card(event)

                if low_events:
                    with st.expander(
                            f"🟢 Low Impact ({len(low_events)} Events)",
                            expanded=False):
                        for event in low_events:
                            _render_event_card(event)
            else:
                st.info(f"Keine Events in den nächsten 14 Tagen.")


# ---------------------------------------------------------------------------
# Hauptseite
# ---------------------------------------------------------------------------

def page_macro():
    st.markdown("## Weltwirtschaft")
    st.caption("Makroökonomische Indikatoren: Wirtschaftskalender, Rohstoffe, Zinsen und Inflation")

    # ── Wirtschaftskalender ───────────────────────────────────────────────
    _render_calendar_section()

    st.markdown("---")

    # ── Rohstoffe ─────────────────────────────────────────────────────────
    st.markdown("### 🌍 Rohstoffmärkte")
    st.markdown("<span style='color:#94a3b8;font-size:0.85rem'>"
                "Rohstoffpreise sind ein Frühindikator für Inflation und wirtschaftliche Aktivität. "
                "Steigende Preise deuten auf höhere Nachfrage oder Angebotsengpässe hin.</span>",
                unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        gold = cached_history("GC=F", "5y")
        if gold is not None:
            st.plotly_chart(
                plot_timeseries(gold, "🥇 Gold (GC=F) — Sicherer Hafen & Inflationsschutz",
                                color="#f59e0b"),
                use_container_width=True, config={"scrollZoom": True, "displayModeBar": True},
            )
        else:
            st.warning("Gold-Daten nicht verfügbar.")

    with col2:
        oil = cached_history("CL=F", "5y")
        if oil is not None:
            st.plotly_chart(
                plot_timeseries(oil, "🛢️ Rohöl (CL=F) — Energiekosten & Wirtschaftsbarometer",
                                color="#3b82f6"),
                use_container_width=True, config={"scrollZoom": True, "displayModeBar": True},
            )
        else:
            st.warning("Rohöl-Daten nicht verfügbar.")

    st.markdown("---")

    # ── Zinsstrukturkurve ─────────────────────────────────────────────
    st.markdown("### 📊 Zinsstrukturkurve (Yield Spread)")
    st.markdown("<span style='color:#94a3b8;font-size:0.85rem'>"
                "<b>Was ist der Yield Spread?</b><br>"
                "Der Yield Spread (Zinsstrukturkurve) misst die Zinsdifferenz zwischen langfristigen (z.B. 10-jährigen) und kurzfristigen (z.B. 2-jährigen) Staatsanleihen. "
                "Normalerweise erhalten Anleger für eine längere Bindung ihres Kapitals höhere Zinsen (positiver Spread).<br><br>"
                "<b>Was bedeutet eine Inversion?</b><br>"
                "Fällt der Spread unter 0 % (<i>inverse Zinsstruktur</i>), werfen kurzfristige Anlagen höhere Zinsen ab als langfristige. "
                "Das passiert, wenn Marktteilnehmer kurzfristig hohe Risiken oder Zinserhöhungen der Zentralbanken erwarten, langfristig aber von Zinssenkungen aufgrund einer abkühlenden Wirtschaft ausgehen. "
                "Ein negativer Spread (Inversion) gilt an der Wall Street als der <b>zuverlässigste Frühindikator für eine Rezession</b>.<br><br>"
                "<b>Was ist eine Rezession?</b><br>"
                "Eine Rezession ist ein deutlicher, breit angelegter Rückgang der wirtschaftlichen Aktivität, üblicherweise definiert durch ein schrumpfendes Bruttoinlandsprodukt (BIP) über mindestens zwei aufeinanderfolgende Quartale. "
                "Dies führt oft zu steigender Arbeitslosigkeit, sinkenden Unternehmensgewinnen und starken Korrekturen an den Aktienmärkten.</span>",
                unsafe_allow_html=True)

    spread = cached_yield_spread()
    if spread is not None:
        st.plotly_chart(plot_yield_spread(spread), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        latest = spread["Spread"].iloc[-1]
        status = "🟢 Normal — Wirtschaft stabil" if latest > 0 else "🔴 Invertiert — Rezessionswarnung"
        c1, c2, c3 = st.columns(3)
        c1.metric("Aktueller Spread", f"{latest:.2f} %")
        c2.metric("10J-Rendite", f"{spread['10Y'].iloc[-1]:.2f} %")
        c3.metric("Status", status)
    else:
        st.warning("Yield-Daten nicht verfügbar.")

    st.markdown("---")

    # ── Inflation ────────────────────────────────────────────────────
    st.markdown("### 📈 Inflationsrate Deutschland")
    st.markdown("<span style='color:#94a3b8;font-size:0.85rem'>"
                "Die jährliche Preissteigerung (CPI). Das EZB-Ziel liegt bei 2%. "
                "Hohe Inflation erhöht Zinserwartungen und belastet Aktienbewertungen, "
                "niedrige Inflation kann auf schwache Nachfrage hindeuten.</span>",
                unsafe_allow_html=True)

    inflation = cached_inflation()
    if inflation is not None and not inflation.empty:
        st.plotly_chart(plot_inflation(inflation), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        latest_infl = inflation["Inflation %"].iloc[-1]
        c1, c2 = st.columns(2)
        c1.metric("Aktuelle Rate", f"{latest_infl:.1f} %")
        c2.metric("EZB-Ziel", "2.0 %",
                  delta=f"{latest_infl - 2.0:+.1f} pp Abweichung")
    else:
        st.info("Inflationsdaten nicht verfügbar (Quelle: FRED).")

    st.markdown("---")

    # ── Nachrichten ──────────────────────────────────────────────────
    st.markdown("### 📰 Nachrichten")
    st.markdown("<span style='color:#94a3b8;font-size:0.85rem'>"
                "Aktuelle Schlagzeilen aus Wirtschaft und Politik — "
                "kuratiert von seriösen Nachrichtenagenturen und Leitmedien.</span>",
                unsafe_allow_html=True)

    news_tab_eu, news_tab_us, news_tab_asia = st.tabs([
        "🇪🇺 Europa", "🇺🇸 USA", "🇨🇳 Asien"
    ])

    with news_tab_eu:
        with st.spinner("Lade Nachrichten …"):
            eu_news = cached_regional_news("europa")
        if eu_news:
            _render_news_list(eu_news)
            st.caption("Quellen: Tagesschau, Handelsblatt")
        else:
            st.info("Keine europäischen Nachrichten verfügbar.")

    with news_tab_us:
        with st.spinner("Lade Nachrichten …"):
            us_news = cached_regional_news("usa")
        if us_news:
            _render_news_list(us_news)
            st.caption("Quellen: CNBC")
        else:
            st.info("Keine US-Nachrichten verfügbar.")

    with news_tab_asia:
        with st.spinner("Lade Nachrichten …"):
            asia_news = cached_regional_news("asien")
        if asia_news:
            _render_news_list(asia_news)
            st.caption("Quellen: Nikkei Asia, CNBC Asia")
        else:
            st.info("Keine asiatischen Nachrichten verfügbar.")
