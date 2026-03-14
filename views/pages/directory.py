import streamlit as st
import pandas as pd
from data_cache import cached_listings

def page_listings():
    st.markdown("## Aktien-Verzeichnis")
    st.caption("Alle handelbaren Aktien — NYSE, NASDAQ, AMEX (Quelle: NASDAQ Screener)")

    with st.spinner("Lade Aktienverzeichnis …"):
        df = cached_listings()

    if df is None or df.empty:
        st.error("Aktienverzeichnis konnte nicht geladen werden.")
        return

    # Filter-Optionen
    col_search, col_filter = st.columns([2, 1])
    with col_search:
        search = st.text_input(
            "🔍 Suche (Kürzel oder Name)",
            placeholder="z.B. AAPL, Microsoft, SAP …",
            key="listing_search",
        )
    with col_filter:
        exchanges = ["Alle"] + sorted(df["Börse"].dropna().unique().tolist())
        selected_exchange = st.selectbox("Börsen-Filter", exchanges, key="listing_idx")

    # Buchstabenfilter
    alphabet = ["Alle"] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    selected_letter = st.radio(
        "Anfangsbuchstabe",
        alphabet,
        horizontal=True,
        key="listing_letter",
        label_visibility="collapsed",
    )

    # Filtern
    filtered = df.copy()
    if selected_exchange != "Alle":
        filtered = filtered[filtered["Börse"] == selected_exchange]

    if search.strip():
        # Textsuche überschreibt Buchstabenfilter
        q = search.strip().upper()
        filtered = filtered[
            filtered["Kürzel"].str.upper().str.contains(q, na=False) |
            filtered["Name"].str.upper().str.contains(q, na=False)
        ]
    elif selected_letter != "Alle":
        filtered = filtered[filtered["Kürzel"].str.startswith(selected_letter, na=False)]

    st.markdown(f"**{len(filtered)}** Aktien gefunden")

    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "Kürzel": st.column_config.TextColumn("Kürzel", width="small"),
            "Name": st.column_config.TextColumn("Unternehmen", width="large"),
            "Börse": st.column_config.TextColumn("Börse", width="medium"),
        },
    )
