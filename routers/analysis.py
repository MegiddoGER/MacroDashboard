"""
routers/analysis.py â€” Analyse-Seite (Herzstueck des Dashboards).

GET  /analysis            â†’ Ticker-Eingabe
POST /analysis/load       â†’ Laedt vollstaendige Analyse als HTMX-Partial
"""

import json
import math
import traceback
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse

from services.cache_core import (
    cached_stock_details, cached_company_news,
    cached_options_overview, cached_events_for_ticker,
    cached_correlation,
)
from services.watchlist import load_watchlist, resolve_ticker
from services.technical import (
    calc_macd, calc_bollinger, calc_stochastic,
    calc_technical_summary, calc_atr, calc_position_sizing,
    detect_liquidity_sweeps, calc_swing_signals, calc_order_flow,
)
from services.fundamental import (
    calc_dcf_valuation, calc_balance_sheet_quality, get_margin_trends,
    get_sector_peers, calc_dividend_analysis, get_insider_institutional,
    get_analyst_consensus,
)
from services.scoring import calc_quick_score

router = APIRouter(tags=["pages"])


def _get_header_metrics():
    from main import get_header_metrics
    return get_header_metrics()


def _fig_to_json(fig) -> str:
    """Serialisiert eine Plotly Figure zu JSON fuer clientseitiges Rendering."""
    if fig is None:
        return "null"
    return fig.to_json()


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return default


def _fmt_price(val, suffix=" EUR"):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "â€”"
    return f"{val:,.2f}{suffix}"


def _fmt_big(val):
    if val is None:
        return "â€”"
    abs_val = abs(val)
    if abs_val >= 1e12:
        return f"{val/1e12:.2f} Bio. EUR"
    if abs_val >= 1e9:
        return f"{val/1e9:.2f} Mrd. EUR"
    if abs_val >= 1e6:
        return f"{val/1e6:.2f} Mio. EUR"
    return f"{val:,.0f} EUR"


# ---------------------------------------------------------------------------
# Page: Analyse (Ticker-Eingabe)
# ---------------------------------------------------------------------------

@router.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request):
    templates = request.app.state.templates
    wl_items = load_watchlist()
    ctx = {
        "current_path": "/analysis",
        "header_metrics": _get_header_metrics(),
        "watchlist_items": wl_items,
    }
    return templates.TemplateResponse(
        request=request,
        name="pages/analysis.html",
        context=ctx,
    )


# ---------------------------------------------------------------------------
# HTMX Partial: Vollstaendige Analyse laden
# ---------------------------------------------------------------------------

@router.post("/analysis/load", response_class=HTMLResponse)
async def analysis_load(
    request: Request,
    ticker_input: str = Form(""),
    time_filter: str = Form("1 Jahr"),
):
    import asyncio

    templates = request.app.state.templates

    raw_input = ticker_input.strip()
    if not raw_input:
        return HTMLResponse(
            "<div class='card' style='text-align:center;padding:32px;'>"
            "<p>Bitte einen Ticker oder Firmennamen eingeben.</p></div>"
        )

    # Run all blocking work in a thread so we don't block the event loop
    ctx = await asyncio.to_thread(_build_analysis_context, raw_input, time_filter)

    if isinstance(ctx, str):
        # Error message returned
        return HTMLResponse(ctx)

    return templates.TemplateResponse(
        request=request,
        name="partials/analysis_content.html",
        context=ctx,
    )


