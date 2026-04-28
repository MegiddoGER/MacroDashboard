"""
services/cache_core.py — Framework-agnostischer Cache-Layer.

Ersetzt services/cache.py mit cachetools.TTLCache statt @st.cache_data.
Alle bestehenden Service-Funktionen werden identisch gecacht.
"""

from cachetools import TTLCache, cached
from threading import Lock

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


# ---------------------------------------------------------------------------
# Cache-Instanzen
# ---------------------------------------------------------------------------

_lock = Lock()

# Kurzlebige Caches (5 Min bei offenem Markt)
_quote_cache = TTLCache(maxsize=500, ttl=300)
_history_cache = TTLCache(maxsize=200, ttl=300)
_multi_cache = TTLCache(maxsize=100, ttl=300)
_details_cache = TTLCache(maxsize=100, ttl=300)
_yield_cache = TTLCache(maxsize=10, ttl=300)
_sectors_cache = TTLCache(maxsize=50, ttl=300)
_options_cache = TTLCache(maxsize=50, ttl=300)
_corr_cache = TTLCache(maxsize=50, ttl=300)
_history_period_cache = TTLCache(maxsize=200, ttl=300)

# Langlebige Caches (30 Min - 24h)
_vix_cache = TTLCache(maxsize=10, ttl=300)
_sp500_series_cache = TTLCache(maxsize=10, ttl=300)
_gold_cache = TTLCache(maxsize=10, ttl=300)
_inflation_cache = TTLCache(maxsize=10, ttl=300)
_listings_cache = TTLCache(maxsize=5, ttl=3600)
_sp500_components_cache = TTLCache(maxsize=5, ttl=86400)

# News / Kalender
_regional_news_cache = TTLCache(maxsize=20, ttl=600)
_company_news_cache = TTLCache(maxsize=100, ttl=600)
_earnings_cache = TTLCache(maxsize=50, ttl=600)
_events_cache = TTLCache(maxsize=50, ttl=3600)
_calendar_summary_cache = TTLCache(maxsize=5, ttl=3600)
_ticker_events_cache = TTLCache(maxsize=100, ttl=3600)

# Portfolio / Risk / Signals
_equity_cache = TTLCache(maxsize=20, ttl=300)
_perf_cache = TTLCache(maxsize=20, ttl=300)
_sector_alloc_cache = TTLCache(maxsize=20, ttl=300)
_risk_cache = TTLCache(maxsize=20, ttl=300)
_signal_stats_cache = TTLCache(maxsize=5, ttl=3600)
_hit_rate_cache = TTLCache(maxsize=10, ttl=3600)
_calibration_cache = TTLCache(maxsize=5, ttl=3600)
_components_perf_cache = TTLCache(maxsize=50, ttl=300)


# ---------------------------------------------------------------------------
# Cached Wrappers (identische API wie der alte services/cache.py)
# ---------------------------------------------------------------------------

@cached(_quote_cache, lock=_lock)
def cached_quote(ticker: str):
    return get_quote(ticker)


@cached(_history_cache, lock=_lock)
def cached_history(ticker: str, period: str = "1y"):
    return get_history(ticker, period)


@cached(_yield_cache, lock=_lock)
def cached_yield_spread():
    return get_yield_spread()


def cached_vix():
    key = "vix"
    if key in _vix_cache:
        return _vix_cache[key]
    val = get_vix_value()
    _vix_cache[key] = val
    return val


def cached_sp500():
    key = "sp500"
    if key in _sp500_series_cache:
        return _sp500_series_cache[key]
    val = get_sp500_close_series()
    _sp500_series_cache[key] = val
    return val


@cached(_multi_cache, lock=_lock)
def cached_multi(tickers_str: str):
    tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
    return get_multi_quotes(tickers)


@cached(_details_cache, lock=_lock)
def cached_stock_details(ticker: str):
    return get_stock_details(ticker)


def cached_gold():
    key = "gold"
    if key in _gold_cache:
        return _gold_cache[key]
    val = get_gold_close_series()
    _gold_cache[key] = val
    return val


@cached(_inflation_cache, lock=_lock)
def cached_inflation():
    return get_german_inflation()


@cached(_listings_cache, lock=_lock)
def cached_listings():
    return get_stock_listings()


