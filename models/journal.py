"""
models/journal.py — Lesezugriff auf das Trade-Journal.

Geschrieben wird das Journal ausschliesslich automatisch beim Kauf und Verkauf
(services/watchlist.py). Dieses Modul liest nur — es gibt keinen Eingabepfad
mehr, seit die handgefuehrte Journal-Seite entfallen ist.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from database import get_session, JournalEntry


@dataclass
class TradeEntry:
    """Repräsentiert einen einzelnen Trade im Journal."""
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    ticker: str = ""
    trade_type: str = "Long"               # "Long" oder "Short"
    setup_type: str = "SMC / Trendfolge"   # Dropdown Auswahl
    entry_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    entry_price: float = 0.0
    conviction: int = 3                    # 1 bis 5 (Sterne)
    entry_notes: str = ""                  # Kaufgrund
    
    status: str = "Offen"                  # "Offen", "Gewonnen", "Verloren", "Break-Even"
    exit_date: str | None = None
    exit_price: float | None = None
    pnl_eur: float | None = None
    pnl_pct: float | None = None
    
    review_notes: str = ""                 # Lessons learned nach dem Schließen

    @classmethod
    def from_db(cls, row: JournalEntry):
        """Erstellt TradeEntry aus einem DB-Row."""
        return cls(
            id=row.id, ticker=row.ticker or "", trade_type=row.trade_type or "Long",
            setup_type=row.setup_type or "", entry_date=row.entry_date or "",
            entry_price=row.entry_price or 0.0, conviction=row.conviction or 3,
            entry_notes=row.entry_notes or "", status=row.status or "Offen",
            exit_date=row.exit_date, exit_price=row.exit_price,
            pnl_eur=row.pnl_eur, pnl_pct=row.pnl_pct,
            review_notes=row.review_notes or "",
        )


class JournalStore:
    """Liest Journaleintraege via SQLAlchemy."""

    @classmethod
    def get_all(cls) -> list[TradeEntry]:
        """Gibt alle Trades (absteigend sortiert nach Datum) zurück."""
        session = get_session()
        try:
            rows = session.query(JournalEntry).order_by(
                JournalEntry.entry_date.desc()
            ).all()
            return [TradeEntry.from_db(r) for r in rows]
        finally:
            session.close()

    @classmethod
    def get_statistics(cls) -> dict:
        """Realisierte Trefferquote über alle abgeschlossenen Trades."""
        closed_trades = [t for t in cls.get_all()
                         if t.status in ("Gewonnen", "Verloren", "Break-Even")]
        if not closed_trades:
            return {}

        win_count = len([t for t in closed_trades if t.status == "Gewonnen"])
        return {
            "total_closed": len(closed_trades),
            "win_rate": round((win_count / len(closed_trades)) * 100, 1),
        }
