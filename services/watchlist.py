"""
watchlist.py — Persistente Watchlist mit Xetra-Priorisierung & Positions-Tracking.

Speichert die Watchlist als JSON-Datei im Projektverzeichnis.
Sucht Aktien per US-Ticker oder Firmenname und löst automatisch
zum Xetra-Ticker (.DE) auf, damit die Kurse in EUR angezeigt werden.

Positions-Tracking: Speichert Kauf-/Verkaufsdaten, Stückzahl, Stop-Loss,
Take-Profit und berechnet realisierte/unrealisierte P&L.
"""

import csv
import json
import os
import uuid
import warnings
from datetime import datetime
import yfinance as yf

# Pfad zur Watchlist-Datei (im data/ Verzeichnis des Projekts)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_WATCHLIST_FILE = os.path.join(_DATA_DIR, "watchlist.json")
_XETRA_CSV = os.path.join(_DATA_DIR, "xetra_stocks.csv")


# ---------------------------------------------------------------------------
# Xetra-CSV laden (lokaler Cache)
# ---------------------------------------------------------------------------

_xetra_cache: list[dict] | None = None


def _load_xetra_csv() -> list[dict]:
    """Lädt die lokale Xetra-CSV mit Kürzel, Name, Index.

    Rückgabe: Liste von {"ticker": str, "name": str, "index": str}
    """
    global _xetra_cache
    if _xetra_cache is not None:
        return _xetra_cache

    if not os.path.exists(_XETRA_CSV):
        _xetra_cache = []
        return _xetra_cache

    try:
        entries = []
        with open(_XETRA_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get("Kürzel", "").strip()
                name = row.get("Name", "").strip()
                index = row.get("Index", "").strip()
                if ticker and name:
                    entries.append({"ticker": ticker, "name": name, "index": index})
        _xetra_cache = entries
    except Exception:
        _xetra_cache = []
    return _xetra_cache


def _search_xetra_csv(query: str) -> list[dict]:
    """Sucht in der Xetra-CSV nach Ticker oder Firmenname.

    Rückgabe: Liste von {"ticker": str, "name": str}, sortiert nach Relevanz.
    Gibt ALLE Matches zurück, damit bei Validierung Alternativen getestet werden.
    """
    entries = _load_xetra_csv()
    q = query.strip()
    if not q:
        return []

    q_upper = q.upper()
    results = []
    seen = set()

    # 1. Exakter Ticker-Match (mit und ohne .DE)
    q_de = q_upper if q_upper.endswith(".DE") else q_upper + ".DE"
    for e in entries:
        if e["ticker"].upper() == q_de and e["ticker"] not in seen:
            results.append({"ticker": e["ticker"], "name": e["name"]})
            seen.add(e["ticker"])

    # 2. Exakter Ticker ohne .DE prüfen (z.B. "SAP" → "SAP.DE")
    for e in entries:
        base = e["ticker"].upper().replace(".DE", "")
        if base == q_upper and e["ticker"] not in seen:
            results.append({"ticker": e["ticker"], "name": e["name"]})
            seen.add(e["ticker"])

    # 3. Namenssuche (case-insensitive, enthält)
    q_lower = q.lower()
    name_matches = []
    for e in entries:
        name_lower = e["name"].lower()
        if q_lower in name_lower and e["ticker"] not in seen:
            score = len(q_lower) / len(name_lower)
            name_matches.append((score, e))
            seen.add(e["ticker"])

    # Sortiere nach Relevanz (höchster Score zuerst)
    name_matches.sort(key=lambda x: x[0], reverse=True)
    for _, e in name_matches:
        results.append({"ticker": e["ticker"], "name": e["name"]})

    return results


# ---------------------------------------------------------------------------
# Persistenz
# ---------------------------------------------------------------------------

def load_watchlist() -> list[dict]:
    """Liest die Watchlist aus der JSON-Datei.

    Rückgabe: Liste von {"ticker": str, "name": str, "display": str, "status": str, "positions": list}
    Migriert automatisch alte Einträge ohne positions-Feld.
    """
    if not os.path.exists(_WATCHLIST_FILE):
        return []
    try:
        with open(_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            migrated = False
            for item in data:
                if "display" not in item:
                    t = item.get("ticker", "")
                    item["display"] = t.replace(".DE", "") if t.endswith(".DE") else t
                    migrated = True
                if "status" not in item:
                    item["status"] = "Beobachtet"
                    migrated = True
                elif item["status"] == "Watchlist":
                    item["status"] = "Beobachtet"
                    migrated = True
                # Migration: positions-Feld hinzufügen falls nicht vorhanden
                if "positions" not in item:
                    item["positions"] = []
                    migrated = True
            if migrated:
                save_watchlist(data)
            return data
        return []
    except (json.JSONDecodeError, Exception):
        return []


def save_watchlist(watchlist: list[dict]) -> None:
    """Speichert die Watchlist in die JSON-Datei."""
    try:
        with open(_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        warnings.warn(f"Watchlist konnte nicht gespeichert werden: {exc}")


def add_to_watchlist(ticker: str, name: str, display: str = "",
                     status: str = "Beobachtet") -> list[dict]:
    """Fügt einen Ticker zur Watchlist hinzu (keine Duplikate)."""
    wl = load_watchlist()
    existing_tickers = {item["ticker"].upper() for item in wl}
    if ticker.upper() not in existing_tickers:
        if not display:
            display = ticker.replace(".DE", "") if ticker.endswith(".DE") else ticker
        wl.append({"ticker": ticker.upper(), "name": name,
                   "display": display.upper(), "status": status})
        save_watchlist(wl)
    return wl


def update_status(ticker: str, new_status: str) -> None:
    """Ändert den Status eines Watchlist-Eintrags."""
    wl = load_watchlist()
    for item in wl:
        if item["ticker"].upper() == ticker.upper():
            item["status"] = new_status
            break
    save_watchlist(wl)


def remove_from_watchlist(ticker: str) -> list[dict]:
    """Entfernt einen Ticker aus der Watchlist."""
    wl = load_watchlist()
    wl = [item for item in wl if item["ticker"].upper() != ticker.upper()]
    save_watchlist(wl)
    return wl


def get_ticker_list() -> list[str]:
    """Gibt nur die Ticker-Symbole als Liste zurück (Xetra-Ticker)."""
    return [item["ticker"] for item in load_watchlist()]


def get_display_map() -> dict[str, str]:
    """Gibt ein Mapping von Ticker → Display-Name zurück."""
    return {item["ticker"]: item.get("display", item["ticker"])
            for item in load_watchlist()}


# ---------------------------------------------------------------------------
# Positions-Management (Kauf/Verkauf Tracking)
# ---------------------------------------------------------------------------

def _new_position_id() -> str:
    """Generiert eine eindeutige Position-ID."""
    return uuid.uuid4().hex[:8]


def add_position(ticker: str, buy_price: float, quantity: float,
                 buy_date: str = None, stop_loss: float = None,
                 take_profit: float = None, fees: float = 0.0,
                 notes: str = "") -> dict | None:
    """Fügt eine neue Position zu einem Watchlist-Eintrag hinzu.

    Args:
        ticker: Watchlist-Ticker
        buy_price: Einkaufspreis pro Aktie
        quantity: Anzahl Aktien
        buy_date: Kaufdatum (ISO-Format, z.B. '2024-01-15'). Default: heute.
        stop_loss: Stop-Loss Kurs (optional)
        take_profit: Take-Profit Kurs (optional)
        fees: Gebühren in EUR (optional)
        notes: Notizen zum Trade (optional)

    Rückgabe: Die erstellte Position als dict, oder None bei Fehler.
    """
    wl = load_watchlist()
    for item in wl:
        if item["ticker"].upper() == ticker.upper():
            if "positions" not in item:
                item["positions"] = []

            position = {
                "id": _new_position_id(),
                "buy_date": buy_date or datetime.now().strftime("%Y-%m-%d"),
                "buy_price": round(buy_price, 2),
                "quantity": round(quantity, 4),
                "stop_loss": round(stop_loss, 2) if stop_loss else None,
                "take_profit": round(take_profit, 2) if take_profit else None,
                "fees": round(fees, 2),
                "notes": notes,
                "sell_date": None,
                "sell_price": None,
                "sell_fees": 0.0,
            }
            item["positions"].append(position)

            # Status automatisch auf "Investiert" setzen
            item["status"] = "Investiert"
            save_watchlist(wl)
            return position
    return None


def close_position(ticker: str, position_id: str, sell_price: float,
                   sell_date: str = None, sell_fees: float = 0.0) -> dict | None:
    """Schließt eine offene Position (Verkauf).

    Rückgabe: Die geschlossene Position als dict, oder None bei Fehler.
    """
    wl = load_watchlist()
    for item in wl:
        if item["ticker"].upper() == ticker.upper():
            for pos in item.get("positions", []):
                if pos.get("id") == position_id and pos.get("sell_date") is None:
                    pos["sell_date"] = sell_date or datetime.now().strftime("%Y-%m-%d")
                    pos["sell_price"] = round(sell_price, 2)
                    pos["sell_fees"] = round(sell_fees, 2)
                    # Prüfe ob noch offene Positionen existieren
                    open_positions = [p for p in item["positions"] if p.get("sell_date") is None]
                    if not open_positions:
                        item["status"] = "Beobachtet"
                    save_watchlist(wl)
                    return pos
    return None


def update_position(ticker: str, position_id: str, **kwargs) -> dict | None:
    """Aktualisiert Felder einer offenen Position (z.B. Stop-Loss, Take-Profit).

    Erlaubte kwargs: stop_loss, take_profit, notes, quantity
    Rückgabe: Die aktualisierte Position, oder None bei Fehler.
    """
    allowed_fields = {"stop_loss", "take_profit", "notes", "quantity"}
    wl = load_watchlist()
    for item in wl:
        if item["ticker"].upper() == ticker.upper():
            for pos in item.get("positions", []):
                if pos.get("id") == position_id:
                    for key, value in kwargs.items():
                        if key in allowed_fields:
                            if key in ("stop_loss", "take_profit") and value is not None:
                                value = round(value, 2)
                            elif key == "quantity" and value is not None:
                                value = round(value, 4)
                            pos[key] = value
                    save_watchlist(wl)
                    return pos
    return None


def delete_position(ticker: str, position_id: str) -> bool:
    """Löscht eine Position komplett (z.B. fehlerhafte Eingabe).

    Rückgabe: True wenn gelöscht, False wenn nicht gefunden.
    """
    wl = load_watchlist()
    for item in wl:
        if item["ticker"].upper() == ticker.upper():
            before = len(item.get("positions", []))
            item["positions"] = [p for p in item.get("positions", [])
                                 if p.get("id") != position_id]
            if len(item["positions"]) < before:
                # Status aktualisieren
                open_positions = [p for p in item["positions"] if p.get("sell_date") is None]
                if not open_positions:
                    item["status"] = "Beobachtet"
                save_watchlist(wl)
                return True
    return False


def get_open_positions(ticker: str = None) -> list[dict]:
    """Gibt alle offenen (nicht verkauften) Positionen zurück.

    Args:
        ticker: Optional. Nur Positionen für diesen Ticker.
                Wenn None, werden ALLE offenen Positionen zurückgegeben.

    Rückgabe: Liste von dicts mit {ticker, name, display, position}.
    """
    wl = load_watchlist()
    results = []
    for item in wl:
        if ticker and item["ticker"].upper() != ticker.upper():
            continue
        for pos in item.get("positions", []):
            if pos.get("sell_date") is None:
                results.append({
                    "ticker": item["ticker"],
                    "name": item["name"],
                    "display": item.get("display", item["ticker"]),
                    "position": pos,
                })
    return results


def get_closed_positions(ticker: str = None) -> list[dict]:
    """Gibt alle geschlossenen (verkauften) Positionen zurück."""
    wl = load_watchlist()
    results = []
    for item in wl:
        if ticker and item["ticker"].upper() != ticker.upper():
            continue
        for pos in item.get("positions", []):
            if pos.get("sell_date") is not None:
                results.append({
                    "ticker": item["ticker"],
                    "name": item["name"],
                    "display": item.get("display", item["ticker"]),
                    "position": pos,
                })
    return results


def calc_position_pnl(position: dict, current_price: float = None) -> dict:
    """Berechnet P&L für eine einzelne Position.

    Für offene Positionen: Unrealisierter P&L basierend auf current_price.
    Für geschlossene Positionen: Realisierter P&L basierend auf sell_price.

    Rückgabe: dict mit pnl_eur, pnl_pct, invested, current_value, is_closed.
    """
    buy_price = position.get("buy_price", 0)
    quantity = position.get("quantity", 0)
    fees = position.get("fees", 0)
    sell_fees = position.get("sell_fees", 0)
    invested = buy_price * quantity + fees

    if position.get("sell_date") is not None:
        # Geschlossene Position: realisierter P&L
        sell_price = position.get("sell_price", 0)
        current_value = sell_price * quantity - sell_fees
        pnl_eur = current_value - invested
        pnl_pct = (pnl_eur / invested * 100) if invested > 0 else 0.0
        return {
            "pnl_eur": round(pnl_eur, 2),
            "pnl_pct": round(pnl_pct, 2),
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "is_closed": True,
        }
    elif current_price is not None:
        # Offene Position: unrealisierter P&L
        current_value = current_price * quantity
        pnl_eur = current_value - invested
        pnl_pct = (pnl_eur / invested * 100) if invested > 0 else 0.0
        return {
            "pnl_eur": round(pnl_eur, 2),
            "pnl_pct": round(pnl_pct, 2),
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "is_closed": False,
        }
    else:
        return {
            "pnl_eur": 0.0,
            "pnl_pct": 0.0,
            "invested": round(invested, 2),
            "current_value": 0.0,
            "is_closed": False,
        }


def calc_portfolio_summary(current_prices: dict[str, float] = None) -> dict:
    """Berechnet eine Gesamt-Portfolio-Übersicht.

    Args:
        current_prices: Dict {ticker: aktueller_kurs}. Wenn None, wird nur Invest berechnet.

    Rückgabe: dict mit total_invested, total_value, total_pnl_eur, total_pnl_pct,
              open_positions_count, closed_positions_count.
    """
    if current_prices is None:
        current_prices = {}

    open_positions = get_open_positions()
    closed_positions = get_closed_positions()

    total_invested = 0.0
    total_value = 0.0
    realized_pnl = 0.0

    for op in open_positions:
        pos = op["position"]
        price = current_prices.get(op["ticker"])
        pnl = calc_position_pnl(pos, price)
        total_invested += pnl["invested"]
        total_value += pnl["current_value"]

    for cp in closed_positions:
        pos = cp["position"]
        pnl = calc_position_pnl(pos)
        realized_pnl += pnl["pnl_eur"]

    unrealized_pnl = total_value - total_invested
    total_pnl = unrealized_pnl + realized_pnl
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    return {
        "total_invested": round(total_invested, 2),
        "total_value": round(total_value, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "total_pnl_eur": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "open_positions_count": len(open_positions),
        "closed_positions_count": len(closed_positions),
    }


# ---------------------------------------------------------------------------
# Smart-Ticker-Erkennung mit Xetra-Priorisierung
# ---------------------------------------------------------------------------

def _get_company_name_from_yahoo(query: str) -> tuple[str, str] | None:
    """Ermittelt Firmennamen und Symbol über Yahoo Finance.

    Rückgabe: (symbol, company_name) oder None.
    """
    # 1. Direkt als Ticker versuchen
    try:
        tk = yf.Ticker(query.upper())
        info = tk.info
        if info and (info.get("regularMarketPrice") or info.get("currentPrice")):
            name = info.get("shortName") or info.get("longName") or query.upper()
            symbol = info.get("symbol", query.upper())
            return (symbol, name)
    except Exception:
        pass

    # 2. Yahoo-Suche
    try:
        results = yf.Search(query)
        quotes = results.quotes if hasattr(results, "quotes") else []
        if quotes:
            best = quotes[0]
            symbol = best.get("symbol", "")
            name = best.get("shortname") or best.get("longname") or symbol
            if symbol:
                return (symbol, name)
    except Exception:
        pass

    return None


def _validate_ticker(ticker: str) -> bool:
    """Prüft ob ein Ticker tatsächlich Kursdaten liefert."""
    try:
        tk = yf.Ticker(ticker)
        h = tk.history(period="5d")
        return not h.empty
    except Exception:
        return False


def resolve_ticker(query: str) -> dict | None:
    """Versucht einen Firmennamen oder Ticker zu einem Xetra-Ticker aufzulösen.

    Priorisierung:
    1. Direkt-Match in Xetra-CSV (Ticker oder Name)
    2. Yahoo Finance → Firmennamen ermitteln → CSV-Match
    3. Yahoo-Symbol + .DE direkt testen
    4. Fallback auf Original-Ticker

    Rückgabe: {"ticker": str, "name": str, "display": str} oder None.
    """
    query = query.strip()
    if not query:
        return None

    # Basis-Display (User-Eingabe bereinigt)
    display = query.upper().replace(".DE", "")

    # 1. Direkt-Match in Xetra-CSV (schnellster Weg)
    csv_matches = _search_xetra_csv(query)
    for csv_match in csv_matches:
        if _validate_ticker(csv_match["ticker"]):
            return {
                "ticker": csv_match["ticker"],
                "name": csv_match["name"],
                "display": display,
            }

    # 2. Yahoo Finance → Firmenname → CSV-Match
    yahoo_result = _get_company_name_from_yahoo(query)
    if yahoo_result:
        us_symbol, company_name = yahoo_result

        # Firmenname in CSV suchen (z.B. "Apple Inc." → findet APC.DE)
        csv_by_name = _search_xetra_csv(company_name)
        for match in csv_by_name:
            if _validate_ticker(match["ticker"]):
                return {
                    "ticker": match["ticker"],
                    "name": company_name,
                    "display": us_symbol.split(".")[0].upper(),
                }

        # Auch den Firmennamen verkürzt suchen (z.B. "Apple" statt "Apple Inc.")
        short_name = company_name.split(" ")[0] if " " in company_name else ""
        if short_name and len(short_name) > 2:
            csv_by_short = _search_xetra_csv(short_name)
            for match in csv_by_short:
                if _validate_ticker(match["ticker"]):
                    return {
                        "ticker": match["ticker"],
                        "name": company_name,
                        "display": us_symbol.split(".")[0].upper(),
                    }

        # 3. Yahoo Search nach .DE-Listings durchsuchen
        try:
            search_results = yf.Search(company_name)
            quotes = search_results.quotes if hasattr(search_results, "quotes") else []
            for q in quotes:
                sym = q.get("symbol", "")
                if sym.endswith(".DE") and _validate_ticker(sym):
                    return {
                        "ticker": sym.upper(),
                        "name": company_name,
                        "display": us_symbol.split(".")[0].upper(),
                    }
        except Exception:
            pass

        # 4. Fallback: Original US-Ticker verwenden
        if _validate_ticker(us_symbol):
            return {
                "ticker": us_symbol.upper(),
                "name": company_name,
                "display": us_symbol.split(".")[0].upper(),
            }

    # 4. Letzter Fallback: Ticker direkt testen
    if _validate_ticker(query.upper()):
        return {
            "ticker": query.upper(),
            "name": query.upper(),
            "display": display,
        }

    return None
