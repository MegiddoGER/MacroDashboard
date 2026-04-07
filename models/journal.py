"""
models/journal.py — Datenmodell & Speicherung für das Trade-Journal.

Verwaltet aktive und abgeschlossene Trades sowie Post-Trade-Reviews.
Persistenz: SQLAlchemy (SQLite → PostgreSQL ready).
"""

from dataclasses import dataclass, asdict, field
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
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

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
    """Verwaltet das Laden und Speichern von Trades via SQLAlchemy."""

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
    def save(cls, trade: TradeEntry):
        """Speichert einen neuen Trade oder aktualisiert einen bestehenden."""
        session = get_session()
        try:
            existing = session.query(JournalEntry).filter_by(id=trade.id).first()
            if existing:
                existing.ticker = trade.ticker
                existing.trade_type = trade.trade_type
                existing.setup_type = trade.setup_type
                existing.entry_date = trade.entry_date
                existing.entry_price = trade.entry_price
                existing.conviction = trade.conviction
                existing.entry_notes = trade.entry_notes
                existing.status = trade.status
                existing.exit_date = trade.exit_date
                existing.exit_price = trade.exit_price
                existing.pnl_eur = trade.pnl_eur
                existing.pnl_pct = trade.pnl_pct
                existing.review_notes = trade.review_notes
            else:
                row = JournalEntry(
                    id=trade.id, ticker=trade.ticker, trade_type=trade.trade_type,
                    setup_type=trade.setup_type, entry_date=trade.entry_date,
                    entry_price=trade.entry_price, conviction=trade.conviction,
                    entry_notes=trade.entry_notes, status=trade.status,
                    exit_date=trade.exit_date, exit_price=trade.exit_price,
                    pnl_eur=trade.pnl_eur, pnl_pct=trade.pnl_pct,
                    review_notes=trade.review_notes,
                )
                session.add(row)
            session.commit()
        finally:
            session.close()

    @classmethod
    def close_trade(cls, trade_id: str, exit_price: float, exit_date: str,
                    status: str, pnl_eur: float, pnl_pct: float, review_notes: str) -> bool:
        """Schließt einen offenen Trade mit Review-Ergebnissen."""
        session = get_session()
        try:
            row = session.query(JournalEntry).filter_by(id=trade_id).first()
            if not row:
                return False
            row.status = status
            row.exit_price = exit_price
            row.exit_date = exit_date
            row.pnl_eur = pnl_eur
            row.pnl_pct = pnl_pct
            row.review_notes = review_notes
            session.commit()
            return True
        finally:
            session.close()

    @classmethod
    def delete_trade(cls, trade_id: str):
        """Löscht einen Trade unwiderruflich aus dem Journal."""
        session = get_session()
        try:
            row = session.query(JournalEntry).filter_by(id=trade_id).first()
            if row:
                session.delete(row)
                session.commit()
                return True
            return False
        finally:
            session.close()
        
    @classmethod
    def get_statistics(cls) -> dict:
        """Berechnet Win-Rates und P&L pro Setup-Typ für die Lernmaschine."""
        trades = cls.get_all()
        closed_trades = [t for t in trades if t.status in ("Gewonnen", "Verloren", "Break-Even")]
        
        if not closed_trades:
            return {}
            
        win_count = len([t for t in closed_trades if t.status == "Gewonnen"])
        loss_count = len([t for t in closed_trades if t.status == "Verloren"])
        total_pnl = sum(t.pnl_eur for t in closed_trades if t.pnl_eur is not None)
        
        setup_stats = {}
        for t in closed_trades:
            s_type = t.setup_type
            if s_type not in setup_stats:
                setup_stats[s_type] = {"total": 0, "wins": 0, "pnl": 0.0}
                
            setup_stats[s_type]["total"] += 1
            if t.status == "Gewonnen":
                setup_stats[s_type]["wins"] += 1
            if t.pnl_eur is not None:
                setup_stats[s_type]["pnl"] += t.pnl_eur
                
        for s_type, data in setup_stats.items():
            if data["total"] > 0:
                data["win_rate"] = round((data["wins"] / data["total"]) * 100, 1)
            else:
                data["win_rate"] = 0.0
                
        return {
            "total_closed": len(closed_trades),
            "total_open": len([t for t in trades if t.status == "Offen"]),
            "win_rate": round((win_count / len(closed_trades)) * 100, 1) if closed_trades else 0.0,
            "win_count": win_count,
            "loss_count": loss_count,
            "total_pnl": total_pnl,
            "setup_stats": setup_stats
        }
