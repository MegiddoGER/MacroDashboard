import streamlit as st
from data_cache import cached_history, cached_yield_spread, cached_inflation, cached_regional_news, _render_news_list
from charts import plot_timeseries, plot_yield_spread, plot_inflation

def page_macro():
    st.markdown("## Weltwirtschaft")
    st.caption("Makroökonomische Indikatoren: Rohstoffe, Zinsen und Inflation")

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
