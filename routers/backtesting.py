"""routers/backtesting.py — Strategy Backtesting Engine."""
import csv
import os
import json
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_XETRA_CSV = os.path.join(_DATA_DIR, "xetra_stocks.csv")
_MARKET_CACHE = None


def _get_header_metrics():
    from main import get_header_metrics
    return get_header_metrics()


def _fig_to_json(fig):
    if fig is None:
        return "null"
    return json.dumps(fig.to_dict(), default=str)


def _load_market_presets() -> dict[str, list[dict]]:
    global _MARKET_CACHE
    if _MARKET_CACHE is not None:
        return _MARKET_CACHE
    presets = {
        "US (Top 30)": [
            {"ticker": "AAPL", "name": "Apple Inc."}, {"ticker": "MSFT", "name": "Microsoft Corp."},
            {"ticker": "AMZN", "name": "Amazon.com Inc."}, {"ticker": "GOOGL", "name": "Alphabet Inc."},
            {"ticker": "META", "name": "Meta Platforms Inc."}, {"ticker": "NVDA", "name": "NVIDIA Corp."},
            {"ticker": "TSLA", "name": "Tesla Inc."}, {"ticker": "JPM", "name": "JPMorgan Chase"},
            {"ticker": "V", "name": "Visa Inc."}, {"ticker": "JNJ", "name": "Johnson & Johnson"},
            {"ticker": "WMT", "name": "Walmart Inc."}, {"ticker": "PG", "name": "Procter & Gamble"},
            {"ticker": "MA", "name": "Mastercard Inc."}, {"ticker": "UNH", "name": "UnitedHealth Group"},
            {"ticker": "HD", "name": "Home Depot Inc."}, {"ticker": "DIS", "name": "Walt Disney Co."},
            {"ticker": "NFLX", "name": "Netflix Inc."}, {"ticker": "KO", "name": "Coca-Cola Co."},
            {"ticker": "PEP", "name": "PepsiCo Inc."}, {"ticker": "MCD", "name": "McDonald's Corp."},
            {"ticker": "COST", "name": "Costco Wholesale"}, {"ticker": "ABBV", "name": "AbbVie Inc."},
            {"ticker": "CRM", "name": "Salesforce Inc."}, {"ticker": "AMD", "name": "AMD"},
            {"ticker": "INTC", "name": "Intel Corp."}, {"ticker": "BA", "name": "Boeing Co."},
            {"ticker": "GS", "name": "Goldman Sachs"}, {"ticker": "CAT", "name": "Caterpillar Inc."},
            {"ticker": "XOM", "name": "Exxon Mobil"}, {"ticker": "CVX", "name": "Chevron Corp."},
        ],
    }
    if os.path.exists(_XETRA_CSV):
        try:
            with open(_XETRA_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                seen = {}
                for row in reader:
                    ticker = row.get("Kürzel", "").strip()
                    name = row.get("Name", "").strip()
                    index = row.get("Index", "").strip()
                    if not ticker or not name or not index:
                        continue
                    key = "Xetra International" if index == "XETRA International" else index
                    if key not in presets:
                        presets[key] = []
                    dedup_key = f"{key}:{ticker}"
                    if dedup_key not in seen:
                        presets[key].append({"ticker": ticker, "name": name})
                        seen[dedup_key] = True
        except Exception:
            pass
    _MARKET_CACHE = presets
    return presets


STRATEGIES = {
    "RSI_Mean_Reversion": "RSI Mean Reversion (Oszillator)",
    "SMA_Cross_Trend": "SMA Golden Cross (Trendfolge)",
    "MACD_Momentum": "MACD Crossover (Momentum)",
    "Bollinger_Breakout": "Bollinger Bands Breakout (Volatilität)",
    "SMC_FVG_Bounce": "Smart Money Concept: FVG Bounce (Proxy)",
}

COST_MODELS = {
    "Trade Republic / Scalable": 1.0,
    "Interactive Brokers": 2.5,
    "Comdirect / Consors": 9.90,
    "Kostenlos (Theoretisch)": 0.0,
}


@router.get("/backtesting", response_class=HTMLResponse)
async def backtesting_page(request: Request):
    templates = request.app.state.templates
    presets = _load_market_presets()
    market_names = list(presets.keys())
    # Flatten first market's tickers for initial display
    first_market = market_names[0] if market_names else "US (Top 30)"
    tickers = presets.get(first_market, [])
    presets_json = json.dumps(presets, default=str)

    ctx = {
        "current_path": "/backtesting",
        "header_metrics": _get_header_metrics(),
        "market_names": market_names,
        "tickers": tickers,
        "strategies": STRATEGIES,
        "cost_models": list(COST_MODELS.keys()),
        "presets_json": presets_json,
    }
    return templates.TemplateResponse(request=request, name="pages/backtesting.html", context=ctx)


@router.post("/backtesting/run", response_class=HTMLResponse)
async def backtesting_run(
    request: Request,
    ticker_input: str = Form(...),
    strategy: str = Form(...),
    period: str = Form("5y"),
    initial_capital: float = Form(10000),
    cost_model: str = Form("Trade Republic / Scalable"),
    slippage: float = Form(0.1),
):
    templates = request.app.state.templates
    from services.cache import cached_stock_history
    from services.watchlist import resolve_ticker
    from services.backtesting import BacktestEngine
    import plotly.graph_objects as go

    commission = COST_MODELS.get(cost_model, 1.0)
    resolved = resolve_ticker(ticker_input)
    ticker = resolved["ticker"] if resolved else ticker_input

    try:
        hist = cached_stock_history(ticker, period)
    except Exception:
        hist = None

    if hist is None or hist.empty or len(hist) < 200:
        return templates.TemplateResponse(request=request, name="partials/backtest_error.html", context={
            "error": f"Nicht genug Daten für {ticker} ({period}). Min. 200 Handelstage nötig."
        })

    engine = BacktestEngine(hist, initial_capital, commission, slippage)
    try:
        equity_df, trades, metrics = engine.run_strategy(strategy)
    except ValueError as e:
        return templates.TemplateResponse(request=request, name="partials/backtest_error.html", context={
            "error": str(e)
        })

    display_name = ticker_input.replace(".DE", "") if ticker_input.endswith(".DE") else ticker_input
    strat_name = STRATEGIES.get(strategy, strategy)

    # Equity chart
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=[str(d) for d in equity_df.index], y=equity_df["Equity"].tolist(),
        mode="lines", name="Strategie (Netto)",
        line=dict(color="#22c55e", width=2),
        fill="tozeroy", fillcolor="rgba(34,197,94,0.08)",
    ))
    fig_eq.add_trace(go.Scatter(
        x=[str(d) for d in equity_df.index], y=equity_df["Benchmark"].tolist(),
        mode="lines", name="Buy & Hold",
        line=dict(color="#94a3b8", width=1, dash="dot"),
    ))
    fig_eq.update_layout(
        title=f"Portfolio: {display_name}",
        yaxis_title="Wert (€)", template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=400, hovermode="x unified",
    )
    equity_json = _fig_to_json(fig_eq)

    # Drawdown chart
    dd_json = "null"
    if "Drawdown" in equity_df.columns:
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=[str(d) for d in equity_df.index], y=equity_df["Drawdown"].tolist(),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.2)",
            line=dict(color="#ef4444", width=2), name="Drawdown %",
        ))
        fig_dd.update_layout(
            title="Drawdown", yaxis_title="Drawdown (%)", template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=300,
        )
        dd_json = _fig_to_json(fig_dd)

    ctx = {
        "display_name": display_name,
        "ticker": ticker,
        "strat_name": strat_name,
        "metrics": metrics,
        "initial_capital": initial_capital,
        "slippage": slippage,
        "period": period,
        "equity_json": equity_json,
        "dd_json": dd_json,
        "trades": trades[:100],  # limit for rendering
    }
    return templates.TemplateResponse(request=request, name="partials/backtest_results.html", context=ctx)
