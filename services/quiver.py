"""
services/quiver.py — Quiver Quantitative API Client.

Primäre Datenquelle für:
- Institutionelle Holdings (13F Filings)
- Kongress-Trades (House + Senate)
- Corporate Insider Transaktionen

Auth: Bearer Token via Umgebungsvariable QUIVER_API_TOKEN.
Caching: TTLCache mit 30 Min TTL pro Ticker/Endpunkt.
Fehlerbehandlung: Gibt leere Listen zurück bei API-Fehlern, loggt Warnungen.
"""

import os
import warnings
import time
from datetime import datetime, timedelta
from cachetools import TTLCache
from threading import Lock

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

_BASE_URL = "https://api.quiverquant.com/beta"
_CACHE_TTL = 1800  # 30 Minuten
_REQUEST_DELAY = 0.3  # Sekunden zwischen Requests (Rate Limiting Schutz)

# Session-Cache: verhindert Re-Fetch bei Tab-Wechsel
_cache = TTLCache(maxsize=300, ttl=_CACHE_TTL)
_cache_lock = Lock()
_last_request_time = 0.0


def _get_token() -> str | None:
    """Liest den Quiver API Token: zuerst aus der DB (Settings-Seite), dann aus Umgebungsvariable."""
    try:
        from database import get_setting
        db_token = get_setting("QUIVER_API_TOKEN")
        if db_token:
            return db_token
    except Exception:
        pass
    return os.environ.get("QUIVER_API_TOKEN")


def _is_available() -> bool:
    """Prüft ob die Quiver API verfügbar ist (Token vorhanden)."""
    return bool(_get_token())


def _parse_amount_numeric(amount_str) -> float | None:
    """Parst den Betrag aus Kongress-Trades zu einem numerischen Wert.

    Unterstützt:
    - Exakte Werte: "150000", "$150,000", "150000.0"
    - Spannen: "$1,001 - $15,000" → Mittelwert (8000.5)
    - Textuelle Formen: "$1,001-$15,000"

    Returns:
        Float-Wert oder None bei Fehler.
    """
    if amount_str is None:
        return None
    if isinstance(amount_str, (int, float)):
        return float(amount_str)

    s = str(amount_str).strip()
    if not s or s == "—":
        return None

    import re

    # Entferne Dollarzeichen für sauberes Parsing
    s = s.replace("$", "").strip()

    # Finde Zahlen-Tokens: Erst Komma-Tausender (150,000), dann bare (150000)
    tokens = re.findall(r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)', s)

    if len(tokens) >= 2:
        # Spanne erkannt: "$X - $Y" → Mittelwert
        try:
            low = float(tokens[0].replace(",", ""))
            high = float(tokens[1].replace(",", ""))
            return (low + high) / 2.0
        except (ValueError, TypeError):
            pass

    if tokens:
        # Einzelner Wert
        try:
            return float(tokens[0].replace(",", ""))
        except (ValueError, TypeError):
            pass

    return None


# ---------------------------------------------------------------------------
# HTTP-Basis-Funktion
# ---------------------------------------------------------------------------

