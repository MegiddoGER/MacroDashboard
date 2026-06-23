"""
snapshot_engine/auswertung.py — Kennzahlen-Berechnung für die Snapshot Engine.

Berechnet Trefferquoten, Durchschnitts-Returns und Score-Kalibrierung
ausschließlich aus der Datenbank (kein yfinance-Aufruf).
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from snapshot_engine.models import AnalyseSnapshot


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------

def kennzahlen_berechnen(db: Session) -> dict:
    """Berechnet alle Auswertungs-Kennzahlen aus den gespeicherten Snapshots.

    Nur DB-Lesezugriff, kein yfinance.

    Returns:
        Dict mit kauf_win_rate, verkauf_win_rate, avg_return_je_signal,
        snapshots_ausstehend, snapshots_ausgewertet, top_ticker, flop_ticker,
        score_kalibrierung.
    """
    ergebnis = {
        "kauf_win_rate": None,
        "verkauf_win_rate": None,
        "avg_return_je_signal": {"KAUF": None, "NEUTRAL": None, "VERKAUF": None},
        "snapshots_ausstehend": 0,
        "snapshots_ausgewertet": 0,
        "top_ticker": [],
        "flop_ticker": [],
        "score_kalibrierung": [],
    }

    try:
        # Alle Snapshots laden
        alle = db.query(AnalyseSnapshot).all()
        ausgewertet = [s for s in alle if s.ausgewertet]
        ausstehend = [s for s in alle if not s.ausgewertet]

        ergebnis["snapshots_ausgewertet"] = len(ausgewertet)
        ergebnis["snapshots_ausstehend"] = len(ausstehend)

        if not ausgewertet:
            return ergebnis

        # ── KAUF Win-Rate ──────────────────────────────────────────
        kauf_snapshots = [s for s in ausgewertet if s.richtungssignal == "KAUF"]
        if kauf_snapshots:
            kauf_gewonnen = sum(1 for s in kauf_snapshots if s.outcome_return and s.outcome_return > 0)
            ergebnis["kauf_win_rate"] = round(kauf_gewonnen / len(kauf_snapshots) * 100, 1)

        # ── VERKAUF Win-Rate ───────────────────────────────────────
        # Signal korrekt wenn Kurs tatsächlich gefallen ist (outcome_return < 0)
        verkauf_snapshots = [s for s in ausgewertet if s.richtungssignal == "VERKAUF"]
        if verkauf_snapshots:
            verkauf_korrekt = sum(1 for s in verkauf_snapshots if s.outcome_return and s.outcome_return < 0)
            ergebnis["verkauf_win_rate"] = round(verkauf_korrekt / len(verkauf_snapshots) * 100, 1)

        # ── Ø Return je Signal ─────────────────────────────────────
        for signal in ["KAUF", "NEUTRAL", "VERKAUF"]:
            signal_snapshots = [s for s in ausgewertet
                                if s.richtungssignal == signal and s.outcome_return is not None]
            if signal_snapshots:
                avg = sum(s.outcome_return for s in signal_snapshots) / len(signal_snapshots)
                ergebnis["avg_return_je_signal"][signal] = round(avg, 2)

        # ── Top/Flop Ticker ────────────────────────────────────────
        # Nur KAUF-Snapshots, min. 3 ausgewertete Einträge pro Ticker
        ticker_returns = defaultdict(list)
        for s in ausgewertet:
            if s.richtungssignal == "KAUF" and s.outcome_return is not None:
                ticker_returns[s.ticker].append(s.outcome_return)

        ticker_avg = {}
        for ticker, returns in ticker_returns.items():
            if len(returns) >= 3:
                ticker_avg[ticker] = round(sum(returns) / len(returns), 2)

        if ticker_avg:
            sortiert = sorted(ticker_avg.items(), key=lambda x: x[1], reverse=True)
            ergebnis["top_ticker"] = [
                {"ticker": t, "avg_return": r, "anzahl": len(ticker_returns[t])}
                for t, r in sortiert[:3]
            ]
            ergebnis["flop_ticker"] = [
                {"ticker": t, "avg_return": r, "anzahl": len(ticker_returns[t])}
                for t, r in sortiert[-3:]
            ]

        # ── Score-Kalibrierung ─────────────────────────────────────
        # Ø outcome_return gruppiert nach Confidence-Ranges
        ranges = [
            {"label": "0–39 (Schwach)", "min": 0, "max": 39},
            {"label": "40–59 (Neutral)", "min": 40, "max": 59},
            {"label": "60–74 (Gut)", "min": 60, "max": 74},
            {"label": "75–100 (Stark)", "min": 75, "max": 100},
        ]

        for r in ranges:
            gruppe = [s for s in ausgewertet
                      if s.outcome_return is not None
                      and r["min"] <= (s.confidence or 0) <= r["max"]]
            if gruppe:
                avg = sum(s.outcome_return for s in gruppe) / len(gruppe)
                ergebnis["score_kalibrierung"].append({
                    "range": r["label"],
                    "avg_return": round(avg, 2),
                    "anzahl": len(gruppe),
                })
            else:
                ergebnis["score_kalibrierung"].append({
                    "range": r["label"],
                    "avg_return": None,
                    "anzahl": 0,
                })

    except Exception as e:
        print(f"[Auswertung] Fehler bei Kennzahlen-Berechnung: {e}")

    return ergebnis
