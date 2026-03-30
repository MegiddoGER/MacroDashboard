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

def _analyze_tf(df: pd.DataFrame, label: str, min_gap_pct: float = 0.5) -> dict:
    """Analysiert einen einzelnen Timeframe und gibt Scores zurück.

    Returns:
        Dict mit trend, fvg_bias, structure, fvgs, eq_levels.
    """
    if df is None or len(df) < 20:
        return {
            "label": label,
            "trend": "neutral",
            "fvg_bias": "neutral",
            "structure": "neutral",
            "fvgs_bull": 0,
            "fvgs_bear": 0,
            "eqh_count": 0,
            "eql_count": 0,
        }

    # FVGs
    fvgs = detect_fvg(df, min_gap_pct=min_gap_pct)
    unmitigated = [f for f in fvgs if not f["mitigated"]]
    bull_count = len([f for f in unmitigated if f["type"] == "bullish"])
    bear_count = len([f for f in unmitigated if f["type"] == "bearish"])

    if bull_count > bear_count:
        fvg_bias = "bullish"
    elif bear_count > bull_count:
        fvg_bias = "bearish"
    else:
        fvg_bias = "neutral"

    # Trend (Slope der letzten N Close-Werte)
    close = df["Close"]
    lookback = min(10, len(close) - 1)
    if lookback >= 2:
        recent = close.iloc[-lookback:]
        slope = float(recent.iloc[-1]) - float(recent.iloc[0])
        if slope > 0:
            trend = "bullish"
        elif slope < 0:
            trend = "bearish"
        else:
            trend = "neutral"
    else:
        trend = "neutral"

    # Structure (EQH/EQL)
    eq_levels = detect_eqh_eql(df, lookback=max(5, min(10, len(df) // 10)),
                                tolerance_pct=0.8)
    eqh_count = len(eq_levels.get("eqh", []))
    eql_count = len(eq_levels.get("eql", []))

    # Strukturelle Bias
    if eql_count > eqh_count:
        structure = "bearish"   # Mehr Liquidität unter dem Markt = bearish Potential
    elif eqh_count > eql_count:
        structure = "bullish"   # Mehr Liquidität über dem Markt = bullish Potential
    else:
        structure = "neutral"

    return {
        "label": label,
        "trend": trend,
        "fvg_bias": fvg_bias,
        "structure": structure,
        "fvgs_bull": bull_count,
        "fvgs_bear": bear_count,
        "eqh_count": eqh_count,
        "eql_count": eql_count,
    }


def analyze_smc(df: pd.DataFrame,
                htf_df: pd.DataFrame = None,
                monthly_df: pd.DataFrame = None) -> dict:
    """Führt die komplette SMC-Analyse auf einem DataFrame durch.

    Args:
        df: Primary DataFrame (z.B. Daily-Kerzen)
        htf_df: Optional Higher-Timeframe DataFrame (z.B. Weekly) für MTF-Confluence
        monthly_df: Optional Monthly-Daten für 3-Tier MTF-Confluence
    """
    fvgs = detect_fvg(df, min_gap_pct=0.5)
    eq_levels = detect_eqh_eql(df, lookback=10, tolerance_pct=0.8)

    # Offene FVGs zählen
    unmitigated_fvgs = [f for f in fvgs if not f["mitigated"]]
    bullish_fvgs = [f for f in unmitigated_fvgs if f["type"] == "bullish"]
    bearish_fvgs = [f for f in unmitigated_fvgs if f["type"] == "bearish"]

    current_price = df["Close"].iloc[-1]

    # ── Multi-Timeframe Analyse ─────────────────────────────────────
    daily_tf = _analyze_tf(df, "Daily", min_gap_pct=0.5)
    weekly_tf = _analyze_tf(htf_df, "Weekly", min_gap_pct=0.3)
    monthly_tf = _analyze_tf(monthly_df, "Monthly", min_gap_pct=0.2)

    # MTF-Matrix (für UI-Visualisierung)
    mtf_matrix = {
        "timeframes": ["Monthly", "Weekly", "Daily"],
        "categories": ["Trend", "FVG Bias", "Structure"],
        "data": {
            "Monthly": {
                "Trend": monthly_tf["trend"],
                "FVG Bias": monthly_tf["fvg_bias"],
                "Structure": monthly_tf["structure"],
            },
            "Weekly": {
                "Trend": weekly_tf["trend"],
                "FVG Bias": weekly_tf["fvg_bias"],
                "Structure": weekly_tf["structure"],
            },
            "Daily": {
                "Trend": daily_tf["trend"],
                "FVG Bias": daily_tf["fvg_bias"],
                "Structure": daily_tf["structure"],
            },
        },
        "details": {
            "Monthly": monthly_tf,
            "Weekly": weekly_tf,
            "Daily": daily_tf,
        },
    }

    # ── Confluence Score (max 5) ────────────────────────────────────
    confluence_score = 0
    htf_trend = weekly_tf["trend"]
    htf_fvg_bias = weekly_tf["fvg_bias"]

    daily_bias = daily_tf["fvg_bias"]

    # Daily ↔ Weekly FVG Alignment
    if daily_bias != "neutral" and daily_bias == htf_fvg_bias:
        confluence_score += 1
    # Daily ↔ Weekly Trend Alignment
    if daily_tf["trend"] != "neutral" and daily_tf["trend"] == htf_trend:
        confluence_score += 1
    # Weekly intern konsistent (Trend = FVG)
    if htf_fvg_bias == htf_trend and htf_trend != "neutral":
        confluence_score += 1
    # Monthly ↔ Weekly Trend Alignment
    if monthly_tf["trend"] != "neutral" and monthly_tf["trend"] == htf_trend:
        confluence_score += 1
    # Alle drei Trends aligned
    if (daily_tf["trend"] == weekly_tf["trend"] == monthly_tf["trend"]
            and daily_tf["trend"] != "neutral"):
        confluence_score += 1

    return {
        "fvgs": fvgs,
        "eqh": eq_levels["eqh"],
        "eql": eq_levels["eql"],
        "confluence_score": confluence_score,
        "confluence_max": 5,
        "htf_trend": htf_trend,
        "htf_fvg_bias": htf_fvg_bias,
        "mtf_matrix": mtf_matrix,
        "stats": {
            "unmitigated_bullish": len(bullish_fvgs),
            "unmitigated_bearish": len(bearish_fvgs),
            "nearest_eqh": min([e["level"] for e in eq_levels["eqh"] if e["level"] > current_price], default=None),
            "nearest_eql": max([e["level"] for e in eq_levels["eql"] if e["level"] < current_price], default=None),
        }
    }

