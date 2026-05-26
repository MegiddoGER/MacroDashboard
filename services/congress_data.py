"""
services/congress_data.py — Kostenloser Kongress-Trading-Client.

Datenquelle: Kadoa Congress Trading Monitor (GitHub)
URL: https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/main/public/data/trades.json

Kein API-Token nötig. Daten werden täglich vom Kadoa-Projekt aktualisiert
basierend auf offiziellen STOCK Act Disclosures (House Clerk + Senate eFD).
"""

import warnings
import time
import httpx
from datetime import datetime, timedelta
from threading import Lock

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

_DATA_URL = (
    "https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor"
    "/main/public/data/trades.json"
)
_CACHE_TTL = 1800  # 30 Minuten — die Daten ändern sich nur täglich
_TIMEOUT = 15  # HTTP Timeout in Sekunden

# Globaler Cache: Einmal laden, dann für alle Ticker filtern
_cache: dict = {"data": None, "timestamp": 0}
_cache_lock = Lock()


# ---------------------------------------------------------------------------
# Daten laden
# ---------------------------------------------------------------------------

def _load_all_trades() -> list[dict]:
    """Lädt alle Kongress-Trades aus dem Kadoa GitHub Repository.

    Die gesamte JSON-Datei (~280KB) wird einmalig geladen und gecached.
    Nachfolgende Aufrufe für verschiedene Ticker filtern nur noch im RAM.
    """
    now = time.time()

    with _cache_lock:
        if _cache["data"] is not None and (now - _cache["timestamp"]) < _CACHE_TTL:
            return _cache["data"]

    try:
        resp = httpx.get(
            _DATA_URL,
            timeout=_TIMEOUT,
            headers={"User-Agent": "MacroDashboard/1.0"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        all_trades = resp.json()

        if not isinstance(all_trades, list):
            warnings.warn("congress_data: Unerwartetes Datenformat (kein Array)")
            return []

        with _cache_lock:
            _cache["data"] = all_trades
            _cache["timestamp"] = now

        return all_trades

    except Exception as exc:
        warnings.warn(f"congress_data: Fehler beim Laden der Kadoa-Daten: {exc}")
        # Veraltete Daten zurückgeben, falls vorhanden
        with _cache_lock:
            if _cache["data"] is not None:
                return _cache["data"]
        return []


def fetch_congress_trades(ticker: str, days: int = 365) -> list[dict]:
    """Filtert Kongress-Trades für einen bestimmten Ticker.

    Args:
        ticker: Aktienticker (z.B. "NVDA", "AAPL")
        days: Nur Trades der letzten N Tage (Standard: 365)

    Returns:
        Liste von normalisierten Trade-Dicts, kompatibel mit dem Scoring-System.
        Felder pro Trade:
        - name: Politikername
        - trade_type: "Purchase" oder "Sale"
        - disclosure_lag: Tage zwischen Trade und Filing
        - amount_low: Untere Betragsgrenze ($)
        - amount_high: Obere Betragsgrenze ($)
        - amount_label: Lesbare Spanne (z.B. "$1,001 - $15,000")
        - transaction_date, filing_date: ISO-Datum-Strings
        - party, chamber, state, office
        - doc_url: Link zum PDF-Beleg
    """
    if not ticker:
        return []

    ticker_upper = ticker.upper().strip()
    all_trades = _load_all_trades()

    if not all_trades:
        return []

    # Zeitfenster
    cutoff = datetime.now() - timedelta(days=days)

    results = []
    for t in all_trades:
        # Ticker-Filter (exakt)
        t_ticker = (t.get("ticker") or "").upper().strip()
        if t_ticker != ticker_upper:
            continue

        # Nur Aktien-Trades: House="ST", Senate="Stock", manche=None
        asset_type = t.get("asset_type")
        if asset_type and asset_type not in ("ST", "Stock"):
            continue

        # Datums-Filter
        tx_date_str = t.get("transaction_date")
        if tx_date_str:
            try:
                tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d")
                if tx_date < cutoff:
                    continue
            except (ValueError, TypeError):
                pass

        # Normalisierung: Kadoa-Felder → Scoring-kompatible Felder
        trade_type_raw = (t.get("transaction_type") or "").strip()
        if "purchase" in trade_type_raw.lower() or "buy" in trade_type_raw.lower():
            normalized_type = "Purchase"
        elif "sale" in trade_type_raw.lower() or "sell" in trade_type_raw.lower():
            normalized_type = "Sale"
        else:
            normalized_type = trade_type_raw  # Exchange, etc.

        results.append({
            "name": t.get("filer_name", "Unbekannt"),
            "trade_type": normalized_type,
            "disclosure_lag": t.get("days_to_file"),  # Kadoa berechnet das bereits!
            "amount_low": t.get("amount_range_low"),
            "amount_high": t.get("amount_range_high"),
            "amount_label": t.get("amount_range_label", "—"),
            "transaction_date": t.get("transaction_date"),
            "filing_date": t.get("filing_date"),
            "party": t.get("party"),
            "chamber": t.get("chamber"),
            "state": t.get("state"),
            "office": t.get("office"),
            "doc_url": t.get("doc_url"),
            "is_late": bool(t.get("is_late")),
        })

    # Sortierung: Neueste zuerst
    results.sort(key=lambda x: x.get("transaction_date") or "", reverse=True)

    return results


def is_available() -> bool:
    """Kongress-Daten sind immer verfügbar (kein Token nötig)."""
    return True
