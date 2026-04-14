"""Charts-Section: 8 Tabs (Candlestick, RSI, MACD, Bollinger, Stochastic, Returns, 5Y, Korrelation)."""
import streamlit as st
import pandas as pd
import numpy as np

from services.watchlist import resolve_ticker
from services.cache import cached_correlation
from services.technical import calc_macd, calc_bollinger, calc_stochastic
from views.components.charts import (
    plot_candlestick, plot_rsi, plot_macd, plot_bollinger, plot_stochastic,
    plot_returns_distribution, plot_timeseries, plot_correlation_matrix
)


def render_charts(hist: pd.DataFrame, close: pd.Series, selected_hist: pd.DataFrame,
                  ticker: str, display_ticker: str, details: dict, stats: dict,
                  time_filter: str):
    """Rendert die 8 technischen Chart-Tabs."""
    tab_chart, tab_rsi, tab_macd, tab_boll, tab_stoch, tab_returns, tab_5y, tab_corr = st.tabs([
        "📊 Kurs & SMAs", "📉 RSI", "📀 MACD", "🌐 Bollinger",
        "📈 Stochastic", "🎲 Renditen", "🗓️ 5 Jahre", "🔗 Korrelation"
    ])

    with tab_chart:
        st.plotly_chart(
            plot_candlestick(
                selected_hist, f"{ticker} — Candlestick ({time_filter})",
                sma_20=details["sma_20"],
                sma_50=details["sma_50"],
                sma_200=details["sma_200"],
            ),
            use_container_width=True, config={"scrollZoom": True, "displayModeBar": True},
        )
        st.caption("SMA 20 (gelb) = kurzfristig · SMA 50 (blau) = mittelfristig · SMA 200 (violett) = langfristig")

    with tab_rsi:
        rsi_series = details["rsi_series"]
        if rsi_series is not None:
            st.plotly_chart(plot_rsi(rsi_series, f"RSI (14) — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
            rsi_val = stats["rsi"]
            if rsi_val:
                if rsi_val > 70: st.warning(f"RSI bei **{rsi_val:.1f}** → Überkauft — möglicher Rücksetzer")
                elif rsi_val < 30: st.success(f"RSI bei **{rsi_val:.1f}** → Überverkauft — mögliche Erholung")
                else: st.info(f"RSI bei **{rsi_val:.1f}** → Neutraler Bereich")
            st.caption("RSI > 70 = überkauft (Verkaufssignal) · RSI < 30 = überverkauft (Kaufsignal)")

    with tab_macd:
        macd_line, signal_line, histogram = calc_macd(close)
        st.plotly_chart(plot_macd(macd_line, signal_line, histogram, f"MACD — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        last_macd = float(macd_line.dropna().iloc[-1]) if not macd_line.dropna().empty else 0
        last_signal = float(signal_line.dropna().iloc[-1]) if not signal_line.dropna().empty else 0
        if last_macd > last_signal: st.success("✅ MACD über Signal-Linie → Bullishes Momentum")
        else: st.warning("⚠️ MACD unter Signal-Linie → Bearishes Momentum")
        st.caption("MACD = Differenz zweier EMAs. Kreuzt die MACD-Linie die Signal-Linie von unten → Kaufsignal.")

    with tab_boll:
        upper, middle, lower = calc_bollinger(close)
        st.plotly_chart(plot_bollinger(close, upper, middle, lower, f"Bollinger Bänder — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        last_close = float(close.iloc[-1])
        last_upper = float(upper.dropna().iloc[-1]) if not upper.dropna().empty else 0
        last_lower = float(lower.dropna().iloc[-1]) if not lower.dropna().empty else 0
        if last_close >= last_upper: st.warning("Kurs am oberen Band → möglicherweise überkauft")
        elif last_close <= last_lower: st.success("Kurs am unteren Band → möglicherweise überverkauft")
        else: st.info("Kurs innerhalb der Bänder → normale Volatilität")
        st.caption("Bollinger Bänder = SMA 20 ± 2 Standardabweichungen. Berührung am Band signalisiert Extrembereiche.")

    with tab_stoch:
        k_line, d_line = calc_stochastic(hist["High"], hist["Low"], hist["Close"])
        st.plotly_chart(plot_stochastic(k_line, d_line, f"Stochastic Oscillator — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        last_k = float(k_line.dropna().iloc[-1]) if not k_line.dropna().empty else 50
        if last_k > 80: st.warning(f"%K bei **{last_k:.0f}** → Überkauft-Zone")
        elif last_k < 20: st.success(f"%K bei **{last_k:.0f}** → Überverkauft-Zone")
        else: st.info(f"%K bei **{last_k:.0f}** → Neutraler Bereich")
        st.caption("%K > 80 = überkauft · %K < 20 = überverkauft. Kreuzung von %K und %D gibt Handelssignale.")

    with tab_returns:
        if details["returns"] is not None and not details["returns"].empty:
            rets = details["returns"]
            st.plotly_chart(plot_returns_distribution(rets, f"Tägliche Renditen — {ticker}"), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric("Ø Tagesrendite", f"{rets.mean()*100:.3f} %")
            rc2.metric("Max Gewinn", f"{rets.max()*100:+.2f} %")
            rc3.metric("Max Verlust", f"{rets.min()*100:+.2f} %")
            rc4.metric("Sharpe (ann.)", f"{(rets.mean()/rets.std()*np.sqrt(252)):.2f}" if rets.std() > 0 else "—")
            st.caption("Sharpe Ratio = risikobereinigte Rendite. > 1 = gut, > 2 = sehr gut, < 0 = negativ.")

    with tab_5y:
        hist_5y = details["hist_5y"]
        if hist_5y is not None and not hist_5y.empty:
            st.plotly_chart(plot_timeseries(hist_5y, f"{ticker} — 5-Jahres-Übersicht", color="#a855f7", height=400), use_container_width=True, config={"scrollZoom": True, "displayModeBar": True})
        else:
            st.info("5-Jahres-Daten nicht verfügbar.")

    with tab_corr:
        st.markdown("##### Korrelation mit anderen Assets")
        st.caption("Wie stark bewegt sich diese Aktie im Gleichschritt mit anderen Assets? Werte nahe +1 = starker Gleichlauf, nahe -1 = gegenläufig, nahe 0 = unabhängig.")

        st.markdown("**Vergleichsaktie hinzufügen**")
        corr_col_input, corr_col_period = st.columns([3, 1])

        with corr_col_input:
            corr_extra = st.text_input("Ticker oder Firmenname", placeholder="z.B. MSFT, BMW, Tesla …", key="corr_extra_ticker").strip()

        with corr_col_period:
            corr_period = st.selectbox(
                "Zeitraum", ["3mo", "6mo", "1y", "2y"],
                index=2, key="corr_period",
                format_func=lambda x: {"3mo": "3 Monate", "6mo": "6 Monate", "1y": "1 Jahr", "2y": "2 Jahre"}[x],
            )

        corr_tickers = [ticker]
        corr_labels = [display_ticker]

        if corr_extra:
            resolved_extra = resolve_ticker(corr_extra)
            if resolved_extra:
                extra_t = resolved_extra["ticker"]
                extra_l = resolved_extra.get("display", extra_t)
            else:
                extra_t = corr_extra.upper()
                extra_l = extra_t
            if extra_t != ticker:
                corr_tickers.append(extra_t)
                corr_labels.append(extra_l)

        st.markdown("**Benchmarks einbeziehen**")
        bench_col1, bench_col2, bench_col3, bench_col4 = st.columns(4)
        benchmarks = {}
        with bench_col1:
            if st.checkbox("S&P 500", value=True, key="corr_sp500"): benchmarks["^GSPC"] = "S&P 500"
        with bench_col2:
            if st.checkbox("DAX", value=True, key="corr_dax"): benchmarks["^GDAXI"] = "DAX"
        with bench_col3:
            if st.checkbox("Gold", value=True, key="corr_gold"): benchmarks["GC=F"] = "Gold"
        with bench_col4:
            if st.checkbox("Bitcoin", value=False, key="corr_btc"): benchmarks["BTC-USD"] = "Bitcoin"

        for bt, bl in benchmarks.items():
            if bt not in corr_tickers:
                corr_tickers.append(bt)
                corr_labels.append(bl)

        if len(corr_tickers) < 2:
            st.info("Füge mindestens eine Vergleichsaktie hinzu oder aktiviere Benchmarks.")
        else:
            tickers_str = ",".join(corr_tickers)
            labels_str = ",".join(corr_labels)
            with st.spinner("Berechne Korrelationen …"):
                corr_df = cached_correlation(tickers_str, labels_str, corr_period)

            if corr_df is not None:
                st.plotly_chart(plot_correlation_matrix(corr_df, f"Korrelationsmatrix — {display_ticker} ({corr_period})"), use_container_width=True)
            else:
                st.warning("Korrelationsdaten nicht verfügbar (zu wenig Datenpunkte).")
