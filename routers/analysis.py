"""
routers/analysis.py — Analyse-Seite (Herzstueck des Dashboards).

GET  /analysis            → Ticker-Eingabe
POST /analysis/load       → Laedt vollstaendige Analyse als HTMX-Partial
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
    return json.dumps(fig.to_dict(), default=str)


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
        return "—"
    return f"{val:,.2f}{suffix}"


def _fmt_big(val):
    if val is None:
        return "—"
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
    templates = request.app.state.templates

    raw_input = ticker_input.strip()
    if not raw_input:
        return HTMLResponse(
            "<div class='card' style='text-align:center;padding:32px;'>"
            "<p>Bitte einen Ticker oder Firmennamen eingeben.</p></div>"
        )

    # Resolve ticker
    resolved = resolve_ticker(raw_input)
    if resolved:
        ticker = resolved["ticker"]
        display_ticker = resolved.get("display", ticker)
    else:
        ticker = raw_input.upper()
        display_ticker = ticker

    # Load stock details
    try:
        details = cached_stock_details(ticker)
    except Exception as e:
        return HTMLResponse(
            f"<div class='alert alert-danger'>Fehler beim Laden: {e}</div>"
        )

    if details is None:
        return HTMLResponse(
            f"<div class='alert alert-danger'>Keine Daten fuer <b>{ticker}</b> gefunden.</div>"
        )

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

    # 1. Candlestick
    from charts import (
        plot_candlestick, plot_rsi, plot_macd as plot_macd_chart,
        plot_bollinger as plot_boll_chart, plot_stochastic as plot_stoch_chart,
        plot_returns_distribution, plot_timeseries,
        plot_liquidity_sweeps as plot_liq_chart,
        plot_swing_overview as plot_swing_chart,
        plot_order_flow as plot_flow_chart,
        plot_financials_chart,
    )

    try:
        charts["candlestick"] = _fig_to_json(plot_candlestick(
            selected_hist, f"{ticker} — Candlestick ({time_filter})",
            sma_20=details.get("sma_20"), sma_50=details.get("sma_50"),
            sma_200=details.get("sma_200"),
        ))
    except Exception:
        charts["candlestick"] = "null"

    # RSI
    rsi_series = details.get("rsi_series")
    rsi_val = _safe_float(stats.get("rsi"))
    try:
        if rsi_series is not None:
            charts["rsi"] = _fig_to_json(plot_rsi(rsi_series, f"RSI (14) — {ticker}"))
        else:
            charts["rsi"] = "null"
    except Exception:
        charts["rsi"] = "null"

    # MACD
    try:
        macd_line, signal_line, histogram = calc_macd(close)
        charts["macd"] = _fig_to_json(plot_macd_chart(
            macd_line, signal_line, histogram, f"MACD — {ticker}"
        ))
        last_macd = float(macd_line.dropna().iloc[-1]) if not macd_line.dropna().empty else 0
        last_signal = float(signal_line.dropna().iloc[-1]) if not signal_line.dropna().empty else 0
        macd_bullish = last_macd > last_signal
    except Exception:
        charts["macd"] = "null"
        macd_bullish = None

    # Bollinger
    try:
        upper, middle, lower = calc_bollinger(close)
        charts["bollinger"] = _fig_to_json(plot_boll_chart(
            close, upper, middle, lower, f"Bollinger Baender — {ticker}"
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
        boll_signal = None

    # Stochastic
    try:
        k_line, d_line = calc_stochastic(hist["High"], hist["Low"], hist["Close"])
        charts["stochastic"] = _fig_to_json(plot_stoch_chart(
            k_line, d_line, f"Stochastic — {ticker}"
        ))
        last_k = float(k_line.dropna().iloc[-1]) if not k_line.dropna().empty else 50
    except Exception:
        charts["stochastic"] = "null"
        last_k = None

    # Returns
    returns = details.get("returns")
    returns_stats = {}
    try:
        if returns is not None and not returns.empty:
            charts["returns"] = _fig_to_json(plot_returns_distribution(
                returns, f"Taegliche Renditen — {ticker}"
            ))
            returns_stats = {
                "avg": f"{returns.mean()*100:.3f}",
                "max_gain": f"{returns.max()*100:+.2f}",
                "max_loss": f"{returns.min()*100:+.2f}",
                "sharpe": f"{(returns.mean()/returns.std()*np.sqrt(252)):.2f}" if returns.std() > 0 else "—",
            }
        else:
            charts["returns"] = "null"
    except Exception:
        charts["returns"] = "null"

    # 5Y
    hist_5y = details.get("hist_5y")
    try:
        if hist_5y is not None and not hist_5y.empty:
            charts["hist5y"] = _fig_to_json(plot_timeseries(
                hist_5y, f"{ticker} — 5-Jahres-Uebersicht", color="#a855f7", height=400
            ))
        else:
            charts["hist5y"] = "null"
    except Exception:
        charts["hist5y"] = "null"

    # Financials chart
    fin_data = details.get("financials", [])
    try:
        if fin_data:
            charts["financials"] = _fig_to_json(plot_financials_chart(fin_data))
        else:
            charts["financials"] = "null"
    except Exception:
        charts["financials"] = "null"

    # === SMC / Swing / Order Flow ===
    # Liquidity Sweeps
    sweeps = []
    try:
        sweeps = detect_liquidity_sweeps(hist["High"], hist["Low"], close) or []
        if sweeps:
            charts["liquidity"] = _fig_to_json(plot_liq_chart(
                hist, sweeps, f"Liquidity Sweeps — {display_ticker}"
            ))
        else:
            charts["liquidity"] = "null"
    except Exception:
        charts["liquidity"] = "null"

    # SMC
    smc_data = None
    try:
        from smc.indicators import analyze_smc
        from smc.charts import plot_smc
        htf_weekly = details.get("hist_max")
        htf_monthly = details.get("hist_monthly")
        smc_data = analyze_smc(hist, htf_df=htf_weekly, monthly_df=htf_monthly)
        if smc_data and "fvgs" in smc_data:
            charts["smc"] = _fig_to_json(plot_smc(
                hist, smc_data, f"SMC & Liquiditaetszonen — {display_ticker}"
            ))
        else:
            charts["smc"] = "null"
    except Exception:
        charts["smc"] = "null"

    # Swing
    swing = None
    try:
        swing = calc_swing_signals(hist["High"], hist["Low"], close, hist["Volume"])
        if swing:
            charts["swing"] = _fig_to_json(plot_swing_chart(
                hist, swing, f"Swing Trading — {display_ticker}"
            ))
        else:
            charts["swing"] = "null"
    except Exception:
        charts["swing"] = "null"

    # Order Flow
    flow = None
    try:
        flow = calc_order_flow(hist["High"], hist["Low"], close, hist["Volume"])
        if flow:
            charts["orderflow"] = _fig_to_json(plot_flow_chart(
                hist, flow, f"Order Flow — {display_ticker}"
            ))
        else:
            charts["orderflow"] = "null"
    except Exception:
        charts["orderflow"] = "null"

    # === Fundamental Data ===
    # DCF
    dcf = None
    try:
        dcf = calc_dcf_valuation(info_data)
    except Exception:
        pass

    # Balance Sheet
    balance = None
    try:
        balance = calc_balance_sheet_quality(info_data)
    except Exception:
        pass

    # Margins
    margins = None
    margins_chart = "null"
    try:
        margins = get_margin_trends(ticker)
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

    # Peers
    peers_html = ""
    try:
        yfin_sector_raw = info_data.get("sector", "")
        yfin_industry_raw = info_data.get("industry", "")
        peers = get_sector_peers(ticker, yfin_sector_raw, yfin_industry_raw)
        if peers is not None and not peers.empty:
            peers_html = peers.to_html(
                classes="data-table", index=False,
                float_format=lambda x: f"{x:.2f}" if isinstance(x, float) else str(x)
            )
    except Exception:
        pass

    # Dividend
    div_data = None
    div_chart = "null"
    try:
        div_data = calc_dividend_analysis(ticker)
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

    # Insider
    insider = None
    try:
        insider = get_insider_institutional(ticker)
    except Exception:
        pass

    # Analyst
    analyst = None
    try:
        analyst = get_analyst_consensus(ticker)
    except Exception:
        pass

    # Earnings
    earnings_profile = None
    eps_chart = "null"
    try:
        from services.earnings import get_earnings_history
        earnings_profile = get_earnings_history(ticker)
    except Exception:
        pass

    # ATR + Position Sizing defaults
    atr_val = None
    try:
        atr_series = calc_atr(hist["High"], hist["Low"], hist["Close"], 14)
        atr_val = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else None
    except Exception:
        pass

    # Summary / Scoring
    sum_data = {}
    try:
        sum_data = calc_technical_summary(stats, hist, info=info_data, ticker=ticker)
    except Exception:
        pass

    # Macro Events
    macro_events = []
    try:
        macro_events = cached_events_for_ticker(ticker, days=7) or []
    except Exception:
        pass

    # Options
    opts = None
    try:
        opts = cached_options_overview(ticker)
    except Exception:
        pass

    # News
    company_news = []
    try:
        company_news = cached_company_news(ticker) or []
    except Exception:
        pass

    # === Quant (sector-specific) ===
    quant_data = {}
    try:
        from services.valuation import determine_sector_category
        sector_cat, tab_name = determine_sector_category(stats, details)
        quant_data["sector_cat"] = sector_cat
        quant_data["tab_name"] = tab_name

        # Call the appropriate valuation function
        if sector_cat == "finanzen":
            from services.valuation import calc_excess_returns
            quant_data["result"] = calc_excess_returns(info_data)
        elif sector_cat == "tech":
            from services.valuation import calc_rule_of_40
            quant_data["result"] = calc_rule_of_40(info_data)
        elif sector_cat == "hardware":
            from services.valuation import calc_hardware_cycle
            quant_data["result"] = calc_hardware_cycle(info_data)
        # Add more sectors as needed — for now fallback
    except Exception:
        quant_data = {}

    # Signal history
    signal_history = []
    try:
        from models.signal import SignalStore
        from services.signal_history import update_stale_signals
        try:
            update_stale_signals()
        except Exception:
            pass
        signal_history = SignalStore.get_all(ticker=ticker, limit=5)
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
        "atr_val": atr_val,
        "sum_data": sum_data,
        "macro_events": macro_events,
        "opts": opts,
        "company_news": company_news,
        "quant_data": quant_data,
        "signal_history": signal_history,
        "fmt_price": _fmt_price,
        "fmt_big": _fmt_big,
    }
    return templates.TemplateResponse(
        request=request,
        name="partials/analysis_content.html",
        context=ctx,
    )
