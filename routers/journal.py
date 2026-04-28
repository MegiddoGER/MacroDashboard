"""routers/journal.py — Trade-Journal (Lernmaschine)."""
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


@router.get("/journal", response_class=HTMLResponse)
async def journal_page(request: Request):
    templates = request.app.state.templates
    from models.journal import JournalStore

    trades = JournalStore.get_all()
    open_trades = [t for t in trades if t.status == "Offen"]
    closed_trades = [t for t in trades if t.status != "Offen"]
    stats = JournalStore.get_statistics()

    # Setup stats chart
    setup_chart_json = "null"
    if stats and stats.get("total_closed", 0) > 0:
        try:
            import plotly.express as px
            import pandas as pd
            setup_list = []
            for s_type, s_data in stats["setup_stats"].items():
                setup_list.append({
                    "Setup": s_type,
                    "Total": s_data["total"],
                    "Win Rate (%)": s_data["win_rate"],
                })
            df_stats = pd.DataFrame(setup_list)
            if not df_stats.empty:
                fig = px.bar(
                    df_stats, x="Win Rate (%)", y="Setup", orientation='h',
                    color="Win Rate (%)", color_continuous_scale="RdYlGn",
                    text_auto=True, title="Trefferquote nach Strategie"
                )
                fig.update_layout(
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(range=[0, 100]),
                    yaxis=dict(categoryorder="total ascending"),
                )
                setup_chart_json = _fig_to_json(fig)
        except Exception:
            pass

    # AI signal stats
    ai_stats = {}
    calib_chart_json = "null"
    try:
        from services.signal_history import get_signal_statistics, calc_calibration_chart
        ai_stats = get_signal_statistics()
        calib = calc_calibration_chart()
        if calib:
            import pandas as pd
            import plotly.express as px
            df_calib = pd.DataFrame(calib).dropna(subset=["hit_rate"])
            if not df_calib.empty:
                fig_cal = px.bar(
                    df_calib, x="bucket", y="hit_rate",
                    color="hit_rate", color_continuous_scale="RdYlGn",
                    text="hit_rate", title="Win-Rate nach Score-Bereichen (%)",
                )
                fig_cal.update_traces(texttemplate='%{text:.1f}%', textposition='auto')
                fig_cal.update_layout(
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(range=[0, 100]),
                )
                calib_chart_json = _fig_to_json(fig_cal)
    except Exception:
        pass

    # Serialize trades for template
    open_data = []
    for t in open_trades:
        open_data.append({
            "id": t.id, "ticker": t.ticker, "trade_type": t.trade_type,
            "entry_price": t.entry_price, "entry_date": t.entry_date,
            "setup_type": t.setup_type, "conviction": t.conviction,
            "entry_notes": t.entry_notes or "",
        })

    closed_data = []
    for t in closed_trades:
        closed_data.append({
            "id": t.id, "ticker": t.ticker, "trade_type": t.trade_type,
            "status": t.status, "entry_date": t.entry_date,
            "entry_price": t.entry_price, "exit_date": t.exit_date or "",
            "exit_price": t.exit_price or 0, "pnl_pct": t.pnl_pct or 0,
            "setup_type": t.setup_type, "conviction": t.conviction,
            "review_notes": t.review_notes or "",
        })

    ctx = {
        "current_path": "/journal",
        "header_metrics": _get_header_metrics(),
        "open_trades": open_data,
        "closed_trades": closed_data,
        "open_count": len(open_trades),
        "closed_count": len(closed_trades),
        "stats": stats,
        "setup_chart_json": setup_chart_json,
        "ai_stats": ai_stats,
        "calib_chart_json": calib_chart_json,
    }
    return templates.TemplateResponse(request=request, name="pages/journal.html", context=ctx)


@router.post("/journal/new", response_class=HTMLResponse)
async def journal_new(
    request: Request,
    ticker: str = Form(...),
    trade_type: str = Form("Long"),
    entry_date: str = Form(...),
    entry_price: float = Form(...),
    setup_type: str = Form(...),
    conviction: int = Form(3),
    notes: str = Form(""),
):
    from models.journal import TradeEntry, JournalStore
    if not ticker or entry_price <= 0:
        return HTMLResponse("<script>showToast('Ungültige Eingabe','error');</script>")
    entry = TradeEntry(
        ticker=ticker.upper(), trade_type=trade_type, setup_type=setup_type,
        entry_date=entry_date, entry_price=entry_price, conviction=conviction,
        entry_notes=notes, status="Offen",
    )
    JournalStore.save(entry)
    return HTMLResponse("<script>showToast('Trade gespeichert!');setTimeout(()=>location.reload(),500);</script>")


@router.post("/journal/close", response_class=HTMLResponse)
async def journal_close(
    request: Request,
    trade_id: str = Form(...),
    exit_price: float = Form(...),
    exit_date: str = Form(...),
    status: str = Form("Gewonnen"),
    review_notes: str = Form(""),
):
    from models.journal import JournalStore, TradeEntry
    trades = JournalStore.get_all()
    trade = next((t for t in trades if t.id == trade_id), None)
    if not trade or exit_price <= 0:
        return HTMLResponse("<script>showToast('Ungültig','error');</script>")

    delta = exit_price - trade.entry_price
    pct = (delta / trade.entry_price) * 100
    if trade.trade_type == "Short":
        delta, pct = -delta, -pct

    JournalStore.close_trade(trade_id, exit_price, exit_date, status, delta, pct, review_notes)
    return HTMLResponse("<script>showToast('Trade abgeschlossen!');setTimeout(()=>location.reload(),500);</script>")


@router.post("/journal/delete", response_class=HTMLResponse)
async def journal_delete(request: Request, trade_id: str = Form(...)):
    from models.journal import JournalStore
    JournalStore.delete_trade(trade_id)
    return HTMLResponse("<script>showToast('Eintrag gelöscht');setTimeout(()=>location.reload(),500);</script>")
