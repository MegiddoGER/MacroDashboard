"""
services/forex.py — Wechselkurs-Service für EUR-Konvertierung.

Alle Preise im MacroDashboard werden in EUR angezeigt.
Aktien werden von ihrer Heimatbörse gezogen (beste Datenqualität),
aber dann nach EUR umgerechnet.

Cache: 1 Stunde pro Währungspaar.
Fallback: Statische Rates bei API-Fehler.
"""

import warnings
import time
import yfinance as yf


# ---------------------------------------------------------------------------
# Fallback-Kurse (ungefähre Werte, falls API ausfällt)
# ---------------------------------------------------------------------------

_FALLBACK_RATES_TO_EUR = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.16,
    "CHF": 0.95,
    "DKK": 0.134,
    "SEK": 0.088,
    "NOK": 0.086,
    "JPY": 0.0062,
    "CAD": 0.68,
    "AUD": 0.60,
    "HKD": 0.118,
    "CNY": 0.127,
    "KRW": 0.00068,
    "INR": 0.011,
    "BRL": 0.16,
    "ILS": 0.25,
    "TWD": 0.029,
    "SGD": 0.69,
    "ZAR": 0.050,
    "MXN": 0.054,
    "PLN": 0.23,
    "CZK": 0.040,
    "HUF": 0.0026,
    "TRY": 0.027,
}


# ---------------------------------------------------------------------------
# Cache: {currency: (rate, timestamp)}
# ---------------------------------------------------------------------------

_rate_cache: dict[str, tuple[float, float]] = {}
_CACHE_TTL = 3600  # 1 Stunde


def get_rate_to_eur(currency: str) -> float:
    """Gibt den Umrechnungskurs einer Währung nach EUR zurück.

    Beispiele:
        get_rate_to_eur("USD") → 0.92  (1 USD = 0.92 EUR)
        get_rate_to_eur("EUR") → 1.0
        get_rate_to_eur("GBP") → 1.16  (1 GBP = 1.16 EUR)

    Cached für 1 Stunde. Fallback auf statische Rates bei Fehler.
    """
    currency = currency.upper().strip()

    if currency == "EUR":
        return 1.0

    # Cache prüfen
    now = time.time()
    cached = _rate_cache.get(currency)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    # Live-Rate holen via yfinance
    rate = _fetch_rate(currency)
    if rate is not None:
        _rate_cache[currency] = (rate, now)
        return rate

    # Fallback
    fallback = _FALLBACK_RATES_TO_EUR.get(currency, 1.0)
    warnings.warn(
        f"forex: Kein Live-Kurs für {currency}/EUR verfügbar, "
        f"verwende Fallback-Rate {fallback}"
    )
    return fallback


def _fetch_rate(currency: str) -> float | None:
    """Holt den Live-Wechselkurs via yfinance Forex-Pair.

    yfinance Forex-Pairs: EURUSD=X gibt den EUR/USD Kurs
    (d.h. wie viel USD man für 1 EUR bekommt).
    Wir brauchen den inversen: 1 USD → x EUR.
    """
    try:
        # Pair: {currency}EUR=X → gibt "1 {currency} = x EUR"
        pair = f"{currency}EUR=X"
        tk = yf.Ticker(pair)
        hist = tk.history(period="5d")

        if hist is not None and not hist.empty:
            rate = float(hist["Close"].dropna().iloc[-1])
            if 0.0001 < rate < 10000:  # Sanity-Check
                return rate

        # Alternativer Ansatz: EUR{currency}=X (invertiert)
        pair_inv = f"EUR{currency}=X"
        tk_inv = yf.Ticker(pair_inv)
        hist_inv = tk_inv.history(period="5d")

        if hist_inv is not None and not hist_inv.empty:
            rate_inv = float(hist_inv["Close"].dropna().iloc[-1])
            if rate_inv > 0:
                return 1.0 / rate_inv

    except Exception as exc:
        warnings.warn(f"forex._fetch_rate({currency}): {exc}")

    return None


def convert_to_eur(value: float | None, currency: str) -> float | None:
    """Rechnet einen Betrag von einer beliebigen Währung nach EUR um.

    Args:
        value: Betrag in Originalwährung (oder None)
        currency: ISO-Währungscode (z.B. "USD", "EUR", "GBP")

    Returns:
        Betrag in EUR, oder None wenn value None ist
    """
    if value is None:
        return None

    rate = get_rate_to_eur(currency)
    return value * rate


def get_fx_info(currency: str) -> dict:
    """Gibt Wechselkurs-Infos für die UI zurück.

    Returns:
        {"currency": "USD", "rate": 0.92, "is_eur": False, "label": "1 USD = 0.92 EUR"}
    """
    currency = currency.upper().strip()
    rate = get_rate_to_eur(currency)
    is_eur = currency == "EUR"

    return {
        "currency": currency,
        "rate": round(rate, 4),
        "is_eur": is_eur,
        "label": f"1 {currency} = {rate:.4f} EUR" if not is_eur else "EUR (keine Umrechnung)",
    }
