"""
app.py — Trading Macro Dashboard (Streamlit).

MVCS Entry Point: Config → Style → Controller Routing.

Starte mit:  py launcher.py   (natives Fenster)
         oder:  py -m streamlit run app.py   (Browser)
"""

import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------
# Page-Config (muss der ERSTE Streamlit-Aufruf sein)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Macro Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sprache auf Deutsch setzen & Übersetzungs-Popup deaktivieren
# ---------------------------------------------------------------------------
st.markdown("""
<meta name="google" content="notranslate">
<meta http-equiv="content-language" content="de">
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Custom CSS — Clean Dark Finance Look
# ---------------------------------------------------------------------------
from style_manager import apply_custom_styles
apply_custom_styles()

# ---------------------------------------------------------------------------
# Controller Imports
# ---------------------------------------------------------------------------
from controllers.sidebar import display_sidebar
from controllers.header import display_header, display_market_clocks
from services.cache import _is_market_open

# ---------------------------------------------------------------------------
# Main Routing
# ---------------------------------------------------------------------------
def main():
    refresh_ms = 300000 if _is_market_open() else 1800000
    components.html(
        f"""<script>setTimeout(function(){{
            window.parent.location.reload();
        }}, {refresh_ms})</script>""",
        height=0,
    )

    page = display_sidebar()
    if page == "Startseite":
        display_market_clocks()
        
    # Alerts im Hintergrund abgleichen
    try:
        from services.alerts import check_active_alerts
        new_alerts = check_active_alerts()
        for a in new_alerts:
            st.toast(f"🚨 **ALARM AUSGELÖST:** {a.ticker} ({a.alert_type} = {a.trigger_value:.2f})", icon="🚨")
    except Exception as e:
        print(f"Alert-System Fehler: {e}")

    display_header()
    st.markdown("---")

    if page == "Startseite":
        from controllers.home import run
        run()
    elif page == "Gesamtwirtschaft":
        from controllers.economy import run
        run()
    elif page == "Watchlist":
        from controllers.watchlist_page import run
        run()
    elif page == "Screener":
        from controllers.screener import run
        run()
    elif page == "Analyse":
        from controllers.analysis import run
        run()
    elif page == "Backtesting":
        from controllers.backtesting import run
        run()
    elif page == "Trade-Journal":
        from controllers.journal import run
        run()
    elif page == "Sektoren":
        from controllers.sectors import run
        run()
    elif page == "Analyse-Lexikon":
        from controllers.lexicon import run
        run()
    elif page == "Aktien-Verzeichnis":
        from controllers.directory import run
        run()

if __name__ == "__main__":
    main()
