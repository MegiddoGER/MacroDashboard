"""routers/watchlist.py — Watchlist + Portfolio-Management."""
import json
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])


def _get_header_metrics():
    from main import get_header_metrics
    return get_header_metrics()


def _fig_to_json(fig):
    if fig is None:
        return "null"
    return json.dumps(fig.to_dict(), default=str)


@router.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request):
    templates = request.app.state.templates
    from services.watchlist import (
        load_watchlist, get_display_map,
        get_open_positions, get_closed_positions,
        calc_position_pnl, calc_portfolio_summary,
    )
    from services.cache_core import cached_multi

    wl_items = load_watchlist()
    display_map = get_display_map()
    invested = [i for i in wl_items if i.get("status") == "Investiert"]
    watching = [i for i in wl_items if i.get("status", "Beobachtet") == "Beobachtet"]

    # Market data for invested/watching groups
    groups = []
    for title, items, color in [("💰 Investiert", invested, "#00d4aa"), ("👁 Beobachtet", watching, "#64748b")]:
        if not items:
            continue
        tickers = [i["ticker"] for i in items]
        names = [display_map.get(t, t) for t in tickers]
        tickers_str = ", ".join(tickers)
        df = None
        try:
            df = cached_multi(tickers_str)
        except Exception:
            pass
        rows = []
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                t = r.get("Ticker", "")
                rows.append({
                    "ticker": display_map.get(t, t),
                    "price": f"{r.get('Kurs (€)', 0):,.2f}",
                    "change": float(r.get("Veränderung %", 0)),
                    "rsi": r.get("RSI (14)"),
                    "sma50": r.get("SMA 50"),
                    "sma200": r.get("SMA 200"),
                })
        groups.append({"title": title, "color": color, "count": len(items), "names": ", ".join(names), "rows": rows})

    # Portfolio
    open_pos = get_open_positions()
    closed_pos = get_closed_positions()
    current_prices = {}
    if open_pos:
        open_tickers = list(set(op["ticker"] for op in open_pos))
        try:
            price_df = cached_multi(", ".join(open_tickers))
            if price_df is not None and not price_df.empty and "Ticker" in price_df.columns:
                for _, row in price_df.iterrows():
                    current_prices[row["Ticker"]] = row.get("Kurs (€)", 0)
        except Exception:
            pass

    summary = calc_portfolio_summary(current_prices) if (open_pos or closed_pos) else None

    # Active positions table
    pos_rows = []
    for op in open_pos:
        pos = op["position"]
        price = current_prices.get(op["ticker"])
        pnl = calc_position_pnl(pos, price)
        pos_rows.append({
            "ticker": display_map.get(op["ticker"], op["ticker"]),
            "raw_ticker": op["ticker"],
            "buy_date": pos.get("buy_date", "—"),
            "buy_price": pos.get("buy_price", 0),
            "quantity": pos.get("quantity", 0),
            "current": price or 0,
            "pnl_eur": pnl["pnl_eur"],
            "pnl_pct": pnl["pnl_pct"],
            "sl": pos.get("stop_loss"),
            "tp": pos.get("take_profit"),
            "id": pos.get("id", ""),
        })

    # Buy options
    buy_options = []
    for item in wl_items:
        buy_options.append({
            "ticker": item["ticker"],
            "display": item.get("display", item["ticker"]),
            "name": item.get("name", ""),
        })

    # Sell options
    sell_options = []
    for op in open_pos:
        pos = op["position"]
        disp = display_map.get(op["ticker"], op["ticker"])
        sell_options.append({
            "ticker": op["ticker"],
            "display": disp,
            "position_id": pos.get("id", ""),
            "quantity": pos.get("quantity", 0),
            "buy_price": pos.get("buy_price", 0),
            "buy_date": pos.get("buy_date", ""),
        })

    ctx = {
        "current_path": "/watchlist",
        "header_metrics": _get_header_metrics(),
        "groups": groups,
        "summary": summary,
        "pos_rows": pos_rows,
        "buy_options": buy_options,
        "sell_options": sell_options,
        "has_portfolio": bool(open_pos or closed_pos),
        "has_open": bool(open_pos),
    }
    return templates.TemplateResponse(request=request, name="pages/watchlist.html", context=ctx)


@router.post("/watchlist/buy", response_class=HTMLResponse)
async def watchlist_buy(
    request: Request,
    ticker: str = Form(...),
    buy_price: float = Form(...),
    quantity: float = Form(...),
    buy_date: str = Form(...),
    stop_loss: float = Form(0),
    take_profit: float = Form(0),
    fees: float = Form(0),
    notes: str = Form(""),
):
    from services.watchlist import add_position
    result = add_position(
        ticker=ticker,
        buy_price=buy_price,
        quantity=quantity,
        buy_date=buy_date,
        stop_loss=stop_loss if stop_loss > 0 else None,
        take_profit=take_profit if take_profit > 0 else None,
        fees=fees,
        notes=notes,
    )
    if result:
        return HTMLResponse(
            content="<script>showToast('Position eröffnet!');setTimeout(()=>location.reload(),500);</script>"
        )
    return HTMLResponse(
        content="<script>showToast('Fehler beim Erstellen','error');</script>"
    )


@router.post("/watchlist/sell", response_class=HTMLResponse)
async def watchlist_sell(
    request: Request,
    ticker: str = Form(...),
    position_id: str = Form(...),
    sell_price: float = Form(...),
    sell_date: str = Form(...),
    sell_fees: float = Form(0),
    sell_setup: str = Form("Sonstiges"),
    sell_conviction: int = Form(3),
    sell_review: str = Form(""),
):
    from services.watchlist import close_position, calc_position_pnl, get_display_map, get_open_positions
    from models.journal import TradeEntry, JournalStore

    display_map = get_display_map()

    # Find the position to get buy info
    open_pos = get_open_positions()
    sell_pos = None
    for op in open_pos:
        if op["ticker"] == ticker and op["position"].get("id") == position_id:
            sell_pos = op["position"]
            break

    result = close_position(
        ticker=ticker,
        position_id=position_id,
        sell_price=sell_price,
        sell_date=sell_date,
        sell_fees=sell_fees,
    )
    if result and sell_pos:
        pnl = calc_position_pnl(sell_pos, sell_price)
        pnl_pct = pnl["pnl_pct"]
        auto_status = "Gewonnen" if pnl_pct > 0.5 else ("Verloren" if pnl_pct < -0.5 else "Break-Even")
        disp_name = display_map.get(ticker, ticker)

        journal_entry = TradeEntry(
            ticker=disp_name,
            trade_type="Long",
            setup_type=sell_setup,
            entry_date=sell_pos.get("buy_date", ""),
            entry_price=sell_pos.get("buy_price", 0),
            conviction=sell_conviction,
            entry_notes=sell_pos.get("notes", "") or "[Auto-Import]",
            status=auto_status,
            exit_date=sell_date,
            exit_price=sell_price,
            pnl_eur=pnl["pnl_eur"],
            pnl_pct=pnl_pct,
            review_notes=sell_review or f"Position geschlossen: {pnl['pnl_eur']:+,.2f}€ ({pnl_pct:+.1f}%)",
        )
        JournalStore.save(journal_entry)

        return HTMLResponse(
            content="<script>showToast('Position geschlossen + Journal gespeichert!');setTimeout(()=>location.reload(),500);</script>"
        )
    return HTMLResponse(
        content="<script>showToast('Fehler beim Schließen','error');</script>"
    )
