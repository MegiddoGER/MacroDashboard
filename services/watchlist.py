"""
watchlist.py — Persistente Watchlist mit Xetra-Priorisierung & Positions-Tracking.

Persistenz: SQLAlchemy (SQLite → PostgreSQL ready).
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

from database import get_session, WatchlistItem, Position as PositionRow

# Pfad zur Watchlist-Datei (im data/ Verzeichnis des Projekts)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_XETRA_CSV = os.path.join(_DATA_DIR, "xetra_stocks.csv")


# ---------------------------------------------------------------------------
# Xetra-CSV laden (lokaler Cache)
# ---------------------------------------------------------------------------

_xetra_cache: list[dict] | None = None


def _load_xetra_csv() -> list[dict]:
    """Lädt die lokale Xetra-CSV mit Kürzel, Name, Index."""
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
    """Sucht in der Xetra-CSV nach Ticker oder Firmenname."""
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
        if e["ticker"].upper() == q_de:
            if e["ticker"] not in seen:
                results.append(e)
                seen.add(e["ticker"])

    # 2. Ticker beginnt mit Query
    for e in entries:
        if e["ticker"].upper().startswith(q_upper) and e["ticker"] not in seen:
            results.append(e)
            seen.add(e["ticker"])

    # 3. Name enthält Query (case-insensitive)
    q_lower = q.lower()
    for e in entries:
        if q_lower in e["name"].lower() and e["ticker"] not in seen:
            results.append(e)
            seen.add(e["ticker"])

    return results


# ---------------------------------------------------------------------------
# Watchlist CRUD (SQLAlchemy)
# ---------------------------------------------------------------------------

def load_watchlist() -> list[dict]:
    """Lädt die komplette Watchlist aus der Datenbank.

    Rückgabe: Liste von dicts mit ticker, name, display, status, positions.
    """
    session = get_session()
    try:
        items = session.query(WatchlistItem).all()
        return [item.to_dict() for item in items]
    finally:
        session.close()


def save_watchlist(watchlist: list[dict]) -> None:
    """Speichert eine komplette Watchlist (Bulk-Ersetzung).

    Legacy-Kompatibilität. Neue Operationen nutzen add/remove/update.
    """
    session = get_session()
    try:
        session.query(PositionRow).delete()
        session.query(WatchlistItem).delete()
        for item in watchlist:
            wl = WatchlistItem(
                ticker=item["ticker"],
                name=item.get("name", ""),
                display=item.get("display"),
                status=item.get("status", "Beobachtet"),
            )
            session.add(wl)
            for pos in item.get("positions", []):
                p = PositionRow(
                    id=pos.get("id", ""),
                    ticker=item["ticker"],
                    buy_date=pos.get("buy_date"),
                    buy_price=pos.get("buy_price"),
                    quantity=pos.get("quantity"),
                    stop_loss=pos.get("stop_loss"),
                    take_profit=pos.get("take_profit"),
                    fees=pos.get("fees", 0),
                    notes=pos.get("notes", ""),
                    sell_date=pos.get("sell_date"),
                    sell_price=pos.get("sell_price"),
                    sell_fees=pos.get("sell_fees"),
                )
                session.add(p)
        session.commit()
    except Exception as exc:
        session.rollback()
        warnings.warn(f"Watchlist konnte nicht gespeichert werden: {exc}")
    finally:
        session.close()


def add_to_watchlist(ticker: str, name: str, display: str = "",
                     status: str = "Beobachtet") -> list[dict]:
    """Fügt einen Ticker zur Watchlist hinzu (keine Duplikate)."""
    session = get_session()
    try:
        existing = session.query(WatchlistItem).filter_by(ticker=ticker.upper()).first()
        if not existing:
            if not display:
                display = ticker.replace(".DE", "") if ticker.endswith(".DE") else ticker
            wl = WatchlistItem(
                ticker=ticker.upper(),
                name=name,
                display=display.upper(),
                status=status,
            )
            session.add(wl)
            session.commit()
    finally:
        session.close()
    return load_watchlist()


def update_status(ticker: str, new_status: str) -> None:
    """Ändert den Status eines Watchlist-Eintrags."""
    session = get_session()
    try:
        item = session.query(WatchlistItem).filter(
            WatchlistItem.ticker.ilike(ticker)
        ).first()
        if item:
            item.status = new_status
            session.commit()
    finally:
        session.close()


def remove_from_watchlist(ticker: str) -> list[dict]:
    """Entfernt einen Ticker aus der Watchlist (CASCADE löscht Positionen)."""
    session = get_session()
    try:
        item = session.query(WatchlistItem).filter(
            WatchlistItem.ticker.ilike(ticker)
        ).first()
        if item:
            session.delete(item)
            session.commit()
    finally:
        session.close()
    return load_watchlist()


def get_ticker_list() -> list[str]:
    """Gibt nur die Ticker-Symbole als Liste zurück."""
    session = get_session()
    try:
        items = session.query(WatchlistItem.ticker).all()
        return [t[0] for t in items]
    finally:
        session.close()


def get_display_map() -> dict[str, str]:
    """Gibt ein Mapping von Ticker → Display-Name zurück."""
    session = get_session()
    try:
        items = session.query(WatchlistItem.ticker, WatchlistItem.display).all()
        return {t: d or t for t, d in items}
    finally:
        session.close()


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
    """Fügt eine neue Position zu einem Watchlist-Eintrag hinzu."""
    session = get_session()
    try:
        item = session.query(WatchlistItem).filter(
            WatchlistItem.ticker.ilike(ticker)
        ).first()
        if not item:
            return None

        pos = PositionRow(
            id=_new_position_id(),
            ticker=item.ticker,
            buy_date=buy_date or datetime.now().strftime("%Y-%m-%d"),
            buy_price=round(buy_price, 2),
            quantity=round(quantity, 4),
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            take_profit=round(take_profit, 2) if take_profit else None,
            fees=round(fees, 2),
            notes=notes,
            sell_date=None,
            sell_price=None,
            sell_fees=0.0,
        )
        session.add(pos)
        item.status = "Investiert"
        session.commit()
        return pos.to_dict()
    finally:
        session.close()


def close_position(ticker: str, position_id: str, sell_price: float,
                   sell_date: str = None, sell_fees: float = 0.0) -> dict | None:
    """Schließt eine offene Position (Verkauf)."""
    session = get_session()
    try:
        pos = session.query(PositionRow).filter_by(id=position_id).first()
        if not pos or pos.sell_date is not None:
            return None

        pos.sell_date = sell_date or datetime.now().strftime("%Y-%m-%d")
        pos.sell_price = round(sell_price, 2)
        pos.sell_fees = round(sell_fees, 2)

        # Prüfe ob noch offene Positionen existieren
        open_count = session.query(PositionRow).filter(
            PositionRow.ticker.ilike(ticker),
            PositionRow.sell_date.is_(None),
            PositionRow.id != position_id,
        ).count()
        if open_count == 0:
            item = session.query(WatchlistItem).filter(
                WatchlistItem.ticker.ilike(ticker)
            ).first()
            if item:
                item.status = "Beobachtet"

        session.commit()
        return pos.to_dict()
    finally:
        session.close()


def update_position(ticker: str, position_id: str, **kwargs) -> dict | None:
    """Aktualisiert Felder einer offenen Position (z.B. Stop-Loss, Take-Profit)."""
    allowed_fields = {"stop_loss", "take_profit", "notes", "quantity"}
    session = get_session()
    try:
        pos = session.query(PositionRow).filter_by(id=position_id).first()
        if not pos:
            return None
        for key, value in kwargs.items():
            if key in allowed_fields:
                if key in ("stop_loss", "take_profit") and value is not None:
                    value = round(value, 2)
                elif key == "quantity" and value is not None:
                    value = round(value, 4)
                setattr(pos, key, value)
        session.commit()
        return pos.to_dict()
    finally:
        session.close()


def delete_position(ticker: str, position_id: str) -> bool:
    """Löscht eine Position komplett."""
    session = get_session()
    try:
        pos = session.query(PositionRow).filter_by(id=position_id).first()
        if not pos:
            return False
        session.delete(pos)

        # Status aktualisieren
        open_count = session.query(PositionRow).filter(
            PositionRow.ticker.ilike(ticker),
            PositionRow.sell_date.is_(None),
            PositionRow.id != position_id,
        ).count()
        if open_count == 0:
            item = session.query(WatchlistItem).filter(
                WatchlistItem.ticker.ilike(ticker)
            ).first()
            if item:
                item.status = "Beobachtet"

        session.commit()
        return True
    finally:
        session.close()


def get_open_positions(ticker: str = None) -> list[dict]:
    """Gibt alle offenen (nicht verkauften) Positionen zurück."""
    session = get_session()
    try:
        query = session.query(PositionRow).filter(PositionRow.sell_date.is_(None))
        if ticker:
            query = query.filter(PositionRow.ticker.ilike(ticker))
        positions = query.all()
        results = []
        for pos in positions:
            item = session.query(WatchlistItem).filter_by(ticker=pos.ticker).first()
            results.append({
                "ticker": pos.ticker,
                "name": item.name if item else pos.ticker,
                "display": item.display if item else pos.ticker,
                "position": pos.to_dict(),
            })
        return results
    finally:
        session.close()


def get_closed_positions(ticker: str = None) -> list[dict]:
    """Gibt alle geschlossenen (verkauften) Positionen zurück."""
    session = get_session()
    try:
        query = session.query(PositionRow).filter(PositionRow.sell_date.isnot(None))
        if ticker:
            query = query.filter(PositionRow.ticker.ilike(ticker))
        positions = query.all()
        results = []
        for pos in positions:
            item = session.query(WatchlistItem).filter_by(ticker=pos.ticker).first()
            results.append({
                "ticker": pos.ticker,
                "name": item.name if item else pos.ticker,
                "display": item.display if item else pos.ticker,
                "position": pos.to_dict(),
            })
        return results
    finally:
        session.close()


def calc_position_pnl(position: dict, current_price: float = None) -> dict:
    """Berechnet P&L für eine einzelne Position."""
    buy_price = position.get("buy_price", 0)
    quantity = position.get("quantity", 0)
    fees = position.get("fees", 0)
    sell_fees = position.get("sell_fees", 0)
    invested = buy_price * quantity + fees

    if position.get("sell_date") is not None:
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

    Hinweis: Mischt EUR- (.DE) und USD-Positionen OHNE Wechselkursumrechnung.
    Das currency_mixed-Flag gibt an, ob die P&L-Werte FX-Effekte enthalten.
    """
    if current_prices is None:
        current_prices = {}

    open_positions = get_open_positions()
    closed_positions = get_closed_positions()

    total_invested = 0.0
    total_value = 0.0
    realized_pnl = 0.0
    has_de = False
    has_us = False

    for op in open_positions:
        pos = op["position"]
        ticker = op.get("ticker", "")
        if ticker.endswith(".DE"):
            has_de = True
        else:
            has_us = True
        price = current_prices.get(ticker)
        pnl = calc_position_pnl(pos, price)
        total_invested += pnl["invested"]
        total_value += pnl["current_value"]

    for cp in closed_positions:
        pos = cp["position"]
        ticker = cp.get("ticker", "")
        if ticker.endswith(".DE"):
            has_de = True
        else:
            has_us = True
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
        "currency_mixed": has_de and has_us,
    }