def _quiver_get(endpoint: str) -> list[dict]:
    """Führt einen GET-Request gegen die Quiver API aus.

    Args:
        endpoint: Relativer Pfad, z.B. '/live/institutional/AAPL'

    Returns:
        Liste von Dicts (JSON-Response) oder leere Liste bei Fehler.
    """
    global _last_request_time

    token = _get_token()
    if not token:
        return []

    url = f"{_BASE_URL}{endpoint}"

    # Rate Limiting: mindestens _REQUEST_DELAY zwischen Requests
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _REQUEST_DELAY:
        time.sleep(_REQUEST_DELAY - elapsed)

    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        # Retry-Logik: 1 Retry bei Timeout/5xx
        for attempt in range(2):
            try:
                _last_request_time = time.time()
                response = httpx.get(url, headers=headers, timeout=15.0)

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        # Manche Endpunkte wrappen Ergebnisse in ein Dict
                        return data.get("data", data.get("results", [data]))
                    return []

                elif response.status_code == 401:
                    warnings.warn("Quiver API: Ungültiger API-Token (401 Unauthorized)")
                    return []
                elif response.status_code == 403:
                    warnings.warn(f"Quiver API: Zugriff verweigert für {endpoint} (403 Forbidden — ggf. Premium erforderlich)")
                    return []
                elif response.status_code == 404:
                    # Kein Fehler — Ticker hat einfach keine Daten
                    return []
                elif response.status_code == 429:
                    warnings.warn("Quiver API: Rate Limit erreicht (429 Too Many Requests)")
                    if attempt == 0:
                        time.sleep(2.0)
                        continue
                    return []
                elif response.status_code >= 500:
                    if attempt == 0:
                        time.sleep(1.0)
                        continue
                    warnings.warn(f"Quiver API: Server-Fehler {response.status_code} für {endpoint}")
                    return []
                else:
                    warnings.warn(f"Quiver API: Unerwarteter Status {response.status_code} für {endpoint}")
                    return []

            except httpx.TimeoutException:
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                warnings.warn(f"Quiver API: Timeout für {endpoint}")
                return []

    except ImportError:
        warnings.warn("httpx nicht installiert — Quiver API nicht verfügbar. Installiere mit: pip install httpx")
        return []
    except Exception as exc:
        warnings.warn(f"Quiver API Fehler ({endpoint}): {exc}")
        return []

    return []


# ---------------------------------------------------------------------------
# Institutionelle Holdings (13F)
# ---------------------------------------------------------------------------

def get_quiver_institutional(ticker: str) -> list[dict]:
    """Lädt institutionelle Holdings von Quiver (/live/institutional/{ticker}).

    Erfasst ALLE institutionellen Inhaber, sortiert nach Positionsgröße absteigend.

    Returns:
        Liste von Dicts mit Feldern:
        - institution: str (Name)
        - shares: int (Anzahl Aktien)
        - value: float (Wert in USD)
        - shares_change: int (Veränderung zur Vorperiode)
        - shares_change_pct: float (Veränderung in %)
        - date: str (Datum des letzten Filings, formatiert)
    """
    cache_key = f"institutional_{ticker.upper()}"
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]

    raw = _quiver_get(f"/live/institutional/{ticker}")
    if not raw:
        return []

    result = []
    for item in raw:
        try:
            # TODO: verify — Feldnamen der Quiver API prüfen
            institution = item.get("Name") or item.get("Investor") or item.get("InstitutionName") or "Unbekannt"
            shares = _safe_int(item.get("Shares") or item.get("shares"))
            value = _safe_float(item.get("Value") or item.get("value") or item.get("MarketValue"))

            # Veränderung zur Vorperiode
            shares_change = _safe_int(item.get("SharesChange") or item.get("Change") or item.get("change"))
            shares_change_pct = _safe_float(item.get("SharesChangePercent") or item.get("ChangePercent"))

            # Datum
            date_raw = item.get("Date") or item.get("date") or item.get("ReportDate")
            date_formatted = _format_date(date_raw)

            result.append({
                "institution": institution,
                "shares": shares or 0,
                "value": value or 0.0,
                "shares_change": shares_change or 0,
                "shares_change_pct": shares_change_pct,
                "date": date_formatted,
            })
        except Exception:
            continue

    # Sortierung: nach Positionsgröße absteigend
    result.sort(key=lambda x: x.get("shares", 0), reverse=True)

    with _cache_lock:
        _cache[cache_key] = result

    return result


# ---------------------------------------------------------------------------
# Kongress-Trades
# ---------------------------------------------------------------------------

