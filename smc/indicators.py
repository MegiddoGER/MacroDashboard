import pandas as pd
import numpy as np

def detect_fvg(df: pd.DataFrame, min_gap_pct: float = 0.5) -> list[dict]:
    """Erkennt Fair Value Gaps (FVGs) in einem DataFrame (Daily/Weekly).
    
    Ein bullishes FVG entsteht, wenn das Tief der 3. Kerze über dem Hoch der 1. Kerze liegt.
    Ein bearishes FVG entsteht, wenn das Hoch der 3. Kerze unter dem Tief der 1. Kerze liegt.
    Gibt eine Liste von Dicts mit {type, start_date, top, bottom, mitigated, mitigated_date} zurück.
    """
    if len(df) < 3:
        return []

    fvgs = []
    highs = df["High"].values
    lows = df["Low"].values
    dates = df.index

    for i in range(2, len(df)):
        # Bullish FVG
        gap_up = lows[i] - highs[i-2]
        if gap_up > 0:
            pct_gap = (gap_up / highs[i-2]) * 100
            if pct_gap >= min_gap_pct:
                fvgs.append({
                    "type": "bullish",
                    "date": dates[i-1],  # Datum der Impuls-Kerze
                    "top": float(lows[i]),
                    "bottom": float(highs[i-2]),
                    "mitigated": False,
                    "mitigated_date": None,
                    "mitigated_idx": None,
                    "gap_idx": i-1
                })
        
        # Bearish FVG
        gap_down = lows[i-2] - highs[i]
        if gap_down > 0:
            pct_gap = (gap_down / lows[i-2]) * 100
            if pct_gap >= min_gap_pct:
                fvgs.append({
                    "type": "bearish",
                    "date": dates[i-1],
                    "top": float(lows[i-2]),
                    "bottom": float(highs[i]),
                    "mitigated": False,
                    "mitigated_date": None,
                    "mitigated_idx": None,
                    "gap_idx": i-1
                })

    # Mitigation prüfen (wurde das FVG später vom Kurs gefüllt?)
    for fvg in fvgs:
        gap_idx = fvg["gap_idx"]
        for j in range(gap_idx + 2, len(df)):
            if fvg["type"] == "bullish":
                if lows[j] <= fvg["bottom"]:  # FVG wurde nach untenhin gefüllt
                    fvg["mitigated"] = True
                    fvg["mitigated_date"] = dates[j]
                    fvg["mitigated_idx"] = j
                    break
            else: # bearish
                if highs[j] >= fvg["top"]:    # FVG wurde nach obenhin gefüllt
                    fvg["mitigated"] = True
                    fvg["mitigated_date"] = dates[j]
                    fvg["mitigated_idx"] = j
                    break

    # Für die Visualisierung: Nur sehr rezente abgemilderte oder offene FVGs sind relevant
    # Wir filtern uralte, bereits gefüllte FVGs aus, um den Chart nicht zu überladen.
    relevance_threshold = len(df) - 100  # betrachte nur die letzten 100 Kerzen strenger
    active_fvgs = []
    for fvg in fvgs:
        if not fvg["mitigated"]:
            active_fvgs.append(fvg)
        else:
            # Wenn mitigiert, zeigen wir es nur, wenn die Mitigation kürzlich stattfand
            if fvg["mitigated_idx"] is not None and fvg["mitigated_idx"] > relevance_threshold:
                active_fvgs.append(fvg)

    return active_fvgs

def find_swing_points(series: pd.Series, lookback: int = 5) -> list[tuple]:
    """Findet lokale Swing Highs oder Lows."""
    swings = []
    n = len(series)
    for i in range(lookback, n - lookback):
        window = series.iloc[i - lookback : i + lookback + 1]
        if series.iloc[i] == window.max():
            swings.append((i, series.index[i], float(series.iloc[i])))
        elif series.iloc[i] == window.min():
            swings.append((i, series.index[i], float(series.iloc[i])))
    return swings

