"""
services/position_analysis.py — Bewertung einer bestehenden Position.

Die Schicht ueber der Einstiegs-Engine. `services/scoring.py` rechnet aus
Kursdaten die Indikatoren und bewertet einen NEUEN Einstieg; dieses Modul nimmt
deren Ergebnis (`ScoreResult.signals`) entgegen und orchestriert daraus die
Bewertung einer Position, die bereits offen ist:

    Validierung (target_stop_validator)
      -> Metriken (position_metrics_engine)
      -> Zustand (position_state_engine)
      -> Stop-Vorschlaege (trailing_stop_engine)
      -> Datenqualitaet (data_quality_engine)
      -> 12 Teilscores (position_scoring)
      -> Empfehlung (recommendation_engine)

Lag bis 2026-10-04 am Ende von services/scoring.py: der Dirigent der
Positions-Pipeline war im Modul der Einstiegs-Engine einquartiert und liess die
Abhaengigkeit verkehrt herum aussehen. Die Imports standen dort in den
Funktionskoerpern, als waere ein Zyklus zu umgehen — keines der beteiligten
Module importiert services.scoring, deshalb stehen sie hier oben.
"""

import pandas as pd

from services.data_quality_engine import assess_data_quality
from services.position_metrics_engine import calc_position_metrics
from services.position_scoring import calc_position_scores
from services.position_state_engine import determine_position_state
from services.position_types import (
    AuditEntry, PositionAnalysis, PositionSide, Severity,
)
from services.recommendation_engine import generate_recommendation
from services.target_stop_validator import validate_target_stop
from services.trailing_stop_engine import (
    calculate_suggested_take_profit, generate_stop_proposals,
    get_suggested_stop,
)


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
            if "Bullish" in entry.get("Signal", "") or "" in entry.get("Signal", ""):
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
            if "Akkumulation" in entry.get("Signal", "") or "" in entry.get("Signal", ""):
                entry["Positionsrelevanz"] = "Institutionelle Käufe stützen die Position."
            elif "Distribution" in entry.get("Signal", "") or "" in entry.get("Signal", ""):
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


# ---------------------------------------------------------------------------
# Orchestrierung der Positions-Engines
# ---------------------------------------------------------------------------

def _fenster_seit_einstieg(hist, buy_date):
    """Höchst- und Tiefstkurs seit dem Einstieg.

    Bis hierher lief das auf einer 22-Bar-Näherung („Best approximation with
    available data"). Für eine Position, die drei Tage alt ist, war das
    ungefähr richtig; für eine, die ein halbes Jahr liegt, war es das Hoch des
    letzten Monats — und damit eine andere Größe als die, die der Name
    behauptet. `profit_giveback_ratio` hängt daran, und die kostet im
    Risiko-Teilscore bis zu 20 Punkte.

    Returns:
        (high, low) über das Fenster ab Einstieg, oder (None, None), wenn die
        Historie den Einstieg nicht abdeckt. None statt einer Näherung ist
        hier die richtige Antwort: die Engines behandeln fehlende Werte
        sauber (Abzug in `data_quality`), einen falschen Wert nicht.
    """
    if hist is None or getattr(hist, "empty", True) or not buy_date:
        return None, None
    if "High" not in hist.columns or "Low" not in hist.columns:
        return None, None

    try:
        einstieg = pd.Timestamp(buy_date)
        index = hist.index
        if getattr(index, "tz", None) is not None:
            einstieg = (einstieg.tz_localize(index.tz) if einstieg.tzinfo is None
                        else einstieg.tz_convert(index.tz))
        elif einstieg.tzinfo is not None:
            einstieg = einstieg.tz_localize(None)

        # Beginnt die Historie NACH dem Einstieg, fehlt der Anfang des
        # Fensters — das wahre Extrem könnte darin liegen.
        if index[0] > einstieg:
            return None, None

        fenster = hist.loc[index >= einstieg]
        if fenster.empty:
            return None, None
        return float(fenster["High"].max()), float(fenster["Low"].min())
    except (TypeError, ValueError, KeyError, IndexError):
        return None, None


def _seite_aus_positionsdaten(position_data: dict):
    """Liest die Positionsseite aus den Eingabedaten; LONG ist der Rückfall.

    Akzeptiert den Enum selbst, seinen Wert ("LONG"/"SHORT") und eine
    Schreibweise in Kleinbuchstaben — Formulardaten kommen als Text herein,
    programmatische Aufrufer halten meist den Enum in der Hand.

    Alles Unbekannte wird LONG. Eine unverständliche Angabe als SHORT zu deuten
    würde aus einem Tippfehler eine umgekehrte Empfehlung machen.
    """
    roh = position_data.get("side") if position_data else None
    if roh is None:
        return PositionSide.LONG
    if isinstance(roh, PositionSide):
        return roh
    return (PositionSide.SHORT if str(roh).strip().upper() == "SHORT"
            else PositionSide.LONG)


