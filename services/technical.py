"""
indicators.py — Technische Indikatoren und Sentiment-Berechnungen.
"""

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# RSI (Relative Strength Index)
# ---------------------------------------------------------------------------

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Berechnet den RSI mit Wilder-Smoothing."""
    try:
        import pandas_ta as ta
        rsi = ta.rsi(series, length=period)
        if rsi is not None and not rsi.dropna().empty:
            return rsi
    except (ImportError, Exception):
        pass

    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Berechnet MACD-Linie, Signal-Linie und Histogram.

    Rückgabe: (macd_line, signal_line, histogram) als pd.Series.
    """
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def calc_bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Berechnet Bollinger Bands.

    Rückgabe: (upper, middle, lower) als pd.Series.
    """
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


# ---------------------------------------------------------------------------
# Stochastic Oscillator
# ---------------------------------------------------------------------------

def calc_stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                    k_period: int = 14, d_period: int = 3):
    """Berechnet Stochastic %K und %D.

    Rückgabe: (k_line, d_line) als pd.Series.
    """
    low_min = low.rolling(k_period).min()
    high_max = high.rolling(k_period).max()
    k_line = 100 * (close - low_min) / (high_max - low_min).replace(0, np.nan)
    d_line = k_line.rolling(d_period).mean()
    return k_line, d_line


# ---------------------------------------------------------------------------
# ATR (Average True Range)
# ---------------------------------------------------------------------------

def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series,
             period: int = 14) -> pd.Series:
    """Berechnet den Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ---------------------------------------------------------------------------
# Fear & Greed — 5-Komponenten-Modell (0 = Extreme Fear … 100 = Extreme Greed)
# ---------------------------------------------------------------------------

def _vix_score(vix_value: float) -> float:
    """VIX-Komponente (0–20): niedriger VIX = Gier, hoher VIX = Angst."""
    if vix_value is None or np.isnan(vix_value):
        return 10.0
    clamped = np.clip(vix_value, 12, 40)
    return 20.0 * (1.0 - (clamped - 12) / (40 - 12))


def _sma200_score(close: pd.Series) -> float:
    """S&P 500 vs. SMA 200 (0–20): über SMA = Gier, unter = Angst."""
    if close is None or close.empty or len(close) < 200:
        return 10.0
    sma200 = close.rolling(200).mean().iloc[-1]
    current = close.iloc[-1]
    if sma200 == 0 or np.isnan(sma200):
        return 10.0
    pct_diff = (current - sma200) / sma200
    clamped = np.clip(pct_diff, -0.10, 0.10)
    return 20.0 * (clamped + 0.10) / 0.20


def _sma50_score(close: pd.Series) -> float:
    """S&P 500 vs. SMA 50 (0–20): kurzfristiges Momentum."""
    if close is None or close.empty or len(close) < 50:
        return 10.0
    sma50 = close.rolling(50).mean().iloc[-1]
    current = close.iloc[-1]
    if sma50 == 0 or np.isnan(sma50):
        return 10.0
    pct_diff = (current - sma50) / sma50
    clamped = np.clip(pct_diff, -0.05, 0.05)
    return 20.0 * (clamped + 0.05) / 0.10


def _rsi_score(close: pd.Series) -> float:
    """S&P 500 RSI (0–20): überkauft = Gier, überverkauft = Angst."""
    if close is None or close.empty or len(close) < 20:
        return 10.0
    rsi = calc_rsi(close, 14)
    if rsi is None or rsi.dropna().empty:
        return 10.0
    rsi_val = float(rsi.dropna().iloc[-1])
    clamped = np.clip(rsi_val, 20, 80)
    return 20.0 * (clamped - 20) / 60.0