def detect_eqh_eql(df: pd.DataFrame, lookback: int = 10, tolerance_pct: float = 0.5) -> dict:
    """Erkennt Equal Highs (EQH) und Equal Lows (EQL) als Liquiditäts-Pools.
    
    Sucht nach zwei Swing-Punkten, die fast auf demselben Preislevel liegen und
    nicht bereits signifikant durchbrochen (gesweept) wurden.
    """
    if len(df) < lookback * 2:
        return {"eqh": [], "eql": []}

    highs = df["High"]
    lows = df["Low"]
    close = df["Close"]
    
    # 1. Swing Highs & Lows finden
    swing_highs = []
    swing_lows = []
    n = len(df)
    
    for i in range(lookback, n - lookback):
        window_high = highs.iloc[i - lookback : i + lookback + 1]
        if highs.iloc[i] == window_high.max():
            swing_highs.append((i, highs.index[i], float(highs.iloc[i])))
            
        window_low = lows.iloc[i - lookback : i + lookback + 1]
        if lows.iloc[i] == window_low.min():
            swing_lows.append((i, lows.index[i], float(lows.iloc[i])))

    eqh_list = []
    eql_list = []

    # 2. Pairs finden (EQH)
    for i in range(len(swing_highs)):
        for j in range(i + 1, len(swing_highs)):
            idx1, date1, price1 = swing_highs[i]
            idx2, date2, price2 = swing_highs[j]
            
            # Prüfen ob sie preislich nah beieinander liegen
            diff_pct = abs(price1 - price2) / max(price1, price2) * 100
            if diff_pct <= tolerance_pct:
                level = (price1 + price2) / 2
                
                # Prüfen, ob der Kurs zwischen den Punkten signifikant höher war (dann ungültig)
                if highs.iloc[idx1:idx2].max() > level * (1 + tolerance_pct/100 * 2):
                    continue
                
                # Prüfen, ob das EQH bereits nach Point 2 gesweept (durchbrochen) wurde
                swept = False
                for k in range(idx2 + 1, n):
                    if close.iloc[k] > level * 1.005:  # Mit echtem Close durchbrochen
                        swept = True
                        break
                
                if not swept:
                    eqh_list.append({
                        "level": level,
                        "date1": date1,
                        "date2": date2,
                        "diff_pct": diff_pct
                    })

    # 3. Pairs finden (EQL)
    for i in range(len(swing_lows)):
        for j in range(i + 1, len(swing_lows)):
            idx1, date1, price1 = swing_lows[i]
            idx2, date2, price2 = swing_lows[j]
            
            diff_pct = abs(price1 - price2) / max(price1, price2) * 100
            if diff_pct <= tolerance_pct:
                level = (price1 + price2) / 2
                
                # Dazwischen tiefer gewesen? -> Ungültig
                if lows.iloc[idx1:idx2].min() < level * (1 - tolerance_pct/100 * 2):
                    continue
                
                # Bereits nach unten durchbrochen?
                swept = False
                for k in range(idx2 + 1, n):
                    if close.iloc[k] < level * 0.995:
                        swept = True
                        break
                
                if not swept:
                    eql_list.append({
                        "level": level,
                        "date1": date1,
                        "date2": date2,
                        "diff_pct": diff_pct
                    })

    # Redundante / zu nahe beieinander liegende EQH/EQL filtern (nur das markanteste behalten)
    def filter_redundant(eq_list):
        if not eq_list: return []
        filtered = []
        # Nach Datum des zweiten Punkts sortieren (neueste zuerst)
        eq_list.sort(key=lambda x: x["date2"], reverse=True)
        for eq in eq_list:
            is_redundant = False
            for f in filtered:
                if abs(eq["level"] - f["level"]) / f["level"] * 100 <= tolerance_pct:
                    is_redundant = True
                    break
            if not is_redundant:
                filtered.append(eq)
        return filtered

    return {
        "eqh": filter_redundant(eqh_list),
        "eql": filter_redundant(eql_list)
    }

def analyze_smc(df: pd.DataFrame, htf_df: pd.DataFrame = None) -> dict:
    """Führt die komplette SMC-Analyse auf einem DataFrame durch.
    
    Args:
        df: Primary DataFrame (z.B. Daily-Kerzen)
        htf_df: Optional Higher-Timeframe DataFrame (z.B. Weekly) für MTF-Confluence
    """
    fvgs = detect_fvg(df, min_gap_pct=0.5)
    eq_levels = detect_eqh_eql(df, lookback=10, tolerance_pct=0.8) # etwas größere Toleranz für Makro
    
    # Offene FVGs zählen
    unmitigated_fvgs = [f for f in fvgs if not f["mitigated"]]
    bullish_fvgs = [f for f in unmitigated_fvgs if f["type"] == "bullish"]
    bearish_fvgs = [f for f in unmitigated_fvgs if f["type"] == "bearish"]

    current_price = df["Close"].iloc[-1]

    # ── Multi-Timeframe Confluence ──────────────────────────────────
    confluence_score = 0  # 0 = keine Bestätigung, 3 = volle MTF-Confluence
    htf_trend = "neutral"
    htf_fvg_bias = "neutral"
    
    if htf_df is not None and len(htf_df) >= 20:
        # 1. HTF-FVGs berechnen
        htf_fvgs = detect_fvg(htf_df, min_gap_pct=0.3)  # Geringere Schwelle für Weekly
        htf_unmitigated = [f for f in htf_fvgs if not f["mitigated"]]
        htf_bull = len([f for f in htf_unmitigated if f["type"] == "bullish"])
        htf_bear = len([f for f in htf_unmitigated if f["type"] == "bearish"])
        
        if htf_bull > htf_bear:
            htf_fvg_bias = "bullish"
        elif htf_bear > htf_bull:
            htf_fvg_bias = "bearish"
        
        # 2. HTF-Trend (VWAP Slope der letzten 10 Wochen)
        htf_close = htf_df["Close"]
        if len(htf_close) >= 10:
            htf_recent = htf_close.iloc[-10:]
            htf_slope = float(htf_recent.iloc[-1]) - float(htf_recent.iloc[0])
            if htf_slope > 0:
                htf_trend = "bullish"
            elif htf_slope < 0:
                htf_trend = "bearish"
        
        # 3. Confluence berechnen
        # Daily FVG-Bias stimmt mit HTF überein?
        daily_bias = "bullish" if len(bullish_fvgs) > len(bearish_fvgs) else ("bearish" if len(bearish_fvgs) > len(bullish_fvgs) else "neutral")
        
        if daily_bias != "neutral" and daily_bias == htf_fvg_bias:
            confluence_score += 1  # FVG-Alignment
        if daily_bias != "neutral" and daily_bias == htf_trend:
            confluence_score += 1  # Trend-Alignment
        if htf_fvg_bias == htf_trend and htf_trend != "neutral":
            confluence_score += 1  # HTF intern konsistent

    return {
        "fvgs": fvgs,
        "eqh": eq_levels["eqh"],
        "eql": eq_levels["eql"],
        "confluence_score": confluence_score,
        "htf_trend": htf_trend,
        "htf_fvg_bias": htf_fvg_bias,
        "stats": {
            "unmitigated_bullish": len(bullish_fvgs),
            "unmitigated_bearish": len(bearish_fvgs),
            "nearest_eqh": min([e["level"] for e in eq_levels["eqh"] if e["level"] > current_price], default=None),
            "nearest_eql": max([e["level"] for e in eq_levels["eql"] if e["level"] < current_price], default=None),
        }
    }