def calc_position_analysis(
    score_result,
    position_data: dict,
    dcf_data: dict | None = None,
    balance_data: dict | None = None,
    volume_modifier: str = "mittel",
    hist=None,
) -> dict:
    """Positionsanalyse mit State Engine, Validierung, Metriken,
    Stop-Vorschlägen, Multi-Score und erklärbarer Empfehlung.

    Orchestriert die Positions-Engines und liefert ein vollständiges
    Analyse-Ergebnis.

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
    signals = score_result.signals if score_result else {}

    buy_price = position_data.get("buy_price", 0)
    current_price = position_data.get("current_price", 0)
    quantity = position_data.get("quantity", 0)
    stop_loss = position_data.get("stop_loss")
    take_profit = position_data.get("take_profit")
    holding_days = position_data.get("holding_days", 0)
    atr_val = position_data.get("atr_val")

    # P3-02: Die Seite kam bis hierher fest verdrahtet als LONG herein,
    # obwohl jede Engine darunter (validate_target_stop, calc_position_metrics,
    # position_state_engine) beide Seiten vollständig behandelt. Der SHORT-Pfad
    # war damit toter Code — nicht falsch, nur unerreichbar.
    #
    # Jetzt entscheidet der Aufrufer über `position_data["side"]`. Die
    # Oberfläche bietet das Feld noch NICHT an; sie liefert weiterhin keine
    # Seite und bekommt damit LONG wie bisher. Das ist Absicht: der SHORT-Pfad
    # ist erst durch Tests abgedeckt, nicht durch Benutzung, und eine
    # Positionsempfehlung ist eine Aussage über echtes Geld.
    side = _seite_aus_positionsdaten(position_data)
    analysis = PositionAnalysis(side=side)

    # ── 1. Validierung ────────────────────────────────────────────
    # P3-01: beide stammen aus der Stop-Historie, sofern die Aufrufstelle eine
    # gespeicherte Position kennt. Fehlen sie, verhält sich alles wie vorher —
    # die Prüfung auf gelockerte Stops und das R-Multiple entfallen dann.
    initial_stop = position_data.get("initial_stop")
    previous_stop = position_data.get("previous_stop")

    validation = validate_target_stop(
        side=side,
        current_price=current_price,
        entry_price=buy_price,
        take_profit=take_profit,
        active_stop=stop_loss,
        previous_stop=previous_stop,
        initial_stop=initial_stop,
    )
    analysis.validation = validation

    # ── 2. Metriken ───────────────────────────────────────────────
    # Fenster seit Einstieg statt der früheren 22-Bar-Näherung. Deckt die
    # Historie den Einstieg nicht ab, bleiben beide None — und alles, was
    # daran hängt (Drawdown, Giveback, MAE/MFE), entfällt sauber.
    hoch_seit_einstieg, tief_seit_einstieg = _fenster_seit_einstieg(
        hist, position_data.get("buy_date"))

    # Davon zu trennen: der Chandelier-Stop weiter unten. Dessen 22 Bars sind
    # die DEFINITION des Verfahrens (höchstes Hoch der letzten 22 Perioden
    # minus k x ATR), keine Näherung für „seit Einstieg". Beide Fenster
    # nebeneinander sind richtig, sie beantworten verschiedene Fragen.
    hoechstes_hoch_22 = None
    if hist is not None and not hist.empty and "High" in hist.columns:
        try:
            hoch_reihe = hist["High"]
            if len(hoch_reihe) >= 22:
                hoechstes_hoch_22 = float(hoch_reihe.iloc[-22:].max())
        except (TypeError, ValueError, KeyError):
            hoechstes_hoch_22 = None

    metrics = calc_position_metrics(
        side=side,
        entry_price=buy_price,
        current_price=current_price,
        quantity=quantity,
        active_stop=validation.active_stop,
        active_take_profit=validation.active_take_profit,
        # P3-01: hier entsteht das R-Multiple. Ohne den Einstiegs-Stop bleibt
        # es None — die Stop-Historie liefert ihn, sobald die Position eine hat.
        initial_stop=initial_stop,
        original_take_profit=take_profit,
        holding_days=holding_days,
        atr_val=atr_val,
        high_since_entry=hoch_seit_einstieg,
        low_since_entry=tief_seit_einstieg,
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
        highest_high_22=hoechstes_hoch_22,
        sma20=sma20,
        sma50=sma50,
        previous_stop=previous_stop,
    )
    analysis.stop_proposals = stop_proposals
    suggested_stop = get_suggested_stop(stop_proposals, side, volume_modifier=volume_modifier)

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

    # ── 6b. Take Profit Vorschlag ─────────────────────────────────
    atr_val = position_data.get("atr_val") or signals.get("atr_val")
    suggested_tp = calculate_suggested_take_profit(
        current_price=current_price,
        entry_price=buy_price,
        suggested_stop=suggested_stop,
        atr_val=atr_val,
        side=side,
        risk_reward_ratio=2.0
    )

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
        suggested_take_profit=suggested_tp,
        volume_modifier=volume_modifier,
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

