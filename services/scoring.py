"""
services/scoring.py — Scoring Engine für das MacroDashboard.

Extrahiert aus technical.py für Wiederverwendbarkeit in:
- Einzelanalyse (vollständiger Score)
- Screener (Schnell-Score, batch-fähig)
- Backtesting (historische Score-Berechnung)
- Alerts (Score-basierte Benachrichtigungen)
"""

import warnings
import pandas as pd
import numpy as np
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Gewichtung der Kategorien
# ---------------------------------------------------------------------------

WEIGHTS_FULL = {
    "trend": 0.30,        # SMC, Trend & Marktstruktur
    "volume": 0.25,       # OBV, Order Flow
    "fundamental": 0.30,  # DCF, Value, Margins, Insider, Analysten
    "sentiment": 0.05,    # News NLP Sentiment (reduziert — VADER hat begrenzte Prognosekraft)
    "oscillator": 0.10,   # RSI, Timing
}

WEIGHTS_QUICK = {
    "trend": 0.15,        # Reduziert: Trendfolger reagieren spät
    "volume": 0.20,       # Optimiert: Order Flow behält Relevanz
    "fundamental": 0.0,
    "sentiment": 0.0,     # Zuviel API-Last für Screener
    "oscillator": 0.65,   # Dominant für Quick-Score Forward Returns (Mean Reversion)
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
        # MACD wird als Info-Indikator geführt, NICHT im Score gezählt
        # (vermeidet Redundanz mit SMA 20/50 Cross — beide messen kurzfristiges Momentum)
        if last_macd > last_signal:
            macd_bullish = True
        else:
            macd_bearish = True

    # ... (Rest der Trend-Logik bleibt)
    swing = calc_swing_signals(high, low, close, volume)
    adx_val = swing.get("adx") if swing else None
    adx_strong = False
    if adx_val and adx_val > 25:
        adx_strong = True
        # ADX > 25 bestätigt Trendstärke — wird als Info geloggt,
        # aber KEIN eigenes cat_max/cat_scores (vermeidet Doppelzählung mit SMA-Cross)
        result.checklist.append({"Indikator": "ADX", "Wert": f"{adx_val:.0f}",
            "Signal": "🟢 Starker Trend bestätigt", "Beitrag": "Info"})
    elif adx_val and adx_val < 20:
        # Seitwärtsmarkt: Info-Indikator (kein Score-Impact — symmetrisch mit ADX > 25)
        result.checklist.append({"Indikator": "ADX", "Wert": f"{adx_val:.0f}",
            "Signal": "🟡 Schwacher Trend / Seitwärts — Trend-Signale weniger verlässlich", "Beitrag": "Info"})
    elif adx_val:
        result.checklist.append({"Indikator": "ADX", "Wert": f"{adx_val:.0f}",
            "Signal": "➖ Moderater Trend", "Beitrag": "0"})

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
            "Signal": "🟢 Bullishes kurzfristiges Momentum", "Beitrag": "Info"})
    else:
        result.checklist.append({"Indikator": "MACD", "Wert": "MACD < Signal",
            "Signal": "🔴 Bearishes kurzfristiges Momentum", "Beitrag": "Info"})

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
                "Signal": "➖ Neutraler Bereich", "Beitrag": "0"})

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
                "Signal": "➖ Normale Volatilität", "Beitrag": "0"})

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
            result.checklist.append({"Indikator": "VWMA (20T)", "Wert": "Kurs > VWMA",
                "Signal": "🟢 Käufer dominieren den Durchschnitt"})
        else:
            result.cat_scores["volume"] -= 1
            result.checklist.append({"Indikator": "VWMA (20T)", "Wert": "Kurs < VWMA",
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

            result.cat_max["trend"] += 1
            if unmitigated_bull > unmitigated_bear:
                result.cat_scores["trend"] += 1
                result.checklist.append({"Indikator": "FVG (Fair Value Gap)",
                    "Wert": f"{unmitigated_bull} bullish / {unmitigated_bear} bearish",
                    "Signal": "Bullisch ↑", "Beitrag": "+1"})
            elif unmitigated_bear > unmitigated_bull:
                result.cat_scores["trend"] -= 1
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
    except Exception as exc:
        warnings.warn(f"_score_smc: SMC-Analyse fehlgeschlagen: {exc}")


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
            elif dcf['upside_pct'] < -20:
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

        # Insider-Sentiment (Corporate Insider — stärkster Einfluss)
        insider = get_insider_institutional(ticker)
        if insider and insider.get('has_summary'):
            buys = insider['purchases_count']
            sells = insider['sales_count']
            net_s = insider['net_shares']
            result.cat_max["fundamental"] += 1
            if buys > sells and net_s > 0 and buys >= 2:
                result.cat_scores["fundamental"] += 1
                result.checklist.append({"Indikator": "Insider-Sentiment",
                    "Wert": f"{buys} Käufe / {sells} Verkäufe (Netto: {net_s:+,} Aktien)".replace(",", "."),
                    "Signal": "Netto-Käufe ↑", "Beitrag": "+1"})
                result.fundamental_text_parts.append(
                    "Insider kaufen aktiv eigene Aktien — ein starkes Vertrauenssignal des Managements.")
            elif sells > buys and net_s < 0 and sells >= 2:
                result.cat_scores["fundamental"] -= 1
                result.checklist.append({"Indikator": "Insider-Sentiment",
                    "Wert": f"{buys} Käufe / {sells} Verkäufe (Netto: {net_s:+,} Aktien)".replace(",", "."),
                    "Signal": "Netto-Verkäufe ↓", "Beitrag": "-1"})
                result.fundamental_text_parts.append(
                    "Auffällig viele Insider-Verkäufe — das Management scheint Gewinne zu sichern.")
            else:
                result.checklist.append({"Indikator": "Insider-Sentiment",
                    "Wert": f"{buys} K / {sells} V",
                    "Signal": "Neutral ≈", "Beitrag": "0"})

        # ── Kongress-Trades — leichter Einfluss (±0.5) ──
        # Nur Trades mit extrem schneller Meldung (<15 Tage) fließen ins Scoring ein.
        # Rationale: Schnelle Disclosure = Dringlichkeit, hat laut Forschung leichtes Alpha.
        if insider and insider.get('has_congress_data') and insider.get('congress_trades'):
            try:
                from services.quiver import _parse_amount_numeric
                from services.congress_mapping import check_conflict_of_interest

                congress_trades = insider['congress_trades']
                ticker_sector = info.get('sector', '') if info else ''

                fast_buys = 0
                fast_sells = 0
                coi_detected = False
                coi_committee = None
                coi_politician = None

                for t in congress_trades:
                    lag = t.get('disclosure_lag')
                    trade_type = (t.get('trade_type') or '').lower()
                    is_buy = 'purchase' in trade_type or 'buy' in trade_type
                    is_sell = 'sale' in trade_type or 'sell' in trade_type

                    # Urgency-Signal: Lag < 15 Tage
                    if lag is not None and lag < 15:
                        if is_buy:
                            fast_buys += 1
                        elif is_sell:
                            fast_sells += 1

                    # Committee Conflict of Interest (jeder Trade wird geprüft)
                    if not coi_detected and ticker_sector:
                        is_coi, matched = check_conflict_of_interest(
                            t.get('name', ''), ticker_sector
                        )
                        if is_coi:
                            coi_detected = True
                            coi_committee = matched
                            coi_politician = t.get('name', '')

                # Scoring: Kongress Urgency (±0.5)
                if fast_buys > 0 or fast_sells > 0:
                    result.cat_max["fundamental"] += 1
                    if fast_buys > fast_sells:
                        result.cat_scores["fundamental"] += 0.5
                        result.checklist.append({"Indikator": "🏛️ Kongress (Urgency)",
                            "Wert": f"{fast_buys} schnelle Käufe / {fast_sells} schnelle Verkäufe (<15T Lag)",
                            "Signal": "Leicht bullisch ↑ (⚠️ Look-Ahead Bias Risiko bei Backtests)", "Beitrag": "+0.5"})
                    elif fast_sells > fast_buys:
                        result.cat_scores["fundamental"] -= 0.5
                        result.checklist.append({"Indikator": "🏛️ Kongress (Urgency)",
                            "Wert": f"{fast_buys} schnelle Käufe / {fast_sells} schnelle Verkäufe (<15T Lag)",
                            "Signal": "Leicht bearisch ↓ (⚠️ Look-Ahead Bias Risiko bei Backtests)", "Beitrag": "-0.5"})
                    else:
                        result.checklist.append({"Indikator": "🏛️ Kongress (Urgency)",
                            "Wert": f"{fast_buys} K / {fast_sells} V (<15T Lag)",
                            "Signal": "Neutral ≈", "Beitrag": "0"})
                else:
                    result.checklist.append({"Indikator": "🏛️ Kongress",
                        "Wert": f"{len(congress_trades)} Trades (keine <15T)",
                        "Signal": "Kein Urgency-Signal", "Beitrag": "Info"})

                # Scoring: Committee Conflict of Interest (Ausschließlich Info, kein Score wg. Ethik/Bias)
                if coi_detected:
                    net_congress = fast_buys - fast_sells
                    if net_congress > 0:
                        result.checklist.append({"Indikator": "🔴 Interessenkonflikt (COI)",
                            "Wert": f"{coi_politician} sitzt im {coi_committee}-Ausschuss",
                            "Signal": f"Kauf trotz Aufsicht über {ticker_sector} ↑", "Beitrag": "Info"})
                    elif net_congress < 0:
                        result.checklist.append({"Indikator": "🔴 Interessenkonflikt (COI)",
                            "Wert": f"{coi_politician} sitzt im {coi_committee}-Ausschuss",
                            "Signal": f"Verkauf trotz Aufsicht über {ticker_sector} ↓", "Beitrag": "Info"})
                    else:
                        result.checklist.append({"Indikator": "🔴 Interessenkonflikt (COI)",
                            "Wert": f"{coi_politician} ({coi_committee})",
                            "Signal": "Erkannt — Netto neutral", "Beitrag": "Info"})
            except Exception as exc:
                warnings.warn(f"_score_fundamental: Kongress-Scoring fehlgeschlagen: {exc}")

        # ── Institutioneller Anteil — sehr leichter Einfluss (+0.5) ──
        # Hoher Inst. Anteil (>70%) = Smart-Money-Qualitätsstempel, kein Timing-Signal.
        if insider and insider.get('institutional_pct'):
            inst_pct = insider['institutional_pct']
            result.cat_max["fundamental"] += 1
            if inst_pct > 70:
                result.cat_scores["fundamental"] += 0.5
                result.checklist.append({"Indikator": "🏦 Institutioneller Anteil",
                    "Wert": f"{inst_pct:.1f}%",
                    "Signal": "Hoher Smart-Money-Anteil ↑", "Beitrag": "+0.5"})
            elif inst_pct < 20:
                result.checklist.append({"Indikator": "🏦 Institutioneller Anteil",
                    "Wert": f"{inst_pct:.1f}%",
                    "Signal": "Niedrig (Micro-/Small-Cap typisch)", "Beitrag": "0"})
            else:
                result.checklist.append({"Indikator": "🏦 Institutioneller Anteil",
                    "Wert": f"{inst_pct:.1f}%",
                    "Signal": "Normal ≈", "Beitrag": "0"})

        # Analysten-Konsens
        analyst = get_analyst_consensus(ticker)
        if analyst and analyst.get('recommendation_mean'):
            rec_mean = analyst['recommendation_mean']
            rec_label = analyst.get('recommendation', '—')
            result.cat_max["fundamental"] += 1
            if rec_mean <= 1.8:
                result.cat_scores["fundamental"] += 1
                result.checklist.append({"Indikator": "Analysten-Konsens",
                    "Wert": f"{rec_label} ({rec_mean}/5)",
                    "Signal": "Strong Buy ↑", "Beitrag": "+1"})
                result.fundamental_text_parts.append(
                    f"Die Wall Street ist klar bullisch (Konsens: {rec_label}, {analyst.get('num_analysts', '?')} Analysten).")
            elif rec_mean >= 3.2:
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
                result.cat_scores["fundamental"] -= 1
                result.checklist.append({"Indikator": "Dividende",
                    "Wert": f"Payout {div_data['payout_ratio']:.0f}% (hoch!)",
                    "Signal": "Nicht nachhaltig ↓", "Beitrag": "-1"})
                result.fundamental_text_parts.append(
                    f"Achtung: Die Ausschüttungsquote ({div_data['payout_ratio']:.0f}%) ist sehr hoch — die Dividende könnte unter Druck geraten.")
    except Exception as exc:
        warnings.warn(f"_score_fundamental: Fundamentaldaten fehlgeschlagen: {exc}")


# ---------------------------------------------------------------------------
# Sentiment (News NLP)
# ---------------------------------------------------------------------------

def _score_sentiment(ticker: str, result: ScoreResult):
    """Bewertet das News-Sentiment mittels VADER NLP + Earnings Surprise.

    Zwei Signalquellen:
    1. VADER-NLP auf aktuelle News-Headlines (cat_max += 2, Score ±2)
    2. Letztes Earnings-Ergebnis wenn < 90 Tage alt (cat_max += 1, Score ±1)
    """
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

    # ── Signal 1: VADER NLP auf News ──
    # cat_max = 2: Score-Bereich [-2, +2], Normalisiert auf [-1, +1]
    result.cat_max["sentiment"] += 2
    avg_c = sent_data.get("avg_compound", 0.0)

    # +2 bis -2 Scoring für Sentiment (symmetrisch mit cat_max=2)
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

    # ── Signal 2: Earnings Surprise (letztes Quartal) ──
    # Ergänzt VADER, überstimmt es nicht (cat_max += 1, Score ±1)
    try:
        from services.earnings import get_earnings_history
        from datetime import datetime, timedelta

        ep = get_earnings_history(ticker)
        if ep and ep.events:
            latest = ep.events[0]  # Neuester Event (sortiert nach Datum)
            # Alter des Events berechnen
            event_date = latest.date
            if hasattr(event_date, 'tzinfo') and event_date.tzinfo:
                event_date = event_date.replace(tzinfo=None)
            event_age_days = (datetime.now() - event_date).days

            if 0 <= event_age_days <= 90 and latest.surprise_pct is not None:
                result.cat_max["sentiment"] += 1
                if latest.surprise_pct > 5.0:
                    # Starker Beat → bullishes Signal
                    result.cat_scores["sentiment"] += 1
                    result.checklist.append({
                        "Indikator": "Earnings Surprise",
                        "Wert": f"{latest.quarter}: {latest.surprise_pct:+.1f}%",
                        "Signal": "Beat 🟢",
                        "Beitrag": "+1"
                    })
                elif latest.surprise_pct < -5.0:
                    # Starker Miss → bearishes Signal
                    result.cat_scores["sentiment"] -= 1
                    result.checklist.append({
                        "Indikator": "Earnings Surprise",
                        "Wert": f"{latest.quarter}: {latest.surprise_pct:+.1f}%",
                        "Signal": "Miss 🔴",
                        "Beitrag": "-1"
                    })
                else:
                    # Moderate Surprise (±5%) → kein Score, aber Info
                    result.checklist.append({
                        "Indikator": "Earnings Surprise",
                        "Wert": f"{latest.quarter}: {latest.surprise_pct:+.1f}%",
                        "Signal": "Inline ➖",
                        "Beitrag": "0"
                    })
                    
                # Speichere für ggf. weitere Logik
                result.signals["last_earnings_surprise"] = latest.surprise_pct
                result.signals["last_earnings_age_days"] = event_age_days
    except Exception as exc:
        warnings.warn(f"_score_sentiment: Earnings-Integration fehlgeschlagen: {exc}")


# ---------------------------------------------------------------------------
# Score-Finalisierung
# ---------------------------------------------------------------------------

def _finalize_score(result: ScoreResult):
    """Berechnet den gewichteten Confidence-Score und Labels inkl. Euphorie-Falle.

    Normalisierung:
    - Jede Kategorie hat cat_scores ∈ [-cat_max, +cat_max]
    - normalized = val / mx  →  ∈ [-1.0, +1.0]  für jede Kategorie
    - weighted_score = Σ(normalized × weight)  →  ∈ [-1.0, +1.0] da Σweights = 1.0
    - confidence = (weighted_score + 1) / 2 × 100  →  [0, 100]
    """
    weighted_score = 0.0
    for cat, weight in result.weights.items():
        mx = result.cat_max.get(cat, 0)
        if mx > 0:
            val = result.cat_scores.get(cat, 0)
            # Clamp auf [-mx, +mx] um Überläufe abzufangen
            val = max(-mx, min(mx, val))
            normalized = val / mx  # ∈ [-1.0, +1.0]
        else:
            normalized = 0.0
        weighted_score += normalized * weight

    # Clamp weighted_score auf [-1, +1] (Sicherheit gegen Fließkomma-Drift)
    weighted_score = max(-1.0, min(1.0, weighted_score))

    # 🧨 Contrarian-Logik: Euphorie-Falle!
    # Operiert auf dem gewichteten Score VOR der Confidence-Umrechnung,
    # damit der Malus proportional zum Scoring-System wirkt.
    avg_c = result.signals.get("sentiment_avg", 0.0)
    rsi_overbought = result.signals.get("rsi_overbought", False)

    if avg_c >= 0.15 and rsi_overbought:
        weighted_score -= 0.30  # ≈ 15% Confidence-Malus (0.30 auf [-1,+1] Skala)
        weighted_score = max(-1.0, weighted_score)
        result.checklist.append({"Indikator": "Contrarian-Warnung 🧨",
                                 "Wert": "News extrem Bullish + RSI > 70",
                                 "Signal": "Euphorie-Falle", "Beitrag": "-15% Conf"})

    # Basis-Confidence: [-1, +1] → [0, 100]
    confidence = round((weighted_score + 1.0) / 2.0 * 100.0, 1)
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


# ---------------------------------------------------------------------------
# Positions-Analyse: Positionsbezogener Score + Handlungsempfehlung
# ---------------------------------------------------------------------------

def generate_position_relevance(checklist: list, position_data: dict) -> list:
    """Generiert positionsspezifische Relevanznotizen pro Indikator.

    Args:
        checklist: Bestehende Indikatoren-Checkliste aus ScoreResult
        position_data: Dict mit buy_price, current_price, pnl_pct, holding_days

    Returns:
        Erweiterte Checkliste mit 'Positionsrelevanz'-Schlüssel pro Eintrag
    """
    pnl_pct = position_data.get("pnl_pct", 0)
    holding_days = position_data.get("holding_days", 0)
    buy_price = position_data.get("buy_price", 0)
    current_price = position_data.get("current_price", 0)

    in_profit = pnl_pct > 0
    deep_profit = pnl_pct > 20
    in_loss = pnl_pct < 0
    deep_loss = pnl_pct < -15

    enriched = []
    for item in checklist:
        entry = dict(item)  # Kopie
        indicator = entry.get("Indikator", "")

        # Positionsrelevanz je nach Indikator generieren
        if "RSI" in indicator:
            wert = entry.get("Wert", "")
            if "Überkauft" in entry.get("Signal", ""):
                if in_profit:
                    entry["Positionsrelevanz"] = "Gewinne absichern — RSI-Signal deutet auf Rücksetzer hin."
                else:
                    entry["Positionsrelevanz"] = "Trotz Verlust kurzfristig überkauft — Erholung könnte auslaufen."
            elif "Überverkauft" in entry.get("Signal", ""):
                if in_loss:
                    entry["Positionsrelevanz"] = "Position im Verlust, aber überverkauft — Rebound-Chance."
                else:
                    entry["Positionsrelevanz"] = "Position im Gewinn, überverkauft — möglicher Nachkauf-Moment."
            else:
                entry["Positionsrelevanz"] = "Position im neutralen Bereich — kein unmittelbarer Handlungsdruck."

        elif "MACD" in indicator:
            if "Bullish" in entry.get("Signal", "") or "🟢" in entry.get("Signal", ""):
                if in_profit:
                    entry["Positionsrelevanz"] = "Momentum unterstützt die Position — Gewinne laufen lassen."
                else:
                    entry["Positionsrelevanz"] = "Momentum dreht positiv — Erholung der Position möglich."
            else:
                if in_profit:
                    entry["Positionsrelevanz"] = "Momentum dreht gegen die Position — Stop-Loss überprüfen."
                else:
                    entry["Positionsrelevanz"] = "Momentum weiter negativ — engmaschige Überwachung empfohlen."

        elif "Trend" in indicator and "SMA" in indicator:
            if "Aufwärts" in entry.get("Wert", ""):
                entry["Positionsrelevanz"] = "Position steht auf solidem Trendunterbau seit Einstieg."
            elif "Abwärts" in entry.get("Wert", ""):
                if in_loss:
                    entry["Positionsrelevanz"] = "Abwärtstrend bestätigt Verluste — Exit-Strategie prüfen."
                else:
                    entry["Positionsrelevanz"] = "Trotz Gewinn: Übergeordneter Trend negativ — Absicherung sinnvoll."
            elif "Korrektur" in entry.get("Wert", ""):
                entry["Positionsrelevanz"] = "Kurzfristige Schwäche — ggf. Nachkauf-Gelegenheit im Aufwärtstrend."
            else:
                entry["Positionsrelevanz"] = "Erholungsversuch — Bestätigung abwarten vor Aufstockung."

        elif "OBV" in indicator:
            if "Akkumulation" in entry.get("Signal", "") or "🟢" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Institutionelle Käufe stützen die Position."
            elif "Distribution" in entry.get("Signal", "") or "🔴" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Abfluss erkennbar — Smart Money verkauft. Position im Auge behalten."
            else:
                entry["Positionsrelevanz"] = "Volumentrend neutral — kein Handlungssignal."

        elif "Bollinger" in indicator:
            if "oberen" in entry.get("Signal", "").lower():
                entry["Positionsrelevanz"] = "Kurs technisch überdehnt — Teilverkauf zur Gewinnsicherung erwägen."
            elif "unteren" in entry.get("Signal", "").lower():
                entry["Positionsrelevanz"] = "Kurs stark abgestraft — möglicher Einstiegspunkt für Aufstockung."
            else:
                entry["Positionsrelevanz"] = "Normale Volatilität — kein Handlungsbedarf."

        elif "DCF" in indicator:
            if "Unterbewertet" in entry.get("Signal", ""):
                if buy_price > 0 and current_price < buy_price:
                    entry["Positionsrelevanz"] = "Fundamentales Upside trotz Kursverlust — langfristiges Halten gerechtfertigt."
                else:
                    entry["Positionsrelevanz"] = "Einstieg zum fairen Wert bestätigt — Position fundamental gut positioniert."
            elif "Überbewertet" in entry.get("Signal", ""):
                if in_profit:
                    entry["Positionsrelevanz"] = "Gewinnmitnahme fundamental gestützt — Kurs über Fair Value."
                else:
                    entry["Positionsrelevanz"] = "Position sowohl im Verlust als auch überbewertet — kritische Lage."
            else:
                entry["Positionsrelevanz"] = "Fair bewertet — kein fundamentaler Handlungsdruck."

        elif "Bilanz" in indicator:
            if "Solide" in entry.get("Signal", "") or "↑" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Starke Bilanz reduziert das Downside-Risiko der Position."
            elif "Kritisch" in entry.get("Signal", "") or "↓" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Schwache Bilanz erhöht das Risiko — Position engmaschig überwachen."
            else:
                entry["Positionsrelevanz"] = "Bilanz akzeptabel — kein zusätzliches Risiko für die Position."

        elif "Insider" in indicator and "Kongress" not in indicator and "Institutionell" not in indicator:
            if "Netto-Käufe" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Insider kaufen — unterstützt die Halteentscheidung."
            elif "Netto-Verkäufe" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Insider verkaufen — Warnsignal für bestehende Positionen."
            else:
                entry["Positionsrelevanz"] = "Insider-Aktivität neutral — kein zusätzliches Signal."

        elif "Analysten" in indicator:
            if "Strong Buy" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Analyst:innen bestätigen Halteentscheidung."
            elif "Hold/Sell" in entry.get("Signal", ""):
                if in_profit:
                    entry["Positionsrelevanz"] = "Analysten zurückhaltend — Teilverkauf zum Sichern von Gewinnen erwägen."
                else:
                    entry["Positionsrelevanz"] = "Analysten negativ — Exit-Strategie definieren."
            else:
                entry["Positionsrelevanz"] = "Analysten-Konsens neutral — kein Handlungsdruck."

        elif "FVG" in indicator:
            if "Bullisch" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Offene FVGs als Support — Position hat strukturelle Absicherung."
            elif "Bearisch" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Bearische FVGs als Widerstand — Kursrückgang möglich."
            else:
                entry["Positionsrelevanz"] = "FVG-Balance ausgeglichen — neutral für die Position."

        else:
            # Default: keine spezifische Relevanz
            entry["Positionsrelevanz"] = ""

        enriched.append(entry)
    return enriched


def calc_position_score(
    score_result,
    position_data: dict,
    dcf_data: dict | None = None,
    volume_modifier: str = "mittel",
) -> dict:
    """Generiert positionsbezogene strategische Handlungsempfehlung.

    NEU: Kernlogik der Positions-Analyse.

    Args:
        score_result: Bestehender ScoreResult von calc_full_score()
        position_data: Dict mit:
            buy_price, quantity, buy_date, current_price,
            stop_loss, take_profit, pnl_eur, pnl_pct, holding_days,
            annualized_return, total_invested, current_value,
            sma20_dist, sma50_dist, sma200_dist, atr_val
        dcf_data: DCF-Bewertungsdaten (optional)
        volume_modifier: "klein", "mittel", "gross"

    Returns:
        Dict mit score, action, reasoning, steps, modifier_badge
    """
    confidence = score_result.confidence
    signals = score_result.signals
    pnl_pct = position_data.get("pnl_pct", 0)
    pnl_eur = position_data.get("pnl_eur", 0)
    holding_days = position_data.get("holding_days", 0)
    buy_price = position_data.get("buy_price", 0)
    current_price = position_data.get("current_price", 0)
    stop_loss = position_data.get("stop_loss")
    take_profit = position_data.get("take_profit")
    atr_val = position_data.get("atr_val")
    quantity = position_data.get("quantity", 0)
    total_invested = position_data.get("total_invested", 0)
    current_value = position_data.get("current_value", 0)
    sma200_dist = position_data.get("sma200_dist")

    # DCF-Daten extrahieren
    dcf_upside = dcf_data.get("upside_pct", 0) if dcf_data else 0
    dcf_fair_value = dcf_data.get("fair_value", 0) if dcf_data else 0
    dcf_mos_entry = 0
    if dcf_fair_value and buy_price > 0:
        dcf_mos_entry = ((dcf_fair_value - buy_price) / buy_price) * 100

    # ── Volume-Modifier Schwellenwerte ──────────────────────────
    thresholds = {
        "klein": {
            "sell_pnl_loss": -12, "sell_confidence": 30,
            "teilverkauf_pnl": 15, "teilverkauf_pct": 40,
            "aufstocken_confidence": 62, "aufstocken_pnl_max": 8,
            "stop_dist_mult": 1.2,
            "language": "aggressive",
        },
        "mittel": {
            "sell_pnl_loss": -15, "sell_confidence": 25,
            "teilverkauf_pnl": 20, "teilverkauf_pct": 30,
            "aufstocken_confidence": 65, "aufstocken_pnl_max": 5,
            "stop_dist_mult": 1.5,
            "language": "balanced",
        },
        "gross": {
            "sell_pnl_loss": -10, "sell_confidence": 35,
            "teilverkauf_pnl": 12, "teilverkauf_pct": 20,
            "aufstocken_confidence": 72, "aufstocken_pnl_max": 3,
            "stop_dist_mult": 1.8,
            "language": "conservative",
        },
    }
    t = thresholds.get(volume_modifier, thresholds["mittel"])

    # ── Positionsbezogene Score-Anpassung ──────────────────────
    # Basis: bestehender Confidence-Score + Positions-Faktoren
    pos_adjustment = 0.0

    # P&L-Faktor: Positions im Gewinn bekommen leichten Bonus
    if pnl_pct > 20:
        pos_adjustment += 5
    elif pnl_pct > 10:
        pos_adjustment += 3
    elif pnl_pct < -20:
        pos_adjustment -= 8
    elif pnl_pct < -10:
        pos_adjustment -= 4

    # Haltedauer-Faktor: Sehr kurze Haltedauer = höhere Unsicherheit
    if holding_days < 7:
        pos_adjustment -= 3
    elif holding_days > 180:
        pos_adjustment += 2

    # SMA200-Distanz: Kurs weit über SMA200 = Überdehnung
    if sma200_dist is not None:
        if sma200_dist > 30:
            pos_adjustment -= 5
        elif sma200_dist < -20:
            pos_adjustment -= 3

    # DCF Margin of Safety
    if dcf_upside > 30:
        pos_adjustment += 5
    elif dcf_upside < -30:
        pos_adjustment -= 5

    position_score = max(0, min(100, confidence + pos_adjustment))

    # ── Handlungsoption bestimmen ──────────────────────────────
    rsi_overbought = signals.get("rsi_overbought", False)
    rsi_oversold = signals.get("rsi_oversold", False)
    trend_macro_bullish = signals.get("trend_macro_bullish", False)
    trend_macro_bearish = signals.get("trend_macro_bearish", False)
    macd_bullish = signals.get("macd_bullish", False)

    action = "HALTEN"
    action_css = "halten"
    action_detail = ""
    rc_color = "rc-blue"

    # 1. VOLLSTÄNDIG SCHLIESSEN
    if (pnl_pct <= t["sell_pnl_loss"] and position_score <= t["sell_confidence"]
            and trend_macro_bearish):
        action = "VOLLSTÄNDIG SCHLIESSEN"
        action_css = "schliessen"
        rc_color = "rc-red"
        realized = pnl_eur
        action_detail = (
            f"Realisierbarer {'Verlust' if realized < 0 else 'Gewinn'}: "
            f"{realized:+,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
        )

    # 2. TEILVERKAUF
    elif pnl_pct >= t["teilverkauf_pnl"] and rsi_overbought:
        action = "TEILVERKAUF"
        action_css = "teilverkauf"
        rc_color = "rc-yellow"
        sell_pct = t["teilverkauf_pct"]
        sell_qty = round(quantity * sell_pct / 100, 2)
        remaining_value = (quantity - sell_qty) * current_price
        action_detail = (
            f"Empfohlen: {sell_pct}% der Position verkaufen "
            f"({sell_qty:.2f} Anteile). "
            f"Verbleibender Positionswert: "
            f"{remaining_value:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
        )

    # 3. AUFSTOCKEN
    elif (position_score >= t["aufstocken_confidence"]
          and pnl_pct <= t["aufstocken_pnl_max"]
          and trend_macro_bullish
          and not rsi_overbought
          and dcf_upside > 10):
        action = "AUFSTOCKEN"
        action_css = "aufstocken"
        rc_color = "rc-green"
        # Empfohlener Zukauf: 25-50% der Ausgangsinvestition je nach Modifier
        zukauf_pct = {"klein": 50, "mittel": 33, "gross": 25}.get(volume_modifier, 33)
        zukauf_eur = total_invested * zukauf_pct / 100
        action_detail = (
            f"Empfohlener Zukaufbetrag: "
            f"{zukauf_eur:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".") +
            f" ({zukauf_pct}% der Ausgangsinvestition)"
        )

    # 4. STOP ANPASSEN
    elif (pnl_pct > 10 and atr_val and stop_loss is not None
          and trend_macro_bullish and macd_bullish):
        new_stop = current_price - t["stop_dist_mult"] * atr_val
        if new_stop > stop_loss:
            action = "STOP ANPASSEN"
            action_css = "stop"
            rc_color = "rc-purple"
            action_detail = (
                f"Aktueller Stop: {stop_loss:,.2f} EUR → "
                f"Empfohlener neuer Stop: {new_stop:,.2f} EUR "
                f"({t['stop_dist_mult']}× ATR unter aktuellem Kurs)"
            ).replace(",", "X").replace(".", ",").replace("X", ".")

    # 5. ABSICHERN
    elif (position_score <= 40 and pnl_pct > 5 and not trend_macro_bullish):
        action = "ABSICHERN"
        action_css = "absichern"
        rc_color = "rc-blue"
        action_detail = (
            "Position im Gewinn, aber technisch/fundamental schwach. "
            "Hedging erwägen (Stop nachziehen, Teilverkauf, oder Put-Absicherung)."
        )

    # 6. HALTEN (Default)
    else:
        action = "HALTEN"
        action_css = "halten"
        rc_color = "rc-blue"
        action_detail = "Position beibehalten — kein unmittelbarer Handlungsbedarf."

    # ── Begründung (strukturiert) ──────────────────────────────
    # Technische Lage
    tech_parts = []
    if trend_macro_bullish:
        tech_parts.append("Der übergeordnete Trend ist intakt (Kurs über SMA 200).")
    elif trend_macro_bearish:
        tech_parts.append("Der übergeordnete Trend ist negativ (Kurs unter SMA 200).")
    if macd_bullish:
        tech_parts.append("MACD zeigt kurzfristig bullishes Momentum.")
    else:
        tech_parts.append("MACD signalisiert nachlassendes Momentum.")
    if rsi_overbought:
        tech_parts.append("RSI im überkauften Bereich — Rücksetzer wahrscheinlich.")
    elif rsi_oversold:
        tech_parts.append("RSI überverkauft — technischer Rebound möglich.")
    tech_text = " ".join(tech_parts[:3])

    # Fundamentale Lage
    fund_parts = []
    if dcf_data:
        if dcf_upside > 20:
            fund_parts.append(f"DCF-Fair-Value {dcf_upside:+.0f}% über aktuellem Kurs — Unterbewertung.")
        elif dcf_upside < -20:
            fund_parts.append(f"DCF-Fair-Value {dcf_upside:+.0f}% unter aktuellem Kurs — Überbewertung.")
        else:
            fund_parts.append("Aktie nahe am fairen Wert bewertet.")

    for part in score_result.fundamental_text_parts[:2]:
        fund_parts.append(part)
    fund_text = " ".join(fund_parts[:3]) if fund_parts else "Keine ausreichenden Fundamentaldaten verfügbar."

    # Positionsspezifisch
    def _fmt_eur(val):
        return f"{val:+,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")

    pos_parts = []
    pos_parts.append(
        f"Sie halten die Position seit {holding_days} Tagen mit einem "
        f"unrealisierten {'Gewinn' if pnl_pct >= 0 else 'Verlust'} von "
        f"{pnl_pct:+.1f}% ({_fmt_eur(pnl_eur)})."
    )
    if dcf_fair_value and current_price:
        dist_to_dcf = ((current_price - dcf_fair_value) / dcf_fair_value) * 100
        if dist_to_dcf < 0:
            pos_parts.append(
                f"Der aktuelle Kurs liegt {abs(dist_to_dcf):.1f}% unter dem "
                f"DCF-Fair-Value von {dcf_fair_value:,.2f} EUR — "
                f"fundamental bleibt die Aktie attraktiv bewertet.".replace(",", "X").replace(".", ",").replace("X", ".")
            )
        else:
            pos_parts.append(
                f"Der aktuelle Kurs liegt {dist_to_dcf:.1f}% über dem "
                f"DCF-Fair-Value von {dcf_fair_value:,.2f} EUR.".replace(",", "X").replace(".", ",").replace("X", ".")
            )
    pos_text = " ".join(pos_parts[:3])

    # Risikofaktoren
    risks = []
    if pnl_pct < -10:
        risks.append(f"Position im deutlichen Verlust ({pnl_pct:+.1f}%) — psychologischer Druck auf Haltedisziplin.")
    if rsi_overbought:
        risks.append("Technisch überkauft — kurzfristiger Rücksetzer wahrscheinlich.")
    if trend_macro_bearish:
        risks.append("Übergeordneter Abwärtstrend aktiv — Gegenposition zum Markttrend.")
    if sma200_dist is not None and sma200_dist > 25:
        risks.append(f"Kurs {sma200_dist:.1f}% über SMA 200 — Mean Reversion Risiko.")
    if dcf_upside < -20:
        risks.append("DCF-Überbewertung — fundamentales Downside-Risiko.")
    if not risks:
        risks.append("Keine wesentlichen Risikofaktoren identifiziert.")
    risks = risks[:4]  # Max 4

    # ── Konkrete Handlungsschritte ─────────────────────────────
    steps = []

    # 1. Entry / Kein neuer Entry
    if action == "AUFSTOCKEN":
        steps.append(f"Zukauf: {action_detail}")
    else:
        steps.append("Kein neuer Entry — bestehende Position verwalten.")

    # 2. Stop-Loss
    if atr_val:
        new_sl = current_price - t["stop_dist_mult"] * atr_val
        if stop_loss:
            steps.append(
                f"Stop-Loss: {stop_loss:,.2f} EUR → empfohlen {new_sl:,.2f} EUR "
                f"({t['stop_dist_mult']}× ATR)".replace(",", "X").replace(".", ",").replace("X", ".")
            )
        else:
            steps.append(
                f"Stop-Loss setzen: {new_sl:,.2f} EUR ({t['stop_dist_mult']}× ATR unter aktuellem Kurs)".replace(",", "X").replace(".", ",").replace("X", ".")
            )

    # 3. Take-Profit
    if atr_val:
        new_tp = buy_price + 2.5 * atr_val if buy_price > 0 else current_price + 2.5 * atr_val
        if take_profit:
            steps.append(
                f"Take-Profit: {take_profit:,.2f} EUR → empfohlen {new_tp:,.2f} EUR "
                f"(2,5× ATR über Einstieg)".replace(",", "X").replace(".", ",").replace("X", ".")
            )
        else:
            steps.append(
                f"Take-Profit setzen: {new_tp:,.2f} EUR (2,5× ATR über Einstieg)".replace(",", "X").replace(".", ",").replace("X", ".")
            )

    # 4. Nächster Review-Zeitpunkt
    if atr_val and current_price > 0:
        volatility_pct = (atr_val / current_price) * 100
        if volatility_pct > 3:
            review_days = 7
        elif volatility_pct > 1.5:
            review_days = 14
        else:
            review_days = 21
        # Längere Haltedauer = seltener Review nötig
        if holding_days > 90:
            review_days = min(review_days + 7, 30)
        steps.append(f"Nächster Review: In {review_days} Tagen")
    else:
        steps.append("Nächster Review: In 14 Tagen")

    # ── Modifizierter Sprachstil ───────────────────────────────
    modifier_labels = {
        "klein": "Kleine Position (< 5% Portfolio)",
        "mittel": "Mittlere Position (5–15% Portfolio)",
        "gross": "Große Position (> 15% Portfolio)",
    }
    modifier_badge = modifier_labels.get(volume_modifier, modifier_labels["mittel"])

    return {
        "position_score": position_score,
        "action": action,
        "action_css": action_css,
        "action_detail": action_detail,
        "rc_color": rc_color,
        "reasoning": {
            "technisch": tech_text,
            "fundamental": fund_text,
            "positionsspezifisch": pos_text,
            "risikofaktoren": risks,
        },
        "steps": steps,
        "modifier_badge": modifier_badge,
        "volume_modifier": volume_modifier,
    }


# ---------------------------------------------------------------------------
# V2: Professionelle Positionsanalyse (orchestriert alle neuen Engines)
# ---------------------------------------------------------------------------

def calc_position_analysis_v2(
    score_result,
    position_data: dict,
    dcf_data: dict | None = None,
    balance_data: dict | None = None,
    volume_modifier: str = "mittel",
    hist=None,
) -> dict:
    """Professionelle Positionsanalyse V2 mit State Engine, Validierung,
    Metriken, Stop-Vorschlägen, Multi-Score und erklärbarer Empfehlung.

    Orchestriert alle neuen Domain-Engines und liefert ein vollständiges
    Analyse-Ergebnis. Das Legacy-Format (calc_position_score) wird
    weiterhin als Fallback innerhalb des zurückgegebenen Dicts mitgeliefert.

    Args:
        score_result: ScoreResult von calc_full_score()
        position_data: Dict mit buy_price, current_price, quantity, etc.
        dcf_data: DCF-Bewertungsdaten (optional)
        balance_data: Bilanzdaten (optional)
        volume_modifier: Positionsgrößen-Modifier
        hist: Historische OHLCV-Daten (für Chandelier/Highest High)

    Returns:
        Dict mit 'position_analysis' (PositionAnalysis) und 'legacy_rec' (altes Format)
    """
    from services.position_types import (
        PositionSide, PositionAnalysis, AuditEntry, Severity,
    )
    from services.target_stop_validator import validate_target_stop
    from services.position_state_engine import determine_position_state
    from services.position_metrics_engine import calc_position_metrics
    from services.trailing_stop_engine import generate_stop_proposals, get_suggested_stop
    from services.scoring_engine_v2 import calc_position_scores
    from services.recommendation_engine import generate_recommendation
    from services.data_quality_engine import assess_data_quality

    signals = score_result.signals if score_result else {}

    buy_price = position_data.get("buy_price", 0)
    current_price = position_data.get("current_price", 0)
    quantity = position_data.get("quantity", 0)
    stop_loss = position_data.get("stop_loss")
    take_profit = position_data.get("take_profit")
    holding_days = position_data.get("holding_days", 0)
    atr_val = position_data.get("atr_val")

    side = PositionSide.LONG  # Default — Short support prepared but not UI-exposed
    analysis = PositionAnalysis(side=side)

    # ── 1. Validierung ────────────────────────────────────────────
    validation = validate_target_stop(
        side=side,
        current_price=current_price,
        entry_price=buy_price,
        take_profit=take_profit,
        active_stop=stop_loss,
        previous_stop=None,  # No previous stop tracking yet
        initial_stop=None,   # No initial stop tracking yet
    )
    analysis.validation = validation

    # ── 2. Metriken ───────────────────────────────────────────────
    # Compute highest_high from hist for drawdown/chandelier
    highest_high_22 = None
    if hist is not None and not hist.empty and "High" in hist.columns:
        try:
            high_series = hist["High"]
            if len(high_series) >= 22:
                highest_high_22 = float(high_series.iloc[-22:].max())
        except Exception:
            pass

    metrics = calc_position_metrics(
        side=side,
        entry_price=buy_price,
        current_price=current_price,
        quantity=quantity,
        active_stop=validation.active_stop,
        active_take_profit=validation.active_take_profit,
        initial_stop=None,
        original_take_profit=take_profit,
        holding_days=holding_days,
        atr_val=atr_val,
        high_since_entry=highest_high_22,  # Best approximation with available data
    )
    analysis.metrics = metrics

    # ── 3. State Engine ───────────────────────────────────────────
    pnl_pct = (metrics.unrealized_pnl_pct or 0) * 100
    state = determine_position_state(
        side=side,
        pnl_pct=pnl_pct,
        validation=validation,
        signals=signals,
        atr_val=atr_val,
        current_price=current_price,
        active_stop=validation.active_stop,
    )
    analysis.state = state
    analysis.mode = state.mode

    # ── 4. Stop-Vorschläge ────────────────────────────────────────
    sma20 = signals.get("sma20_val")
    sma50 = signals.get("sma50_val")

    stop_proposals = generate_stop_proposals(
        side=side,
        current_price=current_price,
        entry_price=buy_price,
        quantity=quantity,
        atr_val=atr_val,
        highest_high_22=highest_high_22,
        sma20=sma20,
        sma50=sma50,
        previous_stop=None,
    )
    analysis.stop_proposals = stop_proposals
    suggested_stop = get_suggested_stop(stop_proposals, side)

    # ── 5. Data Quality ───────────────────────────────────────────
    data_quality = assess_data_quality(
        position_data=position_data,
        signals=signals,
        has_dcf=dcf_data is not None,
        has_balance=balance_data is not None,
    )
    analysis.data_quality = data_quality

    # ── 6. Multi-Score ────────────────────────────────────────────
    scores = calc_position_scores(
        signals=signals,
        position_data=position_data,
        validation=validation,
        metrics=metrics,
        dcf_data=dcf_data,
        balance_data=balance_data,
    )
    analysis.scores = scores

    # ── 7. Recommendation ─────────────────────────────────────────
    recommendation = generate_recommendation(
        mode=state.mode,
        state=state,
        validation=validation,
        metrics=metrics,
        scores=scores,
        signals=signals,
        stop_proposals=stop_proposals,
        data_quality=data_quality,
        side=side,
        current_price=current_price,
        entry_price=buy_price,
        original_take_profit=take_profit,
        suggested_stop=suggested_stop,
    )
    analysis.recommendation = recommendation

    # ── 8. Audit Log ──────────────────────────────────────────────
    audit: list[AuditEntry] = []
    for rule in validation.triggered_rules:
        audit.append(AuditEntry(
            rule_id=rule.rule_id,
            severity=rule.severity,
            triggered=True,
            message=rule.message,
            affected_recommendation=rule.affected_recommendation,
        ))
    for err in validation.errors:
        audit.append(AuditEntry(
            rule_id=err.rule_id,
            severity=err.severity,
            triggered=True,
            message=err.message,
            affected_recommendation=err.affected_recommendation,
        ))
    for warn in validation.warnings:
        if warn.severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL):
            audit.append(AuditEntry(
                rule_id=warn.rule_id,
                severity=warn.severity,
                triggered=True,
                message=warn.message,
                affected_recommendation=warn.affected_recommendation,
            ))
    analysis.audit_log = audit

    # ── Legacy compatibility dict ─────────────────────────────────
    # Map new recommendation to legacy action/css for templates that
    # haven't been updated yet
    _action_map = {
        "HOLD_WITH_TRAILING_STOP": ("HALTEN MIT TRAILING STOP", "halten", "rc-purple"),
        "TARGET_REACHED_REVIEW": ("KURSZIEL ERREICHT", "stop", "rc-yellow"),
        "PARTIAL_TAKE_PROFIT": ("TEILVERKAUF PRÜFEN", "teilverkauf", "rc-yellow"),
        "PROFIT_PROTECTION_MODE": ("GEWINNSICHERUNG", "absichern", "rc-purple"),
        "NORMAL_HOLD": ("HALTEN", "halten", "rc-blue"),
        "HOLD": ("HALTEN", "halten", "rc-blue"),
        "EXIT_REVIEW": ("EXIT PRÜFEN", "schliessen", "rc-red"),
        "EXIT": ("EXIT", "schliessen", "rc-red"),
        "LOSS_POSITION_REVIEW": ("VERLUSTPOSITION PRÜFEN", "schliessen", "rc-red"),
        "THESIS_REVIEW": ("THESE PRÜFEN", "absichern", "rc-yellow"),
        "HOLD_BUT_REDUCE_RISK": ("RISIKO REDUZIEREN", "absichern", "rc-yellow"),
        "STOP_THREATENED": ("STOP BEDROHT", "stop", "rc-red"),
        "NO_ACTION_DATA_INSUFFICIENT": ("DATEN UNZUREICHEND", "halten", "rc-blue"),
    }
    primary_val = recommendation.primary.value if hasattr(recommendation.primary, 'value') else str(recommendation.primary)
    legacy_action, legacy_css, legacy_color = _action_map.get(
        primary_val, ("HALTEN", "halten", "rc-blue")
    )

    # Build steps from next_actions + review_triggers
    legacy_steps = list(recommendation.next_actions)
    if recommendation.review_triggers:
        trigger_text = "Review bei: " + ", ".join(recommendation.review_triggers[:3])
        legacy_steps.append(trigger_text)

    legacy_rec = {
        "position_score": scores.overall or 50,
        "action": legacy_action,
        "action_css": legacy_css,
        "action_detail": recommendation.summary,
        "rc_color": legacy_color,
        "reasoning": {
            "technisch": " ".join(recommendation.rationale[:2]) if recommendation.rationale else "—",
            "fundamental": "—",
            "positionsspezifisch": recommendation.summary,
            "risikofaktoren": recommendation.warnings or ["Keine kritischen Risikofaktoren identifiziert."],
        },
        "steps": legacy_steps,
        "modifier_badge": {
            "klein": "Kleine Position (< 5% Portfolio)",
            "mittel": "Mittlere Position (5–15% Portfolio)",
            "gross": "Große Position (> 15% Portfolio)",
        }.get(volume_modifier, "Mittlere Position (5–15% Portfolio)"),
        "volume_modifier": volume_modifier,
    }

    return {
        "position_analysis": analysis,
        "legacy_rec": legacy_rec,
        "suggested_stop": suggested_stop,
    }

