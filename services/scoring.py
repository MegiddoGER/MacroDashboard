"""
services/scoring.py — Scoring Engine für das MacroDashboard.

Extrahiert aus technical.py für Wiederverwendbarkeit in:
- Einzelanalyse (vollständiger Score)
- Screener (Schnell-Score, batch-fähig)
- Backtesting (historische Score-Berechnung)
- Alerts (Score-basierte Benachrichtigungen)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Gewichtung der Kategorien
# ---------------------------------------------------------------------------

WEIGHTS_FULL = {
    "trend": 0.30,        # SMC, Trend & Marktstruktur
    "volume": 0.25,       # OBV, Order Flow
    "fundamental": 0.20,  # DCF, Value, Margins
    "sentiment": 0.15,    # News NLP Sentiment
    "oscillator": 0.10,   # RSI, Timing
}

WEIGHTS_QUICK = {
    "trend": 0.40,        # Stärker gewichtet ohne Fundamental/Sentiment
    "volume": 0.35,
    "fundamental": 0.0,
    "sentiment": 0.0,     # Zuviel API-Last für Screener
    "oscillator": 0.25,
}


# ---------------------------------------------------------------------------
# Ergebnis-Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class ScoreResult:
    """Standardisiertes Scoring-Ergebnis für eine Aktie."""
    confidence: float = 50.0
    score: int = 0
    score_label: str = "Neutral ➖"
    confidence_label: str = "Gemischte Signale"

    cat_scores: dict = field(default_factory=lambda: {
        "trend": 0, "volume": 0, "fundamental": 0, "sentiment": 0, "oscillator": 0
    })
    cat_max: dict = field(default_factory=lambda: {
        "trend": 0, "volume": 0, "fundamental": 0, "sentiment": 0, "oscillator": 0
    })
    weights: dict = field(default_factory=lambda: dict(WEIGHTS_FULL))

    checklist: list = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    fundamental_text_parts: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Kategorie-Scoring: Trend
# ---------------------------------------------------------------------------

def _score_trend(close, high, low, volume, result: ScoreResult):
    """Bewertet Trend-Indikatoren: SMA 200, SMA-Cross, MACD, ADX."""
    from services.technical import calc_macd, calc_swing_signals

    current_price = float(close.iloc[-1])

    # SMAs berechnen
    sma20_s = close.rolling(20).mean()
    sma50_s = close.rolling(50).mean()
    sma200_s = close.rolling(200).mean()
    sma20 = float(sma20_s.iloc[-1]) if len(close) >= 20 and not np.isnan(sma20_s.iloc[-1]) else None
    sma50 = float(sma50_s.iloc[-1]) if len(close) >= 50 and not np.isnan(sma50_s.iloc[-1]) else None
    sma200 = float(sma200_s.iloc[-1]) if len(close) >= 200 and not np.isnan(sma200_s.iloc[-1]) else None

    trend_macro_bullish = False
    trend_macro_bearish = False

    if sma200:
        result.cat_max["trend"] += 1
        if current_price > sma200:
            result.cat_scores["trend"] += 1
            trend_macro_bullish = True
        else:
            result.cat_scores["trend"] -= 1
            trend_macro_bearish = True

    cross_bullish = False
    cross_bearish = False
    if sma20 and sma50:
        result.cat_max["trend"] += 1
        if sma20 > sma50:
            result.cat_scores["trend"] += 1
            cross_bullish = True
        else:
            result.cat_scores["trend"] -= 1
            cross_bearish = True

    macd_bullish = False
    macd_bearish = False
    macd_line, signal_line, _ = calc_macd(close)
    if not macd_line.dropna().empty and not signal_line.dropna().empty:
        last_macd = float(macd_line.dropna().iloc[-1])
        last_signal = float(signal_line.dropna().iloc[-1])
        result.cat_max["trend"] += 1
        if last_macd > last_signal:
            result.cat_scores["trend"] += 1
            macd_bullish = True
        else:
            result.cat_scores["trend"] -= 1
            macd_bearish = True

    swing = calc_swing_signals(high, low, close, volume)
    adx_val = swing.get("adx") if swing else None
    adx_strong = False
    if adx_val and adx_val > 25:
        adx_strong = True
        result.cat_max["trend"] += 1
        if cross_bullish:
            result.cat_scores["trend"] += 1
        elif cross_bearish:
            result.cat_scores["trend"] -= 1

    # Checklist
    if trend_macro_bullish and cross_bullish:
        result.checklist.append({"Indikator": "Trend (SMAs)", "Wert": "Stark Aufwärts",
            "Signal": "🟢 Intakter Aufwärtstrend (Kurs > SMA 200, Golden Cross)"})
    elif trend_macro_bearish and cross_bullish:
        result.checklist.append({"Indikator": "Trend (SMAs)", "Wert": "Erholung",
            "Signal": "↗️ Kurzfristiges Aufwärtsmomentum im übergeordneten Abwärtstrend"})
    elif trend_macro_bullish and cross_bearish:
        result.checklist.append({"Indikator": "Trend (SMAs)", "Wert": "Korrektur",
            "Signal": "↘️ Kurzfristige Schwäche im übergeordneten Aufwärtstrend"})
    else:
        result.checklist.append({"Indikator": "Trend (SMAs)", "Wert": "Abwärts",
            "Signal": "🔴 Intakter Abwärtstrend (Kurs < SMA 200, Death Cross)"})

    if macd_bullish:
        result.checklist.append({"Indikator": "MACD", "Wert": "MACD > Signal",
            "Signal": "🟢 Bullishes kurzfristiges Momentum"})
    else:
        result.checklist.append({"Indikator": "MACD", "Wert": "MACD < Signal",
            "Signal": "🔴 Bearishes kurzfristiges Momentum"})

    # Signale speichern
    result.signals.update({
        "trend_macro_bullish": trend_macro_bullish,
        "trend_macro_bearish": trend_macro_bearish,
        "cross_bullish": cross_bullish,
        "cross_bearish": cross_bearish,
        "macd_bullish": macd_bullish,
        "macd_bearish": macd_bearish,
        "adx_strong": adx_strong,
        "adx_val": adx_val,
        "sma20_val": sma20,
        "sma50_val": sma50,
        "sma200_val": sma200,
        "current_price": current_price,
    })


# ---------------------------------------------------------------------------
# Kategorie-Scoring: Oszillatoren
# ---------------------------------------------------------------------------

def _score_oscillators(close, high, low, result: ScoreResult):
    """Bewertet Oszillator-Indikatoren: RSI, Stochastic, Bollinger."""
    from services.technical import calc_rsi, calc_stochastic, calc_bollinger

    current_price = float(close.iloc[-1])

    rsi_series = calc_rsi(close, 14)
    rsi_val = float(rsi_series.dropna().iloc[-1]) if rsi_series is not None and not rsi_series.dropna().empty else None

    rsi_overbought = False
    rsi_oversold = False
    if rsi_val:
        result.cat_max["oscillator"] += 1
        if rsi_val > 70:
            result.cat_scores["oscillator"] -= 1
            rsi_overbought = True
            result.checklist.append({"Indikator": "RSI (14)", "Wert": f"{rsi_val:.1f}",
                "Signal": "🔴 Überkauft (Erhöhtes Rückschlagrisiko)"})
        elif rsi_val < 30:
            result.cat_scores["oscillator"] += 1
            rsi_oversold = True
            result.checklist.append({"Indikator": "RSI (14)", "Wert": f"{rsi_val:.1f}",
                "Signal": "🟢 Überverkauft (Chance auf Rebound)"})
        else:
            result.checklist.append({"Indikator": "RSI (14)", "Wert": f"{rsi_val:.1f}",
                "Signal": "➖ Neutraler Bereich"})

    k_line, _ = calc_stochastic(high, low, close)
    if not k_line.dropna().empty:
        last_k = float(k_line.dropna().iloc[-1])
        result.cat_max["oscillator"] += 1
        if last_k > 80:
            result.cat_scores["oscillator"] -= 1
        elif last_k < 20:
            result.cat_scores["oscillator"] += 1

    upper, middle, lower = calc_bollinger(close)
    bollinger_state = "Neutral"
    if not upper.dropna().empty and not lower.dropna().empty:
        last_u = float(upper.dropna().iloc[-1])
        last_l = float(lower.dropna().iloc[-1])
        result.cat_max["oscillator"] += 1
        if current_price >= last_u:
            bollinger_state = "Am oberen Band"
            result.cat_scores["oscillator"] -= 1
            result.checklist.append({"Indikator": "Bollinger Bänder", "Wert": "Am oberen Rand",
                "Signal": "🔴 Kurs technisch überdehnt"})
        elif current_price <= last_l:
            bollinger_state = "Am unteren Band"
            result.cat_scores["oscillator"] += 1
            result.checklist.append({"Indikator": "Bollinger Bänder", "Wert": "Am unteren Rand",
                "Signal": "🟢 Kurs stark abgestraft"})
        else:
            result.checklist.append({"Indikator": "Bollinger Bänder", "Wert": "Im Kanal",
                "Signal": "➖ Normale Volatilität"})

    result.signals.update({
        "rsi_overbought": rsi_overbought,
        "rsi_oversold": rsi_oversold,
        "rsi_val": rsi_val,
        "bollinger_state": bollinger_state,
    })


# ---------------------------------------------------------------------------
# Kategorie-Scoring: Volumen & Order Flow
# ---------------------------------------------------------------------------

def _score_volume(high, low, close, volume, result: ScoreResult):
    """Bewertet Volumen-Indikatoren: OBV, VWAP, POC."""
    from services.technical import calc_order_flow

    current_price = float(close.iloc[-1])
    flow = calc_order_flow(high, low, close, volume)

    obv_bullish = False
    vwap_bullish = False
    poc_bullish = False

    if flow:
        result.cat_max["volume"] += 1
        if flow.get("obv_signal") == "bullish":
            result.cat_scores["volume"] += 1
            obv_bullish = True
            result.checklist.append({"Indikator": "OBV Trend", "Wert": "Steigend",
                "Signal": "🟢 Akkumulation (Kaufdruck vorhanden)"})
        elif flow.get("obv_signal") == "bearish":
            result.cat_scores["volume"] -= 1
            result.checklist.append({"Indikator": "OBV Trend", "Wert": "Fallend",
                "Signal": "🔴 Distribution (Verkaufsdruck vorhanden)"})
        else:
            result.checklist.append({"Indikator": "OBV Trend", "Wert": "Neutral",
                "Signal": "➖ Kein klarer Volumentrend"})

        result.cat_max["volume"] += 1
        if flow.get("vwap_signal") == "bullish":
            result.cat_scores["volume"] += 1
            vwap_bullish = True
            result.checklist.append({"Indikator": "VWAP (Wochen/Monats)", "Wert": "Kurs > VWAP",
                "Signal": "🟢 Käufer dominieren den Durchschnitt"})
        else:
            result.cat_scores["volume"] -= 1
            result.checklist.append({"Indikator": "VWAP (Wochen/Monats)", "Wert": "Kurs < VWAP",
                "Signal": "🔴 Verkäufer dominieren den Durchschnitt"})

        poc = flow.get("poc_price")
        if poc:
            result.cat_max["volume"] += 1
            if current_price > poc:
                result.cat_scores["volume"] += 1
                poc_bullish = True
                result.checklist.append({"Indikator": "Volumen-Cluster (POC)", "Wert": f"{poc:,.2f}",
                    "Signal": "🟢 Kurs oberhalb des stärksten Volumens"})
            else:
                result.cat_scores["volume"] -= 1
                result.checklist.append({"Indikator": "Volumen-Cluster (POC)", "Wert": f"{poc:,.2f}",
                    "Signal": "🔴 Kurs unterhalb des stärksten Volumens"})

    result.signals.update({
        "obv_bullish": obv_bullish,
        "vwap_bullish": vwap_bullish,
        "poc_bullish": poc_bullish,
    })


# ---------------------------------------------------------------------------
# Kategorie-Scoring: SMC (Fair Value Gaps, EQH/EQL)
# ---------------------------------------------------------------------------

def _score_smc(hist, result: ScoreResult):
    """Bewertet SMC-Signale: FVG, EQH, EQL."""
    try:
        from smc.indicators import analyze_smc
        current = float(hist["Close"].iloc[-1])

        smc = analyze_smc(hist)
        if smc and "fvgs" in smc:
            unmitigated_bull = smc["stats"].get("unmitigated_bullish", 0)
            unmitigated_bear = smc["stats"].get("unmitigated_bearish", 0)
            nearest_eqh = smc["stats"].get("nearest_eqh")
            nearest_eql = smc["stats"].get("nearest_eql")

            result.cat_max["volume"] += 1
            if unmitigated_bull > unmitigated_bear:
                result.cat_scores["volume"] += 1
                result.checklist.append({"Indikator": "FVG (Fair Value Gap)",
                    "Wert": f"{unmitigated_bull} bullish / {unmitigated_bear} bearish",
                    "Signal": "Bullisch ↑", "Beitrag": "+1"})
            elif unmitigated_bear > unmitigated_bull:
                result.cat_scores["volume"] -= 1
                result.checklist.append({"Indikator": "FVG (Fair Value Gap)",
                    "Wert": f"{unmitigated_bull} bullish / {unmitigated_bear} bearish",
                    "Signal": "Bearisch ↓", "Beitrag": "-1"})
            else:
                result.checklist.append({"Indikator": "FVG (Fair Value Gap)",
                    "Wert": f"{unmitigated_bull} bullish / {unmitigated_bear} bearish",
                    "Signal": "Neutral ≈", "Beitrag": "0"})

            if nearest_eqh:
                dist_eqh = ((nearest_eqh - current) / current) * 100
                result.checklist.append({"Indikator": "Equal Highs (EQH)",
                    "Wert": f"{nearest_eqh:,.2f} ({dist_eqh:+.1f}%)",
                    "Signal": "Liquiditätsmagnet ⬆️", "Beitrag": "Info"})
            if nearest_eql:
                dist_eql = ((nearest_eql - current) / current) * 100
                result.checklist.append({"Indikator": "Equal Lows (EQL)",
                    "Wert": f"{nearest_eql:,.2f} ({dist_eql:+.1f}%)",
                    "Signal": "Liquiditätsmagnet ⬇️", "Beitrag": "Info"})

            result.signals.update({
                "unmitigated_bull": unmitigated_bull,
                "unmitigated_bear": unmitigated_bear,
                "nearest_eqh": nearest_eqh,
                "nearest_eql": nearest_eql,
            })
    except Exception:
        pass  # SMC-Daten optional


# ---------------------------------------------------------------------------
# Kategorie-Scoring: Fundamentaldaten
# ---------------------------------------------------------------------------

def _score_fundamental(info, ticker, result: ScoreResult):
    """Bewertet Fundamentaldaten: DCF, Bilanz, Insider, Analysten, Dividende."""
    try:
        if not info or not ticker:
            return

        from services.fundamental import (
            calc_dcf_valuation, calc_balance_sheet_quality,
            get_insider_institutional, get_analyst_consensus,
            calc_dividend_analysis
        )

        # DCF
        dcf = calc_dcf_valuation(info)
        if dcf:
            result.cat_max["fundamental"] += 1
            if dcf['upside_pct'] > 20:
                result.cat_scores["fundamental"] += 1
                result.checklist.append({"Indikator": "DCF Fair Value",
                    "Wert": f"{dcf['fair_value']:,.2f} (Upside {dcf['upside_pct']:+.1f}%)",
                    "Signal": "Unterbewertet ↑", "Beitrag": "+1"})
                result.fundamental_text_parts.append(
                    f"Das DCF-Modell sieht die Aktie {dcf['upside_pct']:.0f}% unter ihrem inneren Wert — eine klare fundamentale Unterbewertung.")
            elif dcf['upside_pct'] < -15:
                result.cat_scores["fundamental"] -= 1
                result.checklist.append({"Indikator": "DCF Fair Value",
                    "Wert": f"{dcf['fair_value']:,.2f} (Downside {dcf['upside_pct']:+.1f}%)",
                    "Signal": "Überbewertet ↓", "Beitrag": "-1"})
                result.fundamental_text_parts.append(
                    f"Der DCF-basierte Fair Value liegt {abs(dcf['upside_pct']):.0f}% unter dem aktuellen Kurs — fundamental scheint die Aktie überbewertet.")
            else:
                result.checklist.append({"Indikator": "DCF Fair Value",
                    "Wert": f"{dcf['fair_value']:,.2f} ({dcf['upside_pct']:+.1f}%)",
                    "Signal": "Fair bewertet ≈", "Beitrag": "0"})

        # Bilanzqualität
        balance = calc_balance_sheet_quality(info)
        if balance:
            result.cat_max["fundamental"] += 1
            if balance['score'] >= 2:
                result.cat_scores["fundamental"] += 1
                result.checklist.append({"Indikator": "Bilanzqualität", "Wert": balance['label'],
                    "Signal": "Solide ↑", "Beitrag": "+1"})
                result.fundamental_text_parts.append(
                    "Die Bilanz ist solide — niedrige Verschuldung und gesunde Liquidität geben Sicherheit.")
            elif balance['score'] < 0:
                result.cat_scores["fundamental"] -= 1
                result.checklist.append({"Indikator": "Bilanzqualität", "Wert": balance['label'],
                    "Signal": "Kritisch ↓", "Beitrag": "-1"})
                result.fundamental_text_parts.append(
                    "Die Bilanz ist angespannt — hohe Verschuldung erhöht das Risiko bei Zinserhöhungen oder Umsatzrückgängen.")
            else:
                result.checklist.append({"Indikator": "Bilanzqualität", "Wert": balance['label'],
                    "Signal": "Akzeptabel ≈", "Beitrag": "0"})

        # Insider-Sentiment
        insider = get_insider_institutional(ticker)
        if insider and insider.get('has_insider_data'):
            result.cat_max["fundamental"] += 1
            if insider['net_buys'] > insider['net_sells'] and insider['net_buys'] >= 2:
                result.cat_scores["fundamental"] += 1
                result.checklist.append({"Indikator": "Insider-Sentiment",
                    "Wert": f"{insider['net_buys']} Käufe / {insider['net_sells']} Verkäufe",
                    "Signal": "Netto-Käufe ↑", "Beitrag": "+1"})
                result.fundamental_text_parts.append(
                    "Insider kaufen aktiv eigene Aktien — ein starkes Vertrauenssignal des Managements.")
            elif insider['net_sells'] > insider['net_buys'] + 2:
                result.cat_scores["fundamental"] -= 1
                result.checklist.append({"Indikator": "Insider-Sentiment",
                    "Wert": f"{insider['net_buys']} Käufe / {insider['net_sells']} Verkäufe",
                    "Signal": "Netto-Verkäufe ↓", "Beitrag": "-1"})
                result.fundamental_text_parts.append(
                    "Auffällig viele Insider-Verkäufe — das Management scheint Gewinne zu sichern.")
            else:
                result.checklist.append({"Indikator": "Insider-Sentiment",
                    "Wert": f"{insider['net_buys']} K / {insider['net_sells']} V",
                    "Signal": "Neutral ≈", "Beitrag": "0"})

        # Analysten-Konsens
        analyst = get_analyst_consensus(ticker)
        if analyst and analyst.get('recommendation_mean'):
            rec_mean = analyst['recommendation_mean']
            rec_label = analyst.get('recommendation', '—')
            result.cat_max["fundamental"] += 1
            if rec_mean <= 2.0:
                result.cat_scores["fundamental"] += 1
                result.checklist.append({"Indikator": "Analysten-Konsens",
                    "Wert": f"{rec_label} ({rec_mean}/5)",
                    "Signal": "Strong Buy ↑", "Beitrag": "+1"})
                result.fundamental_text_parts.append(
                    f"Die Wall Street ist klar bullisch (Konsens: {rec_label}, {analyst.get('num_analysts', '?')} Analysten).")
            elif rec_mean >= 3.5:
                result.cat_scores["fundamental"] -= 1
                result.checklist.append({"Indikator": "Analysten-Konsens",
                    "Wert": f"{rec_label} ({rec_mean}/5)",
                    "Signal": "Hold/Sell ↓", "Beitrag": "-1"})
                result.fundamental_text_parts.append(
                    f"Analysten sind zurückhaltend bis negativ (Konsens: {rec_label}).")
            else:
                result.checklist.append({"Indikator": "Analysten-Konsens",
                    "Wert": f"{rec_label} ({rec_mean}/5)",
                    "Signal": "Neutral ≈", "Beitrag": "0"})

        # Dividenden-Nachhaltigkeit
        div_data = calc_dividend_analysis(ticker)
        if div_data and div_data.get('has_dividends'):
            result.cat_max["fundamental"] += 1
            if div_data['payout_ratio'] > 0 and div_data['payout_ratio'] < 60 and div_data['streak'] >= 5:
                result.cat_scores["fundamental"] += 1
                result.checklist.append({"Indikator": "Dividende",
                    "Wert": f"Rendite {div_data['current_yield']:.1f}%, Payout {div_data['payout_ratio']:.0f}%, Streak {div_data['streak']}J",
                    "Signal": "Nachhaltig ↑", "Beitrag": "+1"})
                result.fundamental_text_parts.append(
                    f"Die Dividende ist nachhaltig (Payout {div_data['payout_ratio']:.0f}%) und wächst seit {div_data['streak']} Jahren.")
            elif div_data['payout_ratio'] > 85:
                result.checklist.append({"Indikator": "Dividende",
                    "Wert": f"Payout {div_data['payout_ratio']:.0f}% (hoch!)",
                    "Signal": "Risiko ⚠️", "Beitrag": "0"})
                result.fundamental_text_parts.append(
                    f"Achtung: Die Ausschüttungsquote ({div_data['payout_ratio']:.0f}%) ist sehr hoch — die Dividende könnte unter Druck geraten.")
    except Exception:
        pass  # Fundamentaldaten optional


# ---------------------------------------------------------------------------
# Sentiment (News NLP)
# ---------------------------------------------------------------------------

def _score_sentiment(ticker: str, result: ScoreResult):
    """Bewertet das News-Sentiment mittels VADER NLP."""
    if not ticker:
        result.cat_max["sentiment"] += 1
        return

    from services.sentiment import analyze_ticker_news
    try:
        sent_data = analyze_ticker_news(ticker)
        has_news = sent_data.get("n_articles", 0) > 0
    except Exception:
        has_news = False
        sent_data = {}

    if not has_news:
        result.cat_max["sentiment"] += 1
        return

    result.cat_max["sentiment"] += 4
    avg_c = sent_data.get("avg_compound", 0.0)
    
    # +2 bis -2 Scoring für Sentiment
    if avg_c >= 0.15:
        score = 2
        sig = "Stark Bullish 🔥"
    elif avg_c >= 0.05:
        score = 1
        sig = "Bullish 🟢"
    elif avg_c <= -0.15:
        score = -2
        sig = "Stark Bearish 🧨"
    elif avg_c <= -0.05:
        score = -1
        sig = "Bearish 🔴"
    else:
        score = 0
        sig = "Neutral ➖"

    result.cat_scores["sentiment"] += score
    result.checklist.append({"Indikator": "News Sentiment",
                             "Wert": f"{sent_data['n_articles']} News (∅ {avg_c:.2f})",
                             "Signal": sig, "Beitrag": f"{score:+}"})
                             
    # Speichere das Sentiment im Result für die Euphorie-Logik
    result.signals["sentiment_avg"] = avg_c


# ---------------------------------------------------------------------------
# Score-Finalisierung
# ---------------------------------------------------------------------------

def _finalize_score(result: ScoreResult):
    """Berechnet den gewichteten Confidence-Score und Labels inkl. Euphorie-Falle."""
    weighted_score = 0.0
    for cat, weight in result.weights.items():
        mx = result.cat_max.get(cat, 0)
        if mx > 0:
            val = result.cat_scores.get(cat, 0)
            normalized = val / mx
        else:
            normalized = 0.0
        weighted_score += normalized * weight

    # Basis-Confidence (0 bis 100)
    confidence = round((weighted_score + 1) / 2 * 100, 1)

    # 🧨 Contrarian-Logik: Euphorie-Falle!
    # Wenn Sentiment extrem hoch (>0.15) ist, aber der RSI auf Überkauft (>70) steht,
    # ist das ein klassisches "Sell the News" oder Top-Building Signal.
    avg_c = result.signals.get("sentiment_avg", 0.0)
    rsi_overbought = result.signals.get("rsi_overbought", False)
    
    if avg_c >= 0.15 and rsi_overbought:
        confidence -= 15.0  # Schwerer Malus
        result.checklist.append({"Indikator": "Contrarian-Warnung 🧨",
                                 "Wert": "News extrem Bullish + RSI > 70",
                                 "Signal": "Euphorie-Falle", "Beitrag": "-15% Conf"})

    confidence = max(0.0, min(100.0, confidence))
    score = round(weighted_score * 10)

    if confidence >= 75:
        score_label = "Starkes Kaufsignal 🟢"
        confidence_label = "Hohe Confidence"
    elif confidence >= 60:
        score_label = "Kauftendenz ↗️"
        confidence_label = "Gute Confidence"
    elif confidence >= 45:
        score_label = "Neutral ➖"
        confidence_label = "Gemischte Signale"
    elif confidence >= 30:
        score_label = "Verkaufstendenz ↘️"
        confidence_label = "Schwache Confidence"
    else:
        score_label = "Starkes Verkaufssignal 🔴"
        confidence_label = "Sehr Schwache Confidence"

    result.confidence = confidence
    result.score = score
    result.score_label = score_label
    result.confidence_label = confidence_label


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def calc_quick_score(hist: pd.DataFrame) -> ScoreResult | None:
    """Schnelle Score-Berechnung nur aus OHLCV-Preisdaten."""
    if hist is None or hist.empty or len(hist) < 50:
        return None

    result = ScoreResult()
    result.weights = dict(WEIGHTS_QUICK)

    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    volume = hist["Volume"]

    _score_trend(close, high, low, volume, result)
    _score_oscillators(close, high, low, result)
    _score_volume(high, low, close, volume, result)
    _finalize_score(result)

    return result


def calc_full_score(hist: pd.DataFrame, info: dict = None,
                    ticker: str = None) -> ScoreResult | None:
    """Vollständige Score-Berechnung inkl. Fundamentaldaten, SMC und Sentiment."""
    if hist is None or hist.empty or len(hist) < 200:
        return None

    result = ScoreResult()
    result.weights = dict(WEIGHTS_FULL)

    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    volume = hist["Volume"]

    _score_trend(close, high, low, volume, result)
    _score_oscillators(close, high, low, result)
    _score_volume(high, low, close, volume, result)
    _score_smc(hist, result)
    _score_fundamental(info, ticker, result)
    
    # Neu in Phase 4: Sentiment
    _score_sentiment(ticker, result)
    
    _finalize_score(result)

    if ticker:
        try:
            from services.signal_history import record_signal
            current_price = float(close.iloc[-1])
            record_signal(ticker, result, current_price)
        except Exception as e:
            print(f"Warning: Failed to record signal for {ticker} - {e}")

    return result