@cached(_corr_cache, lock=_lock)
def cached_correlation(tickers_str: str, labels_str: str, period: str = "1y"):
    tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
    labels = [l.strip() for l in labels_str.split(",") if l.strip()] if labels_str else None
    return get_correlation_matrix(tickers, labels, period)


@cached(_sectors_cache, lock=_lock)
def cached_sectors(period: str = "1d", region: str = "us"):
    return get_sector_performance(period, region)


@cached(_regional_news_cache, lock=_lock)
def cached_regional_news(region: str):
    return get_regional_news(region)


@cached(_company_news_cache, lock=_lock)
def cached_company_news(ticker: str):
    return get_company_news(ticker)


@cached(_earnings_cache, lock=_lock)
def cached_earnings(tickers_str: str, names_str: str):
    tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
    name_pairs = [p.split("=", 1) for p in names_str.split(",") if "=" in p]
    names = {k.strip(): v.strip() for k, v in name_pairs}
    return get_earnings_dates(tickers, names)


@cached(_sp500_components_cache, lock=_lock)
def cached_sp500_components():
    return get_sp500_components()


@cached(_components_perf_cache, lock=_lock)
def cached_components_performance(tickers_str: str, period: str):
    tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
    return get_components_performance(tickers, period)


@cached(_events_cache, lock=_lock)
def cached_upcoming_events(days: int = 14, country: str = "", impact: str = ""):
    return get_upcoming_events(days, country or None, impact or None)


@cached(_calendar_summary_cache, lock=_lock)
def cached_calendar_summary():
    return get_calendar_summary()


@cached(_ticker_events_cache, lock=_lock)
def cached_events_for_ticker(ticker: str, days: int = 7):
    return get_events_for_ticker(ticker, days)


@cached(_history_period_cache, lock=_lock)
def cached_stock_history(ticker: str, period: str = "1y"):
    """Cached wrapper für get_history — liefert OHLCV DataFrame."""
    return get_history(ticker, period)


@cached(_options_cache, lock=_lock)
def cached_options_overview(ticker: str, expiry: str = ""):
    return get_options_overview(ticker, expiry or None)


def cached_equity_curve(_prices_hash: str = "", current_prices: dict = None):
    key = _prices_hash or "default"
    if key in _equity_cache:
        return _equity_cache[key]
    val = calc_equity_curve(current_prices)
    _equity_cache[key] = val
    return val


def cached_performance_metrics(_prices_hash: str = "", current_prices: dict = None):
    key = _prices_hash or "default"
    if key in _perf_cache:
        return _perf_cache[key]
    val = calc_performance_metrics(current_prices)
    _perf_cache[key] = val
    return val


def cached_sector_allocation(_prices_hash: str = "", current_prices: dict = None):
    key = _prices_hash or "default"
    if key in _sector_alloc_cache:
        return _sector_alloc_cache[key]
    val = calc_sector_allocation(current_prices)
    _sector_alloc_cache[key] = val
    return val


def cached_risk_report(_prices_hash: str = "", current_prices: dict = None):
    key = _prices_hash or "default"
    if key in _risk_cache:
        return _risk_cache[key]
    val = calc_full_risk_report(current_prices)
    _risk_cache[key] = val
    return val


@cached(_signal_stats_cache, lock=_lock)
def cached_signal_statistics():
    return get_signal_statistics()


@cached(_hit_rate_cache, lock=_lock)
def cached_hit_rate(days: int = 90):
    return calc_hit_rate(days)


@cached(_calibration_cache, lock=_lock)
def cached_calibration():
    return calc_calibration_chart()


# ---------------------------------------------------------------------------
# Cache Management
# ---------------------------------------------------------------------------

def clear_all_caches():
    """Leert alle Cache-Instanzen (z.B. bei 'Alle Daten Aktualisieren')."""
    for cache in [
        _quote_cache, _history_cache, _multi_cache, _details_cache,
        _yield_cache, _vix_cache, _sp500_series_cache, _gold_cache,
        _inflation_cache, _listings_cache, _sectors_cache, _options_cache,
        _corr_cache, _regional_news_cache, _company_news_cache,
        _earnings_cache, _sp500_components_cache, _events_cache,
        _calendar_summary_cache, _ticker_events_cache, _history_period_cache,
        _equity_cache, _perf_cache, _sector_alloc_cache, _risk_cache,
        _signal_stats_cache, _hit_rate_cache, _calibration_cache,
        _components_perf_cache,
    ]:
        cache.clear()
