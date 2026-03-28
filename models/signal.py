"""
models/signal.py — Standardisiertes Signal-Datenmodell für das MacroDashboard.

Gemeinsame Datenstruktur für:
- Analyse-Signale (Confidence Score + Empfehlung)
- Signal-Historisierung (Trefferquoten-Tracking)
- Alerts (Benachrichtigungen bei Score-Änderungen)
- Trade-Journal (Verknüpfung mit Trades)
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Signal-Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """Ein einzelnes Analyse-Signal mit allen relevanten Daten."""

    # Kernfelder
    ticker: str = ""
    timestamp: str = ""                    # ISO-Format: "2024-01-15T14:30:00"
    signal_type: str = "hold"              # "buy", "sell", "hold"
    confidence: float = 50.0               # 0-100, aus Scoring Engine

    # Score-Details
    score_label: str = ""                  # z.B. "Starkes Kaufsignal 🟢"
    confidence_label: str = ""             # z.B. "Hohe Confidence"
    cat_scores: dict = field(default_factory=dict)    # {"trend": X, ...}
    cat_max: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)

    # Marktdaten zum Signal-Zeitpunkt
    price_at_signal: float = 0.0           # Kurs bei Signal-Erzeugung
    rsi_at_signal: Optional[float] = None
    volume_spike: bool = False

    # Kontext
    contributing_factors: list = field(default_factory=list)  # ["RSI überverkauft", "FVG Support", ...]
    macro_text: str = ""                   # Makro-Zusammenfassung
    actionable_text: str = ""              # Handlungsempfehlung

    # Nachverfolgung (wird später durch Signal-Historisierung befüllt)
    price_1w_later: Optional[float] = None
    price_1m_later: Optional[float] = None
    price_3m_later: Optional[float] = None
    was_successful: Optional[bool] = None  # None = noch nicht bewertet

    def to_dict(self) -> dict:
        """Konvertiert Signal zu serialisierbarem dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Signal":
        """Erstellt ein Signal aus einem dict (z.B. aus JSON)."""
        # Nur Felder übernehmen die im Dataclass existieren
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    @classmethod
    def from_score_result(cls, ticker: str, score_result, price: float = 0.0) -> "Signal":
        """Erstellt ein Signal aus einem ScoreResult (von scoring.py).

        Args:
            ticker: Aktien-Ticker
            score_result: ScoreResult Objekt von services/scoring.py
            price: Aktueller Kurs zum Signal-Zeitpunkt
        """
        # Signal-Typ aus Confidence ableiten
        if score_result.confidence >= 65:
            signal_type = "buy"
        elif score_result.confidence <= 35:
            signal_type = "sell"
        else:
            signal_type = "hold"

        # Contributing Factors aus Checklist extrahieren
        factors = []
        for entry in score_result.checklist:
            signal_text = entry.get("Signal", "")
            if "🟢" in signal_text or "↑" in signal_text:
                factors.append(f"✅ {entry.get('Indikator', '')}: {signal_text}")
            elif "🔴" in signal_text or "↓" in signal_text:
                factors.append(f"❌ {entry.get('Indikator', '')}: {signal_text}")

        return cls(
            ticker=ticker.upper(),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            signal_type=signal_type,
            confidence=score_result.confidence,
            score_label=score_result.score_label,
            confidence_label=score_result.confidence_label,
            cat_scores=dict(score_result.cat_scores),
            cat_max=dict(score_result.cat_max),
            weights=dict(score_result.weights),
            price_at_signal=round(price, 2),
            rsi_at_signal=score_result.signals.get("rsi_val"),
            contributing_factors=factors,
        )


# ---------------------------------------------------------------------------
# Signal-Store (Persistenz)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_SIGNALS_FILE = os.path.join(_DATA_DIR, "signals.json")


class SignalStore:
    """Persistente Speicherung von Signalen in JSON."""

    @staticmethod
    def _load_all() -> list[dict]:
        """Lädt alle gespeicherten Signale."""
        if not os.path.exists(_SIGNALS_FILE):
            return []
        try:
            with open(_SIGNALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, Exception):
            return []

    @staticmethod
    def _save_all(signals: list[dict]) -> None:
        """Speichert alle Signale."""
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(signals, f, indent=2, ensure_ascii=False)

    @classmethod
    def save(cls, signal: Signal) -> None:
        """Speichert ein neues Signal."""
        signals = cls._load_all()
        signals.append(signal.to_dict())
        cls._save_all(signals)

    @classmethod
    def get_all(cls, ticker: str = None, limit: int = None) -> list[Signal]:
        """Lädt Signale, optional gefiltert nach Ticker.

        Args:
            ticker: Optional. Nur Signale für diesen Ticker.
            limit: Optional. Max. Anzahl (neueste zuerst).

        Rückgabe: Liste von Signal-Objekten, neueste zuerst.
        """
        raw = cls._load_all()

        if ticker:
            raw = [s for s in raw if s.get("ticker", "").upper() == ticker.upper()]

        # Neueste zuerst
        raw.sort(key=lambda s: s.get("timestamp", ""), reverse=True)

        if limit:
            raw = raw[:limit]

        return [Signal.from_dict(s) for s in raw]

    @classmethod
    def get_latest(cls, ticker: str) -> Signal | None:
        """Gibt das neueste Signal für einen Ticker zurück."""
        signals = cls.get_all(ticker=ticker, limit=1)
        return signals[0] if signals else None

    @classmethod
    def count(cls, ticker: str = None) -> int:
        """Zählt gespeicherte Signale."""
        raw = cls._load_all()
        if ticker:
            raw = [s for s in raw if s.get("ticker", "").upper() == ticker.upper()]
        return len(raw)

    @classmethod
    def update_outcome(cls, ticker: str, timestamp: str,
                       price_1w: float = None, price_1m: float = None,
                       price_3m: float = None) -> bool:
        """Aktualisiert die Nachverfolgung eines Signals.

        Berechnet automatisch ob das Signal erfolgreich war.
        """
        signals = cls._load_all()
        for s in signals:
            if s.get("ticker") == ticker.upper() and s.get("timestamp") == timestamp:
                if price_1w is not None:
                    s["price_1w_later"] = round(price_1w, 2)
                if price_1m is not None:
                    s["price_1m_later"] = round(price_1m, 2)
                if price_3m is not None:
                    s["price_3m_later"] = round(price_3m, 2)

                # Erfolgsberechnung
                entry_price = s.get("price_at_signal", 0)
                signal_type = s.get("signal_type", "hold")
                check_price = price_1m or price_1w  # Primär 1M, Fallback 1W

                if entry_price > 0 and check_price and signal_type != "hold":
                    if signal_type == "buy":
                        s["was_successful"] = check_price > entry_price
                    elif signal_type == "sell":
                        s["was_successful"] = check_price < entry_price

                cls._save_all(signals)
                return True
        return False
