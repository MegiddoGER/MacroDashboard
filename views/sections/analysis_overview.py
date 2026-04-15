"""Übersichts-Section: Metriken-Header mit Kurs, SMAs, Fundamentals."""
import streamlit as st
import pandas as pd
import math
from services.technical import calc_atr


def _fmt_price(val, suffix=" €"):
    """Formatiert einen Preis sicher — gibt '—' zurück bei None/NaN."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "—"
    return f"{val:,.2f}{suffix}"


def render_overview(stats: dict, hist: pd.DataFrame, close: pd.Series,
                    ticker: str, display_ticker: str):
    """Rendert die Übersichts-Metriken (Kurs, SMAs, RSI, PE, ATR, Volumen)."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aktueller Kurs", _fmt_price(stats['current_price']))
    c2.metric("52W Hoch", _fmt_price(stats['high_52w']))
    c3.metric("52W Tief", _fmt_price(stats['low_52w']))
    c4.metric(
        "Volatilität (ann.)", 
        f"{stats['volatility']:.1f} %" if stats.get('volatility') and not math.isnan(stats['volatility']) else "—",
        help="Annualisierte historische Volatilität. Misst die durchschnittliche Schwankungsbreite der Aktie über ein Jahr. Höhere Werte bedeuten höheres Risiko/größere Preisschwankungen."
    )

    c5, c6, c7, c8 = st.columns(4)
    c5.metric(
        "RSI (14)", 
        f"{stats['rsi']:.1f}" if stats["rsi"] else "—",
        help="Relative Strength Index (14 Tage). Ein Momentum-Indikator, der die Geschwindigkeit und Veränderung von Kursbewegungen misst. Werte > 70 gelten als überkauft, < 30 als überverkauft."
    )
    c6.metric(
        "SMA 20", 
        f"{stats['sma_20']:,.2f} €" if stats["sma_20"] else "—",
        help="Simple Moving Average (20 Tage). Der einfache gleitende Durchschnitt der letzten 20 Handelstage. Dient zur Identifikation des kurzfristigen Trends."
    )
    c7.metric(
        "SMA 50", 
        f"{stats['sma_50']:,.2f} €" if stats["sma_50"] else "—",
        help="Simple Moving Average (50 Tage). Zeigt den mittelfristigen Trend an."
    )
    c8.metric(
        "SMA 200", 
        f"{stats['sma_200']:,.2f} €" if stats["sma_200"] else "—",
        help="Simple Moving Average (200 Tage). Einer der wichtigsten Indikatoren für den langfristigen Trend. Liegt der Kurs darüber, herrscht ein Aufwärtstrend."
    )

    c9, c10, c11, c12 = st.columns(4)
    c9.metric(
        "KGV (P/E)", 
        f"{stats['pe_ratio']:.1f}" if stats["pe_ratio"] else "—",
        help="Kurs-Gewinn-Verhältnis (Price-to-Earnings). Setzt den Kurs der Aktie in Relation zum Gewinn je Aktie (EPS). Ein niedriges KGV kann auf eine Unterbewertung hinweisen, variiert jedoch stark nach Sektor."
    )
    if stats["dividend_yield"]:
        c10.metric("Dividendenrendite", f"{stats['dividend_yield']*100:.2f} %")
    else:
        c10.metric("Dividendenrendite", "—")
        
    atr = calc_atr(hist["High"], hist["Low"], hist["Close"], 14)
    atr_val = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else None
    c11.metric(
        "ATR (14)", 
        f"{atr_val:.2f} €" if atr_val else "—",
        help="Average True Range (14 Tage). Misst die absolute Volatilität in Euro. Gibt an, um wie viel Euro die Aktie im Durchschnitt pro Tag schwankt. Hilft bei der Festlegung von Stop-Loss-Leveln."
    )
    if stats["avg_volume"]:
        vol = stats["avg_volume"]
        if vol >= 1e9: vol_str = f"{vol:,} Stück (Mrd.)"
        elif vol >= 1e6: vol_str = f"{vol:,} Stück (Mio.)"
        else: vol_str = f"{vol:,} Stück"
        c12.metric("Ø Volumen", vol_str, help="Durchschnittliches tägliches Handelsvolumen.")
    else:
        c12.metric("Ø Volumen", "—")

    if stats["market_cap"]:
        cap = stats["market_cap"]
        if cap >= 1e12: cap_str = f"{cap/1e12:.2f} Bio. €"
        elif cap >= 1e9: cap_str = f"{cap/1e9:.2f} Mrd. €"
        elif cap >= 1e6: cap_str = f"{cap/1e6:.1f} Mio. €"
        else: cap_str = f"{cap:,.0f} €"
        st.caption(f"Marktkapitalisierung: **{cap_str}**")

    earnings_raw = stats.get("earnings_date")
    if earnings_raw:
        try:
            from datetime import datetime
            ed = datetime.fromisoformat(str(earnings_raw).split(" ")[0])
            earnings_str = ed.strftime("%d.%m.%Y")
        except Exception:
            earnings_str = str(earnings_raw)
        st.caption(f"📅 Nächste Quartalszahlen: **{earnings_str}**")