def _safe_haven_score(gold_close: pd.Series, sp500_close: pd.Series) -> float:
    """Gold vs. S&P 500 relative Performance (0–20).

    Wenn Gold besser performt als Aktien → Angst (Safe-Haven-Nachfrage).
    Wenn Aktien besser performen → Gier.
    """
    if (gold_close is None or gold_close.empty or len(gold_close) < 20 or
            sp500_close is None or sp500_close.empty or len(sp500_close) < 20):
        return 10.0
    # 20-Tage-Performance vergleichen
    gold_ret = (gold_close.iloc[-1] / gold_close.iloc[-20] - 1) * 100
    sp_ret = (sp500_close.iloc[-1] / sp500_close.iloc[-20] - 1) * 100
    diff = sp_ret - gold_ret  # positiv = Aktien stärker = Gier
    clamped = np.clip(diff, -5, 5)
    return 20.0 * (clamped + 5) / 10.0


def calc_fear_greed_components(vix_value: float, sp500_close: pd.Series,
                                gold_close: pd.Series = None) -> dict:
    """Berechnet alle 5 Komponenten und den Gesamt-Score.

    Rückgabe: dict mit scores und Gesamt.
    """
    vix = _vix_score(vix_value)
    sma200 = _sma200_score(sp500_close)
    sma50 = _sma50_score(sp500_close)
    rsi = _rsi_score(sp500_close)
    safe_haven = _safe_haven_score(gold_close, sp500_close)

    total = round(vix + sma200 + sma50 + rsi + safe_haven, 1)
    return {
        "total": total,
        "components": [
            {"name": "VIX (Volatilität)", "score": round(vix, 1), "max": 20,
             "desc": "Niedrig = Gier, Hoch = Angst"},
            {"name": "S&P 500 vs. SMA 200", "score": round(sma200, 1), "max": 20,
             "desc": "Über Durchschnitt = Aufwärtstrend"},
            {"name": "S&P 500 vs. SMA 50", "score": round(sma50, 1), "max": 20,
             "desc": "Kurzfristiges Momentum"},
            {"name": "S&P 500 RSI (14)", "score": round(rsi, 1), "max": 20,
             "desc": "Überkauft/Überverkauft-Signal"},
            {"name": "Safe-Haven-Nachfrage", "score": round(safe_haven, 1), "max": 20,
             "desc": "Gold vs. Aktien Performance"},
        ],
    }


def calc_fear_greed(vix_value: float, sp500_close: pd.Series,
                    gold_close: pd.Series = None) -> float:
    """Gibt den Fear-&-Greed-Gesamtwert (0–100) zurück."""
    result = calc_fear_greed_components(vix_value, sp500_close, gold_close)
    return result["total"]


def fear_greed_label(score: float) -> str:
    """Menschenlesbares Label für den Score."""
    if score <= 20:
        return "Extreme Fear"
    elif score <= 40:
        return "Fear"
    elif score <= 60:
        return "Neutral"
    elif score <= 80:
        return "Greed"
    else:
        return "Extreme Greed"


# ---------------------------------------------------------------------------
# Strategische Entscheidungen — Liquidity Sweep
# ---------------------------------------------------------------------------

def detect_liquidity_sweeps(high: pd.Series, low: pd.Series,
                            close: pd.Series, lookback: int = 20,
                            reclaim_bars: int = 3) -> list[dict]:
    """Erkennt Liquidity-Sweep-Muster (Stop-Hunts).

    Sucht Swing-Hochs/-Tiefs als lokale Extrema und prüft, ob ein kurzer
    Durchbruch stattfand, der innerhalb von *reclaim_bars* Tagen
    wieder zurückgewonnen wurde.

    Rückgabe: Liste von dicts {type, date, level, sweep_date, reclaim_date}.
    """
    if high is None or len(high) < lookback * 2:
        return []

    sweeps = []
    n = len(high)

    # ── Swing-Hochs und -Tiefs finden ──
    half = lookback // 2
    for i in range(half, n - half - reclaim_bars):
        # Swing High: höchster Punkt im Fenster
        window_high = high.iloc[i - half:i + half + 1]
        if high.iloc[i] == window_high.max():
            level = float(high.iloc[i])
            # Prüfen ob danach kurz über das Hoch geschossen und zurückgekehrt
            for j in range(i + 1, min(i + 1 + reclaim_bars * 2, n)):
                if high.iloc[j] > level:
                    # Durchbruch nach oben — prüfe ob innerhalb reclaim_bars
                    # der Close wieder unter das Level fällt (bearish sweep)
                    for k in range(j + 1, min(j + 1 + reclaim_bars, n)):
                        if close.iloc[k] < level:
                            sweeps.append({
                                "type": "bearish",
                                "date": high.index[i],
                                "level": level,
                                "sweep_date": high.index[j],
                                "reclaim_date": high.index[k],
                            })
                            break
                    break

        # Swing Low: tiefster Punkt im Fenster
        window_low = low.iloc[i - half:i + half + 1]
        if low.iloc[i] == window_low.min():
            level = float(low.iloc[i])
            for j in range(i + 1, min(i + 1 + reclaim_bars * 2, n)):
                if low.iloc[j] < level:
                    # Durchbruch nach unten — prüfe Rückkehr (bullish sweep)
                    for k in range(j + 1, min(j + 1 + reclaim_bars, n)):
                        if close.iloc[k] > level:
                            sweeps.append({
                                "type": "bullish",
                                "date": low.index[i],
                                "level": level,
                                "sweep_date": low.index[j],
                                "reclaim_date": low.index[k],
                            })
                            break
                    break

    return sweeps