def get_quiver_congress_trades(ticker: str) -> list[dict]:
    """Lädt Kongress-Trades von Quiver (/live/congresstrading/{ticker}).

    Returns:
        Liste von Dicts mit Feldern:
        - name: str (Name des Politikers)
        - chamber: str ('Senate' oder 'House')
        - party: str ('Republican', 'Democrat', etc.)
        - trade_type: str ('Purchase' oder 'Sale')
        - amount: str (Betragsbereich, z.B. '$1,001 - $15,000')
        - trade_date: str (formatiert)
        - disclosure_date: str (formatiert)
        - disclosure_lag: int (Tage zwischen Trade und Disclosure)
    """
    cache_key = f"congress_{ticker.upper()}"
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]

    raw = _quiver_get(f"/live/congresstrading/{ticker}")
    if not raw:
        return []

    result = []
    for item in raw:
        try:
            # TODO: verify — Feldnamen der Quiver API prüfen
            name = item.get("Representative") or item.get("Name") or item.get("name") or "Unbekannt"
            chamber = item.get("House") or item.get("Chamber") or item.get("house") or "—"
            party = item.get("Party") or item.get("party") or "—"

            # Trade-Typ normalisieren
            tx_type_raw = item.get("Transaction") or item.get("Type") or item.get("type") or ""
            trade_type = _normalize_trade_type(tx_type_raw)

            amount = item.get("Amount") or item.get("Range") or item.get("amount") or "—"

            # Daten
            trade_date_raw = item.get("TransactionDate") or item.get("TradeDate") or item.get("Date")
            disclosure_date_raw = item.get("DisclosureDate") or item.get("ReportDate")

            trade_date = _format_date(trade_date_raw)
            disclosure_date = _format_date(disclosure_date_raw)

            # Disclosure-Lag berechnen
            disclosure_lag = _calc_day_diff(trade_date_raw, disclosure_date_raw)

            result.append({
                "name": name,
                "chamber": chamber,
                "party": party,
                "trade_type": trade_type,
                "amount": amount,
                "trade_date": trade_date,
                "disclosure_date": disclosure_date,
                "disclosure_lag": disclosure_lag,
            })
        except Exception:
            continue

    # Sortierung: neueste zuerst
    result.sort(key=lambda x: x.get("trade_date", ""), reverse=True)

    with _cache_lock:
        _cache[cache_key] = result

    return result


# ---------------------------------------------------------------------------
# Corporate Insider Trades
# ---------------------------------------------------------------------------

def get_quiver_insider_trades(ticker: str) -> list[dict]:
    """Lädt Corporate Insider Trades von Quiver (/live/insiders/{ticker}).

    Returns:
        Tuple von (trades: list[dict], sentiment: dict)
        trades: Liste von Dicts mit Feldern:
        - name: str
        - role: str (CEO, CFO, Director, etc.)
        - trade_type: str ('Purchase', 'Sale', 'Sale (10b5-1)')
        - shares: int
        - value: float
        - date: str (formatiert)
        - is_plan_trade: bool (Rule 10b5-1)

        sentiment: Dict mit:
        - buys_count: int (Käufe letzte 90 Tage)
        - sells_count: int (Verkäufe letzte 90 Tage)
        - buy_value: float
        - sell_value: float
        - net_value: float (buy_value - sell_value)
        - net_shares: int
    """
    cache_key = f"insiders_{ticker.upper()}"
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]

    raw = _quiver_get(f"/live/insiders/{ticker}")
    if not raw:
        return [], _empty_sentiment()

    trades = []
    # Für 90-Tage-Sentiment
    cutoff_90d = datetime.now() - timedelta(days=90)
    buys_count, sells_count = 0, 0
    buy_value, sell_value = 0.0, 0.0
    buy_shares, sell_shares = 0, 0

    for item in raw:
        try:
            # TODO: verify — Feldnamen der Quiver API prüfen
            name = item.get("Name") or item.get("Insider") or item.get("name") or "Unbekannt"
            role = item.get("Title") or item.get("Role") or item.get("Position") or "—"

            tx_raw = item.get("TransactionType") or item.get("Transaction") or item.get("Type") or ""
            is_plan = _is_10b5_1(tx_raw)
            trade_type = _classify_insider_trade(tx_raw, is_plan)

            shares = _safe_int(item.get("Shares") or item.get("shares"))
            value = _safe_float(item.get("Value") or item.get("value"))
            date_raw = item.get("Date") or item.get("date") or item.get("FilingDate")
            date_formatted = _format_date(date_raw)

            trade = {
                "name": name,
                "role": role,
                "trade_type": trade_type,
                "shares": shares or 0,
                "value": value or 0.0,
                "date": date_formatted,
                "is_plan_trade": is_plan,
            }
            trades.append(trade)

            # 90-Tage-Sentiment berechnen
            trade_dt = _parse_date(date_raw)
            if trade_dt and trade_dt >= cutoff_90d:
                if "purchase" in trade_type.lower() or "buy" in trade_type.lower():
                    buys_count += 1
                    buy_value += abs(value or 0)
                    buy_shares += abs(shares or 0)
                elif "sale" in trade_type.lower() or "sell" in trade_type.lower():
                    sells_count += 1
                    sell_value += abs(value or 0)
                    sell_shares += abs(shares or 0)

        except Exception:
            continue

    # Sortierung: neueste zuerst
    trades.sort(key=lambda x: x.get("date", ""), reverse=True)

    sentiment = {
        "buys_count": buys_count,
        "sells_count": sells_count,
        "buy_value": buy_value,
        "sell_value": sell_value,
        "net_value": buy_value - sell_value,
        "net_shares": buy_shares - sell_shares,
    }

    result = (trades, sentiment)
    with _cache_lock:
        _cache[cache_key] = result

    return result


