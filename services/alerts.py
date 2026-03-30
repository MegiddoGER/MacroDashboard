"""
services/alerts.py — Background-Überwachung für Alerts.

Checks running alerts against current ticker data and flags triggered ones.
"""

from datetime import datetime
import pandas as pd

from models.alerts import AlertStore, AlertConfig
from services.cache import cached_stock_details


def _get_current_metrics(ticker: str) -> dict:
    """Holt die aktuellsten Werte (Preis, RSI, Score) für einen Ticker."""
    try:
        from data_cache import cached_stock_history
        hist = cached_stock_history(ticker, "1mo")
        
        if hist is None or hist.empty:
            return {}
            
        current_price = hist["Close"].iloc[-1]
        
        # RSI 14
        delta = hist["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50.0

        # Quick Score (ohne Fundamentals/News um Rate Limits zu sparen)
        from services.scoring import calc_quick_score
        score_res = calc_quick_score(hist)
        score_val = score_res.score if score_res else 0.0

        return {
            "price": current_price,
            "rsi": current_rsi,
            "score": score_val
        }
    except Exception as e:
        print(f"Fehler bei Metrik-Beschaffung für Alert {ticker}: {e}")
        return {}


def check_active_alerts() -> list[AlertConfig]:
    """Prüft alle aktiven Alerts auf Auslösung.
    
    Wird z.B. bei jedem Dashboard-Refresh im Hintergrund aufgerufen.
    """
    active_alerts = AlertStore.get_active()
    newly_triggered = []
    
    # Gruppieren nach Ticker um API-Calls / Historie-Lookups zu minimieren
    tickers = set([a.ticker for a in active_alerts])
    
    ticker_metrics = {}
    for t in tickers:
        ticker_metrics[t] = _get_current_metrics(t)
        
    for a in active_alerts:
        metrics = ticker_metrics.get(a.ticker, {})
        if not metrics:
            continue
            
        is_triggered = False
        trigger_val = 0.0
        
        c_price = metrics.get("price", 0.0)
        c_rsi = metrics.get("rsi", 50.0)
        c_score = metrics.get("score", 0.0)

        # -------------------------------------------------------------------
        # Logik-Regeln
        # -------------------------------------------------------------------
        if a.alert_type == "price_above" and c_price >= a.threshold:
            is_triggered = True; trigger_val = c_price
        elif a.alert_type == "price_below" and c_price > 0 and c_price <= a.threshold:
            is_triggered = True; trigger_val = c_price
        elif a.alert_type == "rsi_above" and c_rsi >= a.threshold:
            is_triggered = True; trigger_val = c_rsi
        elif a.alert_type == "rsi_below" and c_rsi > 0 and c_rsi <= a.threshold:
            is_triggered = True; trigger_val = c_rsi
        elif a.alert_type == "score_above" and c_score >= a.threshold:
            is_triggered = True; trigger_val = c_score
        elif a.alert_type == "score_below" and c_score > 0 and c_score <= a.threshold:
            is_triggered = True; trigger_val = c_score

        # -------------------------------------------------------------------
        # Status Update
        # -------------------------------------------------------------------
        if is_triggered:
            a.status = "triggered"
            a.triggered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            a.trigger_value = trigger_val
            AlertStore.save(a)
            newly_triggered.append(a)

    return newly_triggered