# ---------------------------------------------------------------------------
# Strategische Entscheidungen — Swing Trading Signale
# ---------------------------------------------------------------------------

def _calc_adx(high: pd.Series, low: pd.Series, close: pd.Series,
              period: int = 14) -> pd.Series:
    """Average Directional Index (ADX) — Trendstärke."""
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    plus_dm = high - prev_high
    minus_dm = prev_low - low
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, min_periods=period,
                                  adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, min_periods=period,
                                    adjust=False).mean() / atr)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return adx


def calc_swing_signals(high: pd.Series, low: pd.Series,
                       close: pd.Series, volume: pd.Series) -> dict | None:
    """Swing-Trading-Signale: ADX, SMA-Cross, Pivot-Levels, Risk/Reward.

    Rückgabe: dict mit allen relevanten Werten oder None.
    """
    if close is None or len(close) < 50:
        return None

    current = float(close.iloc[-1])

    # ADX
    adx = _calc_adx(high, low, close, 14)
    adx_val = float(adx.dropna().iloc[-1]) if not adx.dropna().empty else None

    if adx_val is not None:
        if adx_val >= 25:
            trend_strength = "stark"
        elif adx_val >= 20:
            trend_strength = "moderat"
        else:
            trend_strength = "schwach / seitwärts"
    else:
        trend_strength = "—"

    # SMA-Cross-Status
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    sma20_val = float(sma20.dropna().iloc[-1]) if not sma20.dropna().empty else None
    sma50_val = float(sma50.dropna().iloc[-1]) if not sma50.dropna().empty else None

    if sma20_val and sma50_val:
        if sma20_val > sma50_val:
            cross_status = "bullish"
            cross_label = "Golden Cross (SMA 20 > SMA 50)"
        else:
            cross_status = "bearish"
            cross_label = "Death Cross (SMA 20 < SMA 50)"
    else:
        cross_status = "neutral"
        cross_label = "—"

    # Richtung (Kurs vs. SMA 20)
    if sma20_val:
        if current > sma20_val:
            direction = "aufwärts"
        else:
            direction = "abwärts"
    else:
        direction = "—"

    # Pivot Points (klassisch, auf Basis des letzten Handelstags)
    last_h = float(high.iloc[-1])
    last_l = float(low.iloc[-1])
    last_c = float(close.iloc[-1])
    pivot = (last_h + last_l + last_c) / 3
    r1 = 2 * pivot - last_l
    r2 = pivot + (last_h - last_l)
    s1 = 2 * pivot - last_h
    s2 = pivot - (last_h - last_l)

    # Risk / Reward basierend auf ATR
    atr = calc_atr(high, low, close, 14)
    atr_val = float(atr.dropna().iloc[-1]) if not atr.dropna().empty else None

    if atr_val:
        stop_loss = current - 1.5 * atr_val
        take_profit = current + 2.5 * atr_val
        rr_ratio = 2.5 / 1.5
    else:
        stop_loss = None
        take_profit = None
        rr_ratio = None

    return {
        "current": current,
        "adx": adx_val,
        "trend_strength": trend_strength,
        "cross_status": cross_status,
        "cross_label": cross_label,
        "direction": direction,
        "sma20": sma20_val,
        "sma50": sma50_val,
        "pivot": round(pivot, 2),
        "r1": round(r1, 2),
        "r2": round(r2, 2),
        "s1": round(s1, 2),
        "s2": round(s2, 2),
        "atr": atr_val,
        "stop_loss": round(stop_loss, 2) if stop_loss else None,
        "take_profit": round(take_profit, 2) if take_profit else None,
        "rr_ratio": round(rr_ratio, 2) if rr_ratio else None,
        "sma20_series": sma20,
        "sma50_series": sma50,
    }