def _empty_sentiment() -> dict:
    """Leeres Sentiment-Dict als Fallback."""
    return {
        "buys_count": 0, "sells_count": 0,
        "buy_value": 0.0, "sell_value": 0.0,
        "net_value": 0.0, "net_shares": 0,
    }


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _safe_int(val) -> int | None:
    """Konvertiert zu int, gibt None bei Fehler zurück."""
    if val is None:
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _safe_float(val) -> float | None:
    """Konvertiert zu float, gibt None bei Fehler zurück."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_date(date_str) -> datetime | None:
    """Versucht ein Datum zu parsen (multiple Formate)."""
    if date_str is None:
        return None
    if isinstance(date_str, datetime):
        return date_str

    date_str = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except (ValueError, IndexError):
            continue
    return None


def _format_date(date_str) -> str:
    """Formatiert ein Datum als dd.mm.yyyy."""
    dt = _parse_date(date_str)
    if dt:
        return dt.strftime("%d.%m.%Y")
    return str(date_str) if date_str else "—"


def _calc_day_diff(date1_str, date2_str) -> int | None:
    """Berechnet die Differenz in Tagen zwischen zwei Daten."""
    d1 = _parse_date(date1_str)
    d2 = _parse_date(date2_str)
    if d1 and d2:
        return abs((d2 - d1).days)
    return None


def _normalize_trade_type(raw: str) -> str:
    """Normalisiert den Trade-Typ für Kongress-Trades."""
    lower = raw.lower().strip()
    if "purchase" in lower or "buy" in lower:
        return "Purchase"
    elif "sale" in lower or "sell" in lower:
        if "partial" in lower:
            return "Sale (Partial)"
        return "Sale"
    elif "exchange" in lower:
        return "Exchange"
    return raw or "—"


def _classify_insider_trade(raw: str, is_plan: bool) -> str:
    """Klassifiziert einen Insider-Trade-Typ."""
    lower = raw.lower().strip()
    if is_plan:
        if "purchase" in lower or "buy" in lower:
            return "Purchase (10b5-1)"
        return "Sale (10b5-1)"
    if "purchase" in lower or "buy" in lower:
        return "Purchase"
    if "sale" in lower or "sell" in lower or "disposition" in lower:
        return "Sale"
    if "option" in lower or "exercise" in lower:
        return "Option Exercise"
    if "gift" in lower:
        return "Gift"
    return raw or "—"


def _is_10b5_1(raw: str) -> bool:
    """Prüft ob ein Trade unter Rule 10b5-1 Plan erfolgte."""
    if not raw:
        return False
    lower = raw.lower()
    return "10b5" in lower or "10b-5" in lower or "rule 10b" in lower or "plan" in lower