def _build_analysis_context(raw_input: str, time_filter: str) -> dict | str:
    """Synchronous function that builds the full analysis context.
    
    Returns a dict for the template context, or a str with an HTML error message.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Resolve ticker
    resolved = resolve_ticker(raw_input)
    if resolved:
        ticker = resolved["ticker"]
        display_ticker = resolved.get("display", ticker)
    else:
        ticker = raw_input.upper()
        display_ticker = ticker

    # Load stock details (must be sequential â€” everything depends on it)
    try:
        details = cached_stock_details(ticker)
    except Exception as e:
        return f"<div class='alert alert-danger'>Fehler beim Laden: {e}</div>"

    if details is None:
        return f"<div class='alert alert-danger'>Keine Daten fuer <b>{ticker}</b> gefunden.</div>"

    stats = details["stats"]
    hist = details["hist_1y"]
    close = hist["Close"]
    info_data = details.get("info", {})

    # Time filter mapping
    hist_map = {
        "1 Tag": details.get("hist_1d", hist),
        "1 Woche": details.get("hist_1w", hist),
        "1 Monat": details.get("hist_1m", hist),
        "YTD": details.get("hist_ytd", hist),
        "1 Jahr": hist,
        "5 Jahre": details.get("hist_5y", hist),
        "Gesamt": details.get("hist_max", details.get("hist_5y", hist)),
    }
    selected_hist = hist_map.get(time_filter, hist)

    # === Build all chart JSONs ===
    charts = {}

    from charts import (
        plot_candlestick, plot_rsi, plot_macd as plot_macd_chart,
        plot_bollinger as plot_boll_chart, plot_stochastic as plot_stoch_chart,
        plot_returns_distribution, plot_timeseries,
        plot_liquidity_sweeps as plot_liq_chart,
        plot_swing_overview as plot_swing_chart,
        plot_order_flow as plot_flow_chart,
        plot_financials_chart,
    )

    # --- Charts (CPU-bound, fast) ---
    try:
        charts["candlestick"] = _fig_to_json(plot_candlestick(
            selected_hist, f"{ticker} â€” Candlestick ({time_filter})",
            sma_20=details.get("sma_20"), sma_50=details.get("sma_50"),
            sma_200=details.get("sma_200"),
        ))
    except Exception:
        charts["candlestick"] = "null"

    rsi_series = details.get("rsi_series")
    rsi_val = _safe_float(stats.get("rsi"))
    try:
        if rsi_series is not None:
            charts["rsi"] = _fig_to_json(plot_rsi(rsi_series, f"RSI (14) â€” {ticker}"))
        else:
            charts["rsi"] = "null"
    except Exception:
        charts["rsi"] = "null"

    macd_bullish = None
    try:
        macd_line, signal_line, histogram = calc_macd(close)
        charts["macd"] = _fig_to_json(plot_macd_chart(
            macd_line, signal_line, histogram, f"MACD â€” {ticker}"
        ))
        last_macd = float(macd_line.dropna().iloc[-1]) if not macd_line.dropna().empty else 0
        last_signal = float(signal_line.dropna().iloc[-1]) if not signal_line.dropna().empty else 0
        macd_bullish = last_macd > last_signal
    except Exception:
        charts["macd"] = "null"

    boll_signal = None
    try:
        upper, middle, lower = calc_bollinger(close)
        charts["bollinger"] = _fig_to_json(plot_boll_chart(
            close, upper, middle, lower, f"Bollinger Baender â€” {ticker}"
        ))
        last_close = float(close.iloc[-1])
        last_upper = float(upper.dropna().iloc[-1]) if not upper.dropna().empty else 0
        last_lower = float(lower.dropna().iloc[-1]) if not lower.dropna().empty else 0
        if last_close >= last_upper:
            boll_signal = "overbought"
        elif last_close <= last_lower:
            boll_signal = "oversold"
        else:
            boll_signal = "normal"
    except Exception:
        charts["bollinger"] = "null"

    last_k = None
    try:
        k_line, d_line = calc_stochastic(hist["High"], hist["Low"], hist["Close"])
        charts["stochastic"] = _fig_to_json(plot_stoch_chart(
            k_line, d_line, f"Stochastic â€” {ticker}"
        ))
        last_k = float(k_line.dropna().iloc[-1]) if not k_line.dropna().empty else 50
    except Exception:
        charts["stochastic"] = "null"

    returns = details.get("returns")
    returns_stats = {}
    try:
        if returns is not None and not returns.empty:
            charts["returns"] = _fig_to_json(plot_returns_distribution(
                returns, f"Taegliche Renditen â€” {ticker}"
            ))
            returns_stats = {
                "avg": f"{returns.mean()*100:.3f}",
                "max_gain": f"{returns.max()*100:+.2f}",
                "max_loss": f"{returns.min()*100:+.2f}",
                "sharpe": f"{(returns.mean()/returns.std()*np.sqrt(252)):.2f}" if returns.std() > 0 else "â€”",
            }
        else:
            charts["returns"] = "null"
    except Exception:
        charts["returns"] = "null"

    hist_5y = details.get("hist_5y")
    try:
        if hist_5y is not None and not hist_5y.empty:
            charts["hist5y"] = _fig_to_json(plot_timeseries(
                hist_5y, f"{ticker} â€” 5-Jahres-Uebersicht", color="#a855f7", height=400
            ))
        else:
            charts["hist5y"] = "null"
    except Exception:
        charts["hist5y"] = "null"

    fin_data = details.get("financials", [])
    try:
        if fin_data:
            charts["financials"] = _fig_to_json(plot_financials_chart(fin_data))
        else:
            charts["financials"] = "null"
    except Exception:
        charts["financials"] = "null"

    # --- SMC / Swing / Order Flow (CPU-bound from hist, fast) ---
    sweeps = []
    try:
        sweeps = detect_liquidity_sweeps(hist["High"], hist["Low"], close) or []
        if sweeps:
            charts["liquidity"] = _fig_to_json(plot_liq_chart(
                hist, sweeps, f"Liquidity Sweeps â€” {display_ticker}"
            ))
        else:
            charts["liquidity"] = "null"
    except Exception:
        charts["liquidity"] = "null"

    smc_data = None
    try:
        from smc.indicators import analyze_smc
        from smc.charts import plot_smc
        htf_weekly = details.get("hist_max")
        htf_monthly = details.get("hist_monthly")
        smc_data = analyze_smc(hist, htf_df=htf_weekly, monthly_df=htf_monthly)
        if smc_data and "fvgs" in smc_data:
            charts["smc"] = _fig_to_json(plot_smc(
                hist, smc_data, f"SMC & Liquiditaetszonen â€” {display_ticker}"
            ))
        else:
            charts["smc"] = "null"
    except Exception:
        charts["smc"] = "null"

    swing = None
    try:
        swing = calc_swing_signals(hist["High"], hist["Low"], close, hist["Volume"])
        if swing:
            charts["swing"] = _fig_to_json(plot_swing_chart(
                hist, swing, f"Swing Trading â€” {display_ticker}"
            ))
        else:
            charts["swing"] = "null"
    except Exception:
        charts["swing"] = "null"

    flow = None
    try:
        flow = calc_order_flow(hist["High"], hist["Low"], close, hist["Volume"])
        if flow:
            charts["orderflow"] = _fig_to_json(plot_flow_chart(
                hist, flow, f"Order Flow â€” {display_ticker}"
            ))
        else:
            charts["orderflow"] = "null"
    except Exception:
        charts["orderflow"] = "null"

    # === PARALLEL: Independent service calls (I/O-bound) ===
    # Each of these makes independent API/DB calls, so run them all concurrently
    dcf = None
    balance = None
    margins = None
    margins_chart = "null"
    peers_html = ""
    div_data = None
    div_chart = "null"
    insider = None
    analyst = None
    earnings_profile = None
    eps_chart = "null"
    drift_chart = "null"
    opts = None
    company_news = []
    macro_events = []
    quant_data = {}
    signal_history = []
    sum_data = {}

    def _fetch_dcf():
        return calc_dcf_valuation(info_data)

    def _fetch_balance():
        return calc_balance_sheet_quality(info_data)

    def _fetch_margins():
        return get_margin_trends(ticker)

    def _fetch_peers():
        yfin_sector_raw = info_data.get("sector", "")
        yfin_industry_raw = info_data.get("industry", "")
        return get_sector_peers(ticker, yfin_sector_raw, yfin_industry_raw)

    def _fetch_dividend():
        return calc_dividend_analysis(ticker)

    def _fetch_insider():
        return get_insider_institutional(ticker)

    def _fetch_analyst():
        return get_analyst_consensus(ticker)

    def _fetch_earnings():
        from services.earnings import get_earnings_history
        return get_earnings_history(ticker)

    def _fetch_options():
        return cached_options_overview(ticker)

    def _fetch_news():
        return cached_company_news(ticker) or []

    def _fetch_events():
        return cached_events_for_ticker(ticker, days=7) or []

    def _fetch_summary():
        return calc_technical_summary(stats, hist, info=info_data, ticker=ticker)

    def _fetch_quant():
        from services.valuation import determine_sector_category
        sector_cat, tab_name = determine_sector_category(stats, details)
        result_data = {"sector_cat": sector_cat, "tab_name": tab_name}
        if sector_cat == "finanzen":
            from services.valuation import calc_excess_returns
            result_data["result"] = calc_excess_returns(info_data)
        elif sector_cat == "tech":
            from services.valuation import calc_rule_of_40
            result_data["result"] = calc_rule_of_40(info_data)
        elif sector_cat == "hardware":
            from services.valuation import calc_hardware_cycle
            result_data["result"] = calc_hardware_cycle(info_data)
        elif sector_cat == "pharma":
            from services.valuation import calc_rnpv_proxy
            result_data["result"] = calc_rnpv_proxy(info_data)
        elif sector_cat == "energie":
            from services.valuation import calc_ev_dacf
            result_data["result"] = calc_ev_dacf(info_data)
        elif sector_cat == "telekom":
            from services.valuation import calc_telecom_metrics
            result_data["result"] = calc_telecom_metrics(info_data)
        elif sector_cat == "logistik":
            from services.valuation import calc_logistics_metrics
            result_data["result"] = calc_logistics_metrics(info_data)
        elif sector_cat == "defense":
            from services.valuation import calc_defense_metrics
            result_data["result"] = calc_defense_metrics(info_data)
        elif sector_cat == "auto":
            from services.valuation import calc_auto_metrics
            result_data["result"] = calc_auto_metrics(info_data)
        elif sector_cat == "maschinenbau":
            from services.valuation import calc_machinery_metrics
            result_data["result"] = calc_machinery_metrics(info_data)
        elif sector_cat == "industrie":
            from services.valuation import calc_hgb_proxy
            result_data["result"] = calc_hgb_proxy(info_data)
        elif sector_cat == "csvs":
            from services.valuation import calc_csvs
            result_data["result"] = calc_csvs(info_data)
        return result_data

    def _fetch_signals():
        from models.signal import SignalStore
        from services.signal_history import update_stale_signals
        try:
            update_stale_signals()
        except Exception:
            pass
        return SignalStore.get_all(ticker=ticker, limit=5)

    def _fetch_correlation():
        benchmarks = ["SPY", "QQQ", "GLD"]
        all_tickers = [ticker] + [b for b in benchmarks if b.upper() != ticker.upper()]
        tickers_str = ",".join(all_tickers)
        labels_str = tickers_str
        return cached_correlation(tickers_str, labels_str, "1y")

    # Run all independent service calls in parallel
    task_map = {
        "dcf": _fetch_dcf,
        "balance": _fetch_balance,
        "margins": _fetch_margins,
        "peers": _fetch_peers,
        "dividend": _fetch_dividend,
        "insider": _fetch_insider,
        "analyst": _fetch_analyst,
        "earnings": _fetch_earnings,
        "options": _fetch_options,
        "news": _fetch_news,
        "events": _fetch_events,
        "summary": _fetch_summary,
        "quant": _fetch_quant,
        "signals": _fetch_signals,
        "correlation": _fetch_correlation,
    }

    results_map = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_to_key = {pool.submit(fn): key for key, fn in task_map.items()}
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                results_map[key] = future.result()
            except Exception:
                results_map[key] = None

    # Unpack parallel results
    dcf = results_map.get("dcf")
    balance = results_map.get("balance")
    margins = results_map.get("margins")
    insider = results_map.get("insider")
    analyst = results_map.get("analyst")
    earnings_profile = results_map.get("earnings")
    opts = results_map.get("options")
    company_news = results_map.get("news") or []
    macro_events = results_map.get("events") or []
    sum_data = results_map.get("summary") or {}
    quant_data = results_map.get("quant") or {}
    signal_history = results_map.get("signals") or []
    div_data = results_map.get("dividend")

    # Save quick-score signal for tracking (like Streamlit version)
    try:
        if sum_data and sum_data.get("confidence") and stats.get("current_price"):
            from models.signal import SignalStore
            confidence = sum_data["confidence"]
            if confidence >= 70:
                sig_type = "buy"
            elif confidence <= 40:
                sig_type = "sell"
            else:
                sig_type = "hold"
            SignalStore.create(
                ticker=ticker,
                signal_type=sig_type,
                confidence=confidence,
                price_at_signal=stats["current_price"],
            )
    except Exception:
        pass

    # Post-process: margins chart
    try:
        if margins and len(margins) >= 2:
            import plotly.graph_objects as go
            fig_m = go.Figure()
            years = [str(m['year']) for m in margins]
            for name, key, color in [
                ("Bruttomarge", "gross_margin", "#22c55e"),
                ("EBITDA-Marge", "ebitda_margin", "#3b82f6"),
                ("Nettomarge", "net_margin", "#a855f7"),
            ]:
                vals = [m.get(key) for m in margins]
                if any(v is not None for v in vals):
                    fig_m.add_trace(go.Scatter(
                        x=years, y=vals, name=name, mode="lines+markers",
                        line=dict(color=color, width=2),
                    ))
            fig_m.update_layout(
                template="plotly_dark", height=350,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                yaxis_title="Marge (%)", xaxis_title="Jahr",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=40, r=20, t=30, b=40),
            )
            margins_chart = _fig_to_json(fig_m)
    except Exception:
        pass

    # Post-process: peers HTML
    try:
        peers_raw = results_map.get("peers")
        if peers_raw is not None and not peers_raw.empty:
            peers_html = peers_raw.to_html(
                classes="data-table", index=False,
                float_format=lambda x: f"{x:.2f}" if isinstance(x, float) else str(x)
            )
    except Exception:
        pass

    # Post-process: dividend chart
    try:
        if div_data and div_data.get("has_dividends") and div_data.get("annual_dividends"):
            import plotly.graph_objects as go
            div_years = [str(d['year']) for d in div_data['annual_dividends']]
            div_amounts = [d['amount'] for d in div_data['annual_dividends']]
            fig_div = go.Figure(go.Bar(x=div_years, y=div_amounts, marker_color="#22c55e"))
            fig_div.update_layout(
                template="plotly_dark", height=300,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                yaxis_title="Dividende (EUR)", xaxis_title="Jahr",
                margin=dict(l=40, r=20, t=20, b=40),
            )
            div_chart = _fig_to_json(fig_div)
    except Exception:
        pass

    # Post-process: EPS chart + drift chart for Earnings section
    try:
        if earnings_profile and earnings_profile.events:
            import plotly.graph_objects as go

            # EPS chart: last 12 quarters, sorted chronologically
            chart_events = sorted(earnings_profile.events, key=lambda e: e.date)[-12:]
            quarters = [e.quarter for e in chart_events]
            actuals = [e.eps_actual for e in chart_events]
            estimates = [e.eps_estimate for e in chart_events]

            fig_eps = go.Figure()
            fig_eps.add_trace(go.Bar(
                x=quarters, y=estimates, name="EPS Estimate",
                marker_color="rgba(100, 200, 255, 0.4)",
                marker_line_color="#64C8FF", marker_line_width=1,
            ))
            bar_colors = []
            for e in chart_events:
                if e.result == "Beat": bar_colors.append("#22c55e")
                elif e.result == "Miss": bar_colors.append("#ef4444")
                else: bar_colors.append("#eab308")
            fig_eps.add_trace(go.Bar(
                x=quarters, y=actuals, name="EPS Actual",
                marker_color=bar_colors, marker_line_width=0,
            ))
            fig_eps.update_layout(
                template="plotly_dark", height=380, barmode="group",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                yaxis_title="EPS ($)", xaxis_title="Quartal",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=50, r=20, t=30, b=50), xaxis_tickangle=-45,
                font=dict(family="Inter, sans-serif", size=12, color="#cbd5e1"),
            )
            eps_chart = _fig_to_json(fig_eps)

            # Drift chart
            drift_events = sorted(
                [e for e in earnings_profile.events if e.drift_1d is not None],
                key=lambda e: e.date
            )[-12:]
            if drift_events:
                fig_drift = go.Figure()
                d_quarters = [e.quarter for e in drift_events]
                for days_label, get_val, color in [
                    ("1 Tag", lambda e: e.drift_1d, "#64C8FF"),
                    ("5 Tage", lambda e: e.drift_5d, "#a855f7"),
                    ("20 Tage", lambda e: e.drift_20d, "#f97316"),
                ]:
                    vals = [get_val(e) for e in drift_events]
                    fig_drift.add_trace(go.Scatter(
                        x=d_quarters, y=vals, name=days_label,
                        mode="lines+markers", line=dict(color=color, width=2),
                        marker=dict(size=8),
                    ))
                fig_drift.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
                fig_drift.update_layout(
                    template="plotly_dark", height=350,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    yaxis_title="Kursaenderung (%)", xaxis_title="Quartal",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                    margin=dict(l=50, r=20, t=30, b=50), xaxis_tickangle=-45,
                    font=dict(family="Inter, sans-serif", size=12, color="#cbd5e1"),
                )
                drift_chart = _fig_to_json(fig_drift)
    except Exception:
        pass

    # ATR + Position Sizing defaults
    atr_val = None
    try:
        atr_series = calc_atr(hist["High"], hist["Low"], hist["Close"], 14)
        atr_val = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else None
    except Exception:
        pass

    corr_chart = "null"
    try:
        corr_df = results_map.get("correlation")
        if corr_df is not None and not corr_df.empty:
            from charts import plot_correlation_matrix
            corr_chart = _fig_to_json(plot_correlation_matrix(
                corr_df, f"Korrelation — {display_ticker} vs. Benchmarks"
            ))
    except Exception:
        pass

    ps_defaults = None
    try:
        if atr_val and stats.get("current_price"):
            ps_defaults = calc_position_sizing(
                current_price=stats["current_price"],
                atr_val=atr_val,
                portfolio_value=10000,
                max_risk_pct=0.02,
            )
    except Exception:
        pass

    # === Build context ===
    ctx = {
        "ticker": ticker,
        "display_ticker": display_ticker,
        "stats": stats,
        "time_filter": time_filter,
        "charts": charts,
        "rsi_val": rsi_val,
        "macd_bullish": macd_bullish,
        "boll_signal": boll_signal,
        "last_k": last_k,
        "returns_stats": returns_stats,
        "fin_data": fin_data,
        "sweeps": sweeps,
        "smc_data": smc_data,
        "swing": swing,
        "flow": flow,
        "dcf": dcf,
        "balance": balance,
        "margins": margins,
        "margins_chart": margins_chart,
        "peers_html": peers_html,
        "div_data": div_data,
        "div_chart": div_chart,
        "insider": insider,
        "analyst": analyst,
        "earnings_profile": earnings_profile,
        "eps_chart": eps_chart,
        "drift_chart": drift_chart,
        "atr_val": atr_val,
        "sum_data": sum_data,
        "macro_events": macro_events,
        "opts": opts,
        "company_news": company_news,
        "quant_data": quant_data,
        "signal_history": signal_history,
        "corr_chart": corr_chart,
        "ps_defaults": ps_defaults,
        "info_data": info_data,
        "fmt_price": _fmt_price,
        "fmt_big": _fmt_big,
    }
    return ctx