# ---------------------------------------------------------------------------
# Strategische Entscheidungen — Order Flow (volumenbasiert)
# ---------------------------------------------------------------------------

def calc_order_flow(high: pd.Series, low: pd.Series,
                    close: pd.Series, volume: pd.Series) -> dict | None:
    """Order-Flow-Analyse über volumenbasierte Proxies.

    Berechnet VWAP, OBV, Volume-Profil und Volumen-Spikes.
    Rückgabe: dict mit Serien und Zusammenfassungen oder None.
    """
    if close is None or len(close) < 20:
        return None

    # ── VWAP (kumulativ über den sichtbaren Zeitraum) ──
    typical = (high + low + close) / 3
    cum_vol = volume.cumsum()
    cum_tp_vol = (typical * volume).cumsum()
    vwap = cum_tp_vol / cum_vol.replace(0, np.nan)

    current = float(close.iloc[-1])
    vwap_val = float(vwap.dropna().iloc[-1]) if not vwap.dropna().empty else None

    if vwap_val:
        if current > vwap_val:
            vwap_signal = "bullish"
            vwap_desc = "Kurs über VWAP — Käufer dominieren"
        else:
            vwap_signal = "bearish"
            vwap_desc = "Kurs unter VWAP — Verkäufer dominieren"
    else:
        vwap_signal = "neutral"
        vwap_desc = "—"

    # ── OBV (On-Balance Volume) ──
    direction = np.where(close > close.shift(1), 1,
                         np.where(close < close.shift(1), -1, 0))
    obv = (volume * direction).cumsum()
    obv = pd.Series(obv, index=close.index, name="OBV")

    # OBV-Trend (20-Tage-Slope)
    if len(obv.dropna()) >= 20:
        obv_recent = obv.dropna().iloc[-20:]
        obv_slope = (float(obv_recent.iloc[-1]) - float(obv_recent.iloc[0]))
        if obv_slope > 0:
            obv_signal = "bullish"
            obv_desc = "OBV steigt — akkumulation (Kaufdruck)"
        else:
            obv_signal = "bearish"
            obv_desc = "OBV fällt — Distribution (Verkaufsdruck)"
    else:
        obv_signal = "neutral"
        obv_desc = "—"
        obv_slope = 0

    # ── Volume-Profil (Preis-Bins mit Volumenverteilung) ──
    n_bins = 30
    price_min = float(low.min())
    price_max = float(high.max())
    if price_max <= price_min:
        price_max = price_min + 1

    bin_edges = np.linspace(price_min, price_max, n_bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    vol_profile = np.zeros(n_bins)

    for i in range(len(close)):
        idx = int(np.clip(
            np.searchsorted(bin_edges, float(close.iloc[i])) - 1,
            0, n_bins - 1
        ))
        vol_profile[idx] += float(volume.iloc[i])

    vol_profile_df = pd.DataFrame({
        "Preis": bin_centers,
        "Volumen": vol_profile,
    })

    # High-Volume-Node (POC — Point of Control)
    poc_idx = int(np.argmax(vol_profile))
    poc_price = float(bin_centers[poc_idx])

    # ── Volumen-Spikes ──
    avg_vol_20 = volume.rolling(20).mean()
    spike_threshold = 2.0
    spikes = volume > (avg_vol_20 * spike_threshold)
    spike_dates = volume.index[spikes].tolist()
    n_spikes_recent = int(spikes.iloc[-20:].sum()) if len(spikes) >= 20 else 0

    return {
        "vwap": vwap,
        "vwap_val": vwap_val,
        "vwap_signal": vwap_signal,
        "vwap_desc": vwap_desc,
        "obv": obv,
        "obv_signal": obv_signal,
        "obv_desc": obv_desc,
        "vol_profile": vol_profile_df,
        "poc_price": poc_price,
        "spike_dates": spike_dates,
        "n_spikes_recent": n_spikes_recent,
        "current": current,
    }

# ---------------------------------------------------------------------------
# Position Sizing — Kelly Criterion + ATR-basiertes Risikomanagement
# ---------------------------------------------------------------------------

def calc_position_sizing(current_price: float, atr_val: float,
                         portfolio_value: float, max_risk_pct: float = 0.02,
                         win_rate: float = 0.55,
                         avg_win_loss_ratio: float = 1.67) -> dict | None:
    """Berechnet die optimale Positionsgröße.
    
    Args:
        current_price: Aktueller Kurs der Aktie
        atr_val: Average True Range (14 Tage)
        portfolio_value: Gesamtkapital des Portfolios in EUR
        max_risk_pct: Max. Risiko pro Trade (Standard: 2%)
        win_rate: Historische Gewinnquote (Standard: 55%)
        avg_win_loss_ratio: Durchschnittliches Gewinn/Verlust-Verhältnis (Standard: 1.67)
        
    Rückgabe: dict mit Positionsgröße, Kelly-Anteil, Stop-Level etc. oder None.
    """
    if not current_price or current_price <= 0 or not atr_val or atr_val <= 0:
        return None
    if not portfolio_value or portfolio_value <= 0:
        return None
        
    # ATR-basierter Stop-Loss (1.5x ATR unter aktuellem Kurs)
    stop_distance = 1.5 * atr_val
    risk_per_share = stop_distance
    
    # Max. Risiko in Euro
    max_risk_eur = portfolio_value * max_risk_pct
    
    # Positionsgröße (Stückzahl)
    shares = int(max_risk_eur / risk_per_share) if risk_per_share > 0 else 0
    position_value = shares * current_price
    position_pct = (position_value / portfolio_value) * 100 if portfolio_value > 0 else 0
    
    # Kelly Criterion: f* = (W × R - L) / R
    # W = Win Rate, R = Avg Win/Loss Ratio, L = 1 - W
    kelly_fraction = (win_rate * avg_win_loss_ratio - (1 - win_rate)) / avg_win_loss_ratio
    kelly_fraction = max(0.0, min(kelly_fraction, 0.25))  # Cap bei 25% (Half-Kelly Sicherheit)
    kelly_position = portfolio_value * kelly_fraction
    kelly_shares = int(kelly_position / current_price) if current_price > 0 else 0
    
    # Stop-Loss und Take-Profit Levels
    stop_loss = current_price - stop_distance
    take_profit = current_price + 2.5 * atr_val
    
    return {
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct": round(position_pct, 1),
        "risk_eur": round(max_risk_eur, 2),
        "stop_distance": round(stop_distance, 2),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "kelly_fraction_pct": round(kelly_fraction * 100, 1),
        "kelly_position": round(kelly_position, 2),
        "kelly_shares": kelly_shares,
    }

# ---------------------------------------------------------------------------
# Zusammenfassung — Synthese aller Indikatoren
# ---------------------------------------------------------------------------

def calc_technical_summary(stats: dict, hist: pd.DataFrame, info: dict = None, ticker: str = None) -> dict:
    """Wertet Trend, Oszillatoren, Volumen und Fundamentaldaten aus und generiert ein Gesamt-Fazit.

    Nutzt die Scoring Engine (services/scoring.py) für die Bewertung und
    generiert daraus Prosa-Texte (Macro, Micro, Actionable).

    Rückgabe: dict mit 'score', 'score_label', 'checklist', 'macro', 'micro', 'actionable'
    """
    from services.scoring import calc_full_score

    if hist is None or hist.empty or len(hist) < 200:
        return {
            "score": 0, "score_label": "Nicht berechenbar (zu wenig Daten)",
            "checklist": [], "macro": "—", "micro": "—", "actionable": "—"
        }

    result = calc_full_score(hist, info, ticker)
    if result is None:
        return {
            "score": 0, "score_label": "Nicht berechenbar (zu wenig Daten)",
            "checklist": [], "macro": "—", "micro": "—", "actionable": "—"
        }

    signals = result.signals

    # ── Macro-Text (Übergeordnetes Trendverhalten) ────────────────────
    trend_macro_bullish = signals.get("trend_macro_bullish", False)
    trend_macro_bearish = signals.get("trend_macro_bearish", False)
    cross_bullish = signals.get("cross_bullish", False)
    cross_bearish = signals.get("cross_bearish", False)
    adx_strong = signals.get("adx_strong", False)

    if trend_macro_bullish and cross_bullish:
        macro = "Die Aktie befindet sich in einem voll intakten, bestätigten Aufwärtstrend auf allen relevanten Zeitebenen."
    elif trend_macro_bullish and cross_bearish:
        macro = "Die Aktie befindet sich langfristig im Aufwärtstrend, vollzieht aber momentan eine mittelfristige Korrektur."
    elif trend_macro_bearish and cross_bearish:
        macro = "Das übergeordnete Chartbild ist stark angeschlagen; die Aktie befindet sich in einem klaren Abwärtstrend."
    elif trend_macro_bearish and cross_bullish:
        macro = "Die Aktie steckt langfristig in einem Abwärtstrend, baut aber aktuell ein kurzfristiges Erholungsmomentum auf (mögliche Bodenbildung)."
    else:
        macro = "Das Trendverhalten ist aktuell gemischt und deutet auf eine richtungslose Phase hin."

    if adx_strong:
        macro += " Der aktuelle Trend wird durch hohes Momentum (ADX > 25) gestützt."

    # ── Micro-Text (Kurzfristiges Momentum) ───────────────────────────
    rsi_overbought = signals.get("rsi_overbought", False)
    rsi_oversold = signals.get("rsi_oversold", False)
    bollinger_state = signals.get("bollinger_state", "Neutral")
    obv_bullish = signals.get("obv_bullish", False)

    micro_parts = []
    if rsi_overbought and bollinger_state == "Am oberen Band":
        micro_parts.append("Kurzfristig ist die Aktie jedoch stark überdehnt (RSI > 70 und am oberen Bollinger Band). Ein Rücksetzer zum Abbau der Heißläufersituation ist wahrscheinlich.")
    elif rsi_oversold and bollinger_state == "Am unteren Band":
        micro_parts.append("Auf kurzer Sichtelebene ist der Wert massiv abgestraft und überverkauft. Die Wahrscheinlichkeit für einen technischen Rebound steigt signifikant.")
    elif rsi_overbought:
        micro_parts.append("Das kurzfristige Momentum kühlt potenziell bald ab, da der Oszillator überkaufte Niveaus anzeigt.")
    elif rsi_oversold:
        micro_parts.append("Kurzfristig zeigt sich die Aktie bereits stark abverkauft, was Verkäufern weniger Spielraum lässt.")

    if obv_bullish and not trend_macro_bullish:
        micro_parts.append("Trotz des schwachen Gesamtbildes zeigt das On-Balance-Volume klare Akkumulation – Großkapital scheint sich bereits verdeckt einzukaufen.")
    elif not obv_bullish and trend_macro_bullish:
        micro_parts.append("Ein Warnsignal liefert allerdings das sinkende Orderbuch-Volumen (Distribution) in steigende Kurse hinein.")

    if not micro_parts:
        micro = "Momentum und Volatilität bewegen sich in normalen Bahnen ohne extreme Ausschläge."
    else:
        micro = " ".join(micro_parts)

    # SMC-Ergänzungen zum Micro-Text
    unmitigated_bull = signals.get("unmitigated_bull", 0)
    unmitigated_bear = signals.get("unmitigated_bear", 0)
    nearest_eqh = signals.get("nearest_eqh")
    nearest_eql = signals.get("nearest_eql")
    current = signals.get("current_price", 0)

    if unmitigated_bull > unmitigated_bear:
        micro += f" Es gibt {unmitigated_bull} offene bullische Fair Value Gaps als potenzielle Support-Zonen."
    elif unmitigated_bear > unmitigated_bull:
        micro += f" {unmitigated_bear} offene bearische Fair Value Gaps bilden Widerstandszonen über dem aktuellen Kurs."

    if nearest_eqh and current:
        dist_eqh = ((nearest_eqh - current) / current) * 100
        if dist_eqh < 3:
            micro += f" Ein Equal-High-Cluster bei {nearest_eqh:,.2f} ({dist_eqh:+.1f}%) wirkt als kurzfristiger Magnet nach oben."
    if nearest_eql and current:
        dist_eql = ((nearest_eql - current) / current) * 100
        if abs(dist_eql) < 3:
            micro += f" Ein Equal-Low-Cluster bei {nearest_eql:,.2f} ({dist_eql:+.1f}%) signalisiert Risiko eines Liquidity Sweeps nach unten."

    # ── Actionable-Text (Handlungsempfehlung) ─────────────────────────
    confidence = result.confidence
    poc_bullish = signals.get("poc_bullish", False)
    fundamental_context = " ".join(result.fundamental_text_parts) if result.fundamental_text_parts else ""

    if confidence >= 75 and not rsi_overbought:
        action = "Technisch und fundamental ein starkes Gesamtbild. Das Momentum und die Bewertung sprechen für sich — Neueinstiege bei kleinen Rücksetzern an den SMA 20 oder VWAP bieten ein gutes Chance-Risiko-Verhältnis."
    elif confidence >= 60 and not rsi_overbought:
        action = "Ein attraktives Setup für Trendfolger. Das Momentum spricht für sich, Neueinstiege bei kleinen Rücksetzern an den SMA 20 oder den VWAP bieten ein gutes Chance-Risiko-Verhältnis."
    elif confidence >= 55 and rsi_overbought:
        action = "Der Trend ist intakt, aber frisches Kapital sollte geduldig bleiben. Gewinne absichern und erst bei einem Rücklauf (Pullback) an den nächsten Support einkaufen."
    elif rsi_oversold and poc_bullish:
        action = "Spekulativer antizyklischer Einstieg: Die Aktie ist technisch überverkauft und konnte sich über dem stärksten Volumenknoten (POC) stabilisieren. Enger Stop-Loss unter dem letzten Tief ratsam."
    elif confidence <= 20:
        action = "Technisch und fundamental ein schwieriges Bild. Weder Chartstruktur noch Bewertung sprechen für eine Positionierung — Abstand halten."
    elif confidence <= 30:
        action = "Ein klassisches 'Falling Knife'. Solange die Struktur keine höheren Hochs (Golden Cross) und steigendes Volumen (OBV) ausbildet, drängt sich fundamental oder technisch kein Kauf auf."
    elif trend_macro_bullish and cross_bearish:
        action = "Abwarten, bis die mittelfristige Korrektur endet. Erst wenn der Kurs zurück über den SMA 50 klettert, löst sich das Setup wieder in Trendrichtung auf."
    else:
        action = "Unklare Gesamtlage. Das Setup rechtfertigt aktuell keine größeren Positionierungen. Auf eine klarere Trendbestätigung (z.B. Ausbruch über starken VWAP/POC-Bereich) sollte gewartet werden."

    if fundamental_context:
        action += " — Fundamental: " + fundamental_context

    return {
        "score": result.score,
        "score_label": result.score_label,
        "confidence": result.confidence,
        "confidence_label": result.confidence_label,
        "cat_scores": dict(result.cat_scores),
        "cat_max": dict(result.cat_max),
        "weights": dict(result.weights),
        "checklist": result.checklist,
        "macro": macro,
        "micro": micro,
        "actionable": action
    }

