"""
services/cache.py — Streamlit-Caching-Wrappers für alle Datendienste.

Zentraler Cache-Layer, der marktbewusste TTLs bereitstellt
(kürzere TTLs bei offenen Märkten, längere bei geschlossenen).
"""

import streamlit as st
import pandas as pd
from services.market_data import (
    get_quote, get_history, get_multi_quotes, get_yield_spread,
    get_vix_value, get_sp500_close_series, get_gold_close_series,
    get_stock_details, get_german_inflation, get_stock_listings,
    get_correlation_matrix, get_sector_performance,
    get_earnings_dates, get_sp500_components,
    get_components_performance
)
from services.news import get_regional_news, get_company_news
from services.economic_calendar import get_upcoming_events, get_calendar_summary, get_events_for_ticker
from services.options import get_options_overview
from services.portfolio import calc_equity_curve, calc_performance_metrics, calc_sector_allocation
from services.risk import calc_full_risk_report
from services.signal_history import get_signal_statistics, calc_hit_rate, calc_calibration_chart

# ---------------------------------------------------------------------------
# Dynamischer Cache-TTL: Börsen offen → 5 Min, geschlossen → 30 Min
# ---------------------------------------------------------------------------

def _is_market_open() -> bool:
    """Prüft, ob Xetra (9-17:30 CET) oder US (15:30-22 CET) gerade offen."""
    from datetime import datetime
    import zoneinfo
    now = datetime.now(zoneinfo.ZoneInfo("Europe/Berlin"))
    if now.weekday() >= 5:
        return False
    h, m = now.hour, now.minute
    t = h * 60 + m
    xetra_open = 9 * 60 <= t <= 17 * 60 + 30
    us_open = 15 * 60 + 30 <= t <= 22 * 60
    return xetra_open or us_open

def _market_ttl() -> int:
    return 300 if _is_market_open() else 1800

@st.cache_data(ttl=300, show_spinner=False)
def cached_quote(ticker: str): return get_quote(ticker)

@st.cache_data(ttl=300, show_spinner=False)
def cached_history(ticker: str, period: str = "1y"): return get_history(ticker, period)

@st.cache_data(ttl=300, show_spinner=False)
def cached_yield_spread(): return get_yield_spread()

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_vix_long(): return get_vix_value()

@st.cache_data(ttl=300, show_spinner=False)
def _cached_vix_short(): return get_vix_value()

def cached_vix(): return _cached_vix_short() if _is_market_open() else _cached_vix_long()

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_sp500_long(): return get_sp500_close_series()

@st.cache_data(ttl=300, show_spinner=False)
def _cached_sp500_short(): return get_sp500_close_series()

def cached_sp500(): return _cached_sp500_short() if _is_market_open() else _cached_sp500_long()

@st.cache_data(ttl=300, show_spinner=False)
def cached_multi(tickers_str: str):
    tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
    return get_multi_quotes(tickers)

@st.cache_data(ttl=300, show_spinner=False)
def cached_stock_details(ticker: str): return get_stock_details(ticker)

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_gold_long(): return get_gold_close_series()

@st.cache_data(ttl=300, show_spinner=False)
def _cached_gold_short(): return get_gold_close_series()

def cached_gold(): return _cached_gold_short() if _is_market_open() else _cached_gold_long()

@st.cache_data(ttl=300, show_spinner=False)
def cached_inflation(): return get_german_inflation()

@st.cache_data(ttl=3600, show_spinner=False)
def cached_listings(): return get_stock_listings()

@st.cache_data(ttl=300, show_spinner=False)
def cached_correlation(tickers_str: str, labels_str: str, period: str = "1y"):
    tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
    labels = [l.strip() for l in labels_str.split(",") if l.strip()] if labels_str else None
    return get_correlation_matrix(tickers, labels, period)

@st.cache_data(ttl=300, show_spinner=False)
def cached_sectors(period: str = "1d", region: str = "us"): return get_sector_performance(period, region)

@st.cache_data(ttl=600, show_spinner=False)
def cached_regional_news(region: str): return get_regional_news(region)

@st.cache_data(ttl=600, show_spinner=False)
def cached_company_news(ticker: str): return get_company_news(ticker)

@st.cache_data(ttl=600, show_spinner=False)
def cached_earnings(tickers_str: str, names_str: str):
    tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
    name_pairs = [p.split("=", 1) for p in names_str.split(",") if "=" in p]
    names = {k.strip(): v.strip() for k, v in name_pairs}
    return get_earnings_dates(tickers, names)

@st.cache_data(ttl=86400, show_spinner=False)
def cached_sp500_components(): return get_sp500_components()

@st.cache_data(ttl=300, show_spinner=False)
def cached_components_performance(tickers_str: str, period: str):
    tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
    return get_components_performance(tickers, period)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_upcoming_events(days: int = 14, country: str = "", impact: str = ""):
    return get_upcoming_events(days, country or None, impact or None)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_calendar_summary():
    return get_calendar_summary()

@st.cache_data(ttl=3600, show_spinner=False)
def cached_events_for_ticker(ticker: str, days: int = 7):
    return get_events_for_ticker(ticker, days)

@st.cache_data(ttl=300, show_spinner=False)
def cached_stock_history(ticker: str, period: str = "1y"):
    """Cached wrapper für get_history — liefert OHLCV DataFrame."""
    return get_history(ticker, period)

@st.cache_data(ttl=300, show_spinner=False)
def cached_options_overview(ticker: str, expiry: str = ""):
    return get_options_overview(ticker, expiry or None)

@st.cache_data(ttl=300, show_spinner=False)
def cached_equity_curve(_prices_hash: str = "", current_prices: dict = None):
    return calc_equity_curve(current_prices)

@st.cache_data(ttl=300, show_spinner=False)
def cached_performance_metrics(_prices_hash: str = "", current_prices: dict = None):
    return calc_performance_metrics(current_prices)

@st.cache_data(ttl=300, show_spinner=False)
def cached_sector_allocation(_prices_hash: str = "", current_prices: dict = None):
    return calc_sector_allocation(current_prices)

@st.cache_data(ttl=300, show_spinner=False)
def cached_risk_report(_prices_hash: str = "", current_prices: dict = None):
    return calc_full_risk_report(current_prices)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_signal_statistics():
    return get_signal_statistics()

@st.cache_data(ttl=3600, show_spinner=False)
def cached_hit_rate(days: int = 90):
    return calc_hit_rate(days)

@st.cache_data(ttl=3600, show_spinner=False)
def cached_calibration():
    return calc_calibration_chart()