# ---------------------------------------------------------------------------
# Smart-Ticker-Erkennung mit Xetra-Priorisierung
# ---------------------------------------------------------------------------

def _get_company_name_from_yahoo(query: str) -> tuple[str, str] | None:
    """Ermittelt Firmennamen und Symbol über Yahoo Finance."""
    try:
        tk = yf.Ticker(query.upper())
        info = tk.info
        if info and (info.get("regularMarketPrice") or info.get("currentPrice")):
            name = info.get("shortName") or info.get("longName") or query.upper()
            symbol = info.get("symbol", query.upper())
            return (symbol, name)
    except Exception:
        pass

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
    """Versucht einen Firmennamen oder Ticker zu einem Xetra-Ticker aufzulösen."""
    query = query.strip()
    if not query:
        return None

    display = query.upper().replace(".DE", "")

    # 1. Direkt-Match in Xetra-CSV
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

        csv_by_name = _search_xetra_csv(company_name)
        for match in csv_by_name:
            if _validate_ticker(match["ticker"]):
                return {
                    "ticker": match["ticker"],
                    "name": company_name,
                    "display": us_symbol.split(".")[0].upper(),
                }

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

        # 3. Yahoo Search nach .DE-Listings
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

        # 4. Fallback: Original US-Ticker
        if _validate_ticker(us_symbol):
            return {
                "ticker": us_symbol.upper(),
                "name": company_name,
                "display": us_symbol.split(".")[0].upper(),
            }

    # Letzter Fallback
    if _validate_ticker(query.upper()):
        return {
            "ticker": query.upper(),
            "name": query.upper(),
            "display": display,
        }

    return None
