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

def analyze_smc(df: pd.DataFrame) -> dict:
    """Führt die komplette SMC-Analyse auf einem DataFrame durch."""
    fvgs = detect_fvg(df, min_gap_pct=0.5)
    eq_levels = detect_eqh_eql(df, lookback=10, tolerance_pct=0.8) # etwas größere Toleranz für Makro
    
    # Offene FVGs zählen
    unmitigated_fvgs = [f for f in fvgs if not f["mitigated"]]
    bullish_fvgs = [f for f in unmitigated_fvgs if f["type"] == "bullish"]
    bearish_fvgs = [f for f in unmitigated_fvgs if f["type"] == "bearish"]

    current_price = df["Close"].iloc[-1]

    return {
        "fvgs": fvgs,
        "eqh": eq_levels["eqh"],
        "eql": eq_levels["eql"],
        "stats": {
            "unmitigated_bullish": len(bullish_fvgs),
            "unmitigated_bearish": len(bearish_fvgs),
            "nearest_eqh": min([e["level"] for e in eq_levels["eqh"] if e["level"] > current_price], default=None),
            "nearest_eql": max([e["level"] for e in eq_levels["eql"] if e["level"] < current_price], default=None),
        }
    }
