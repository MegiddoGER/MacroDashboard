"""
models/journal.py — Datenmodell & Speicherung für das Trade-Journal.

Verwaltet aktive und abgeschlossene Trades sowie Post-Trade-Reviews.
"""

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from uuid import uuid4


DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "journal.json")

# Stelle sicher, dass das Verzeichnis existiert
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)


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


class JournalStore:
    """Verwaltet das Laden und Speichern von Trades."""

    @staticmethod
    def _load_all() -> list[dict]:
        if not os.path.exists(DATA_FILE):
            return []
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    @staticmethod
    def _save_all(data: list[dict]):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @classmethod
    def get_all(cls) -> list[TradeEntry]:
        """Gibt alle Trades (absteigend sortiert nach Datum) zurück."""
        data = cls._load_all()
        trades = [TradeEntry.from_dict(t) for t in data]
        
        # Sortieren nach Entry Date, neueste zuerst
        def get_date(t):
            try:
                return datetime.strptime(t.entry_date, "%Y-%m-%d")
            except Exception:
                return datetime.min
                
        trades.sort(key=get_date, reverse=True)
        return trades

    @classmethod
    def save(cls, trade: TradeEntry):
        """Speichert einen neuen Trade oder aktualisiert einen bestehenden."""
        all_data = cls._load_all()
        found = False
        
        trade_dict = asdict(trade)
        for i, existing in enumerate(all_data):
            if existing.get("id") == trade.id:
                all_data[i] = trade_dict
                found = True
                break
                
        if not found:
            all_data.append(trade_dict)
            
        cls._save_all(all_data)

    @classmethod
    def close_trade(cls, trade_id: str, exit_price: float, exit_date: str,
                    status: str, pnl_eur: float, pnl_pct: float, review_notes: str) -> bool:
        """Schließt einen offenen Trade mit Review-Ergebnissen."""
        trades = cls.get_all()
        for t in trades:
            if t.id == trade_id:
                t.status = status
                t.exit_price = exit_price
                t.exit_date = exit_date
                t.pnl_eur = pnl_eur
                t.pnl_pct = pnl_pct
                t.review_notes = review_notes
                cls.save(t)
                return True
        return False

    @classmethod
    def delete_trade(cls, trade_id: str):
        """Löscht einen Trade unwiderruflich aus dem Journal."""
        all_data = cls._load_all()
        filtered = [t for t in all_data if t.get("id") != trade_id]
        if len(filtered) < len(all_data):
            cls._save_all(filtered)
            return True
        return False
        
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
                
        # Hitraten und Profitfaktoren ausrechnen
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
