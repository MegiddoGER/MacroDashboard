"""
snapshot_engine/snapshot_service.py — Kern-Logik der Signal-Qualitäts-Engine.

Erstellt Snapshots (eingefrorene Analysen) und trägt die tatsächlich
eingetretenen Kursergebnisse nach.

Der Live-Lauf ist zweistufig aufgebaut, weil das Universum ~700 Ticker umfasst:

  Phase A (gating_lauf)      — ein günstiger Batch-Download über das gesamte
                               Universum, rein technisches Scoring, entscheidet
                               per Kadenz-Regel welche Ticker überhaupt fällig
                               sind, und reiht nur diese ein.
  Phase B (queue_abarbeiten) — arbeitet die Warteschlange in kleinen Häppchen
                               ab und holt je Ticker die teuren Volldaten
                               (Fundamentals, News, SMC).

Ein einzelner Durchlauf über 700 Ticker mit Voll-Abruf wäre weder zeitlich
noch bezüglich Rate-Limits durchführbar — die Aufteilung ist der Kern des
Designs, nicht bloß eine Optimierung.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    HORIZONTE_TAGE, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotIndikator,
    AnalyseSnapshotOutcome, BackfillStatus, Datenmodus, ErstelltVon,
    Granularitaet, SignalLiveQueue, beitrag_parsen, erfolg_bewerten,
    outcomes_anlegen,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Indikator → Kategorie
# ---------------------------------------------------------------------------

# Die Checkliste aus scoring.py führt keine Kategorie mit. Diese Zuordnung
# spiegelt wider, welche _score_*-Funktion den jeweiligen Eintrag erzeugt —
# nötig, um später "alle Trend-Indikatoren" auswerten zu können.
_INDIKATOR_KATEGORIEN: dict[str, str] = {
    # _score_trend
    "ADX": "trend",
    "MACD": "trend",
    "Trend (SMAs)": "trend",
    # _score_smc (schreibt ebenfalls in die Kategorie trend)
    "FVG (Fair Value Gap)": "trend",
    "Equal Highs (EQH)": "trend",
    "Equal Lows (EQL)": "trend",
    # _score_oscillators
    "RSI (14)": "oscillator",
    "Bollinger Bänder": "oscillator",
    # _score_volume
    "OBV Trend": "volume",
    "VWMA (20T)": "volume",
    "Volumen-Cluster (POC)": "volume",
    # _score_fundamental
    "DCF Fair Value": "fundamental",
    "Bilanzqualität": "fundamental",
    "Insider-Sentiment": "fundamental",
    "Kongress": "fundamental",
    "Kongress (Urgency)": "fundamental",
    "Interessenkonflikt (COI)": "fundamental",
    "Institutioneller Anteil": "fundamental",
    "Analysten-Konsens": "fundamental",
    "Dividende": "fundamental",
    # _score_sentiment
    "News Sentiment": "sentiment",
    "Earnings Surprise": "sentiment",
    # _finalize_score (kategorieübergreifende Korrektur)
    "Contrarian-Warnung": "meta",
}


def _name_normalisieren(name: str) -> str:
    """Entfernt führende Symbole/Emoji und Leerraum aus Indikator-Namen.

    Einige Checklisten-Einträge tragen Emoji-Präfixe bzw. Variation Selectors
    (z.B. "️ Kongress"), die je nach Codepfad variieren.
    """
    if not name:
        return ""
    bereinigt = "".join(
        zeichen for zeichen in name
        if zeichen.isalnum() or zeichen in " ()-.&äöüÄÖÜß/"
    ).strip()
    return bereinigt


def indikator_kategorie(name: str) -> Optional[str]:
    """Ordnet einen Checklisten-Indikator seiner Score-Kategorie zu."""
    sauber = _name_normalisieren(name)
    if sauber in _INDIKATOR_KATEGORIEN:
        return _INDIKATOR_KATEGORIEN[sauber]
    # Präfix-Treffer (z.B. "Contrarian-Warnung " mit Symbolrest)
    for bekannt, kategorie in _INDIKATOR_KATEGORIEN.items():
        if sauber.startswith(bekannt):
            return kategorie
    return None


# ---------------------------------------------------------------------------
# Indikator-Attribution
# ---------------------------------------------------------------------------

# Die Checkliste aus scoring.py ist ein ANZEIGE-Format: das Feld "Beitrag" ist
# uneinheitlich befüllt (oft gar nicht, teils "0" obwohl der Indikator gewertet
# wurde, teils "Info"). Als Grundlage für die Indikator-Auswertung taugt es
# daher nicht.
#
# Verlässlich ist stattdessen ScoreResult.signals — dasselbe Dict, aus dem
# auch scoring_engine_v2 seine Teilscores ableitet. Konvention dort:
#   Schlüssel fehlt  → Indikator konnte nicht berechnet werden
#   True/False       → bullisch/bearisch
#
# Jeder Eintrag: (Anzeigename, Kategorie, Ableitungsfunktion).
# Die Funktion liefert +1 (bullisch), -1 (bearisch) oder None (kein
# gerichtetes Signal — z.B. RSI im neutralen Bereich).

def _aus_bool(signals: dict, schluessel: str) -> Optional[int]:
    """Bool-Signal → Richtung. Fehlender Schlüssel = nicht berechenbar."""
    wert = signals.get(schluessel)
    if wert is None:
        return None
    return 1 if wert else -1


def _aus_gegensatz(signals: dict, bullisch: str, bearisch: str) -> Optional[int]:
    """Zwei sich ausschließende Flags → Richtung."""
    if signals.get(bullisch):
        return 1
    if signals.get(bearisch):
        return -1
    return None


def _rsi_richtung(signals: dict) -> Optional[int]:
    """RSI im Mean-Reversion-Sinn: überverkauft = Kaufsignal (wie in scoring.py)."""
    if signals.get("rsi_oversold"):
        return 1
    if signals.get("rsi_overbought"):
        return -1
    return None  # Neutrale Zone ist keine Prognose


def _bollinger_richtung(signals: dict) -> Optional[int]:
    zustand = (signals.get("bollinger_state") or "").lower()
    if "unteren" in zustand:
        return 1
    if "oberen" in zustand:
        return -1
    return None


def _fvg_richtung(signals: dict) -> Optional[int]:
    bull = signals.get("unmitigated_bull")
    bear = signals.get("unmitigated_bear")
    if bull is None or bear is None or bull == bear:
        return None
    return 1 if bull > bear else -1


def _sentiment_richtung(signals: dict) -> Optional[int]:
    wert = signals.get("sentiment_avg")
    if wert is None:
        return None
    if wert > 0.05:
        return 1
    if wert < -0.05:
        return -1
    return None


def _earnings_richtung(signals: dict) -> Optional[int]:
    wert = signals.get("last_earnings_surprise")
    if wert is None:
        return None
    if wert > 0:
        return 1
    if wert < 0:
        return -1
    return None


# ADX fehlt hier bewusst: er misst Trendstärke, nicht Trendrichtung — als
# Prognose "steigt/fällt" ist er nicht auswertbar (scoring.py führt ihn
# konsequenterweise ebenfalls nur als Info-Indikator).
_SIGNAL_INDIKATOREN: tuple = (
    ("Trend (SMA 200)", "trend",
     lambda s: _aus_gegensatz(s, "trend_macro_bullish", "trend_macro_bearish"),
     "sma200_val"),
    ("SMA-Cross (20/50)", "trend",
     lambda s: _aus_gegensatz(s, "cross_bullish", "cross_bearish"), "sma50_val"),
    ("MACD", "trend",
     lambda s: _aus_gegensatz(s, "macd_bullish", "macd_bearish"), None),
    ("FVG (Fair Value Gap)", "trend", _fvg_richtung, "unmitigated_bull"),
    ("RSI (14)", "oscillator", _rsi_richtung, "rsi_val"),
    ("Bollinger Bänder", "oscillator", _bollinger_richtung, "bollinger_state"),
    ("OBV Trend", "volume", lambda s: _aus_bool(s, "obv_bullish"), None),
    ("VWMA (20T)", "volume", lambda s: _aus_bool(s, "vwap_bullish"), None),
    ("Volumen-Cluster (POC)", "volume", lambda s: _aus_bool(s, "poc_bullish"), None),
    ("News Sentiment", "sentiment", _sentiment_richtung, "sentiment_avg"),
    ("Earnings Surprise", "sentiment", _earnings_richtung, "last_earnings_surprise"),
)


def indikatoren_schreiben(db: Session, snapshot: AnalyseSnapshot, score_result) -> int:
    """Legt die Indikator-Zeilen eines Snapshots an.

    Primärquelle ist ScoreResult.signals (verlässlich). Ergänzend werden
    Fundamental-Indikatoren aus der Checkliste übernommen, soweit sie dort
    einen numerischen Beitrag tragen — _score_fundamental schreibt nichts nach
    `signals`, andernfalls fehlten diese Indikatoren vollständig.

    Returns:
        Anzahl geschriebener Indikator-Zeilen.
    """
    signals = getattr(score_result, "signals", None) or {}
    geschrieben = 0

    for name, kategorie, richtung_fn, wert_schluessel in _SIGNAL_INDIKATOREN:
        try:
            richtung = richtung_fn(signals)
        except Exception:
            richtung = None
        if richtung is None:
            continue  # Nicht berechenbar oder kein gerichtetes Signal

        rohwert = signals.get(wert_schluessel) if wert_schluessel else None
        db.add(AnalyseSnapshotIndikator(
            snapshot=snapshot,
            indikator_name=name,
            kategorie=kategorie,
            wert=(f"{rohwert:.2f}" if isinstance(rohwert, (int, float))
                  else str(rohwert)[:200] if rohwert is not None else None),
            signal_text="bullisch" if richtung > 0 else "bearisch",
            beitrag_raw=str(richtung),
            beitrag_numeric=float(richtung),
            granularitaet=Granularitaet.INDIKATOR,
        ))
        geschrieben += 1

    # Fundamental-Indikatoren aus der Checkliste ergänzen
    for eintrag in (getattr(score_result, "checklist", None) or []):
        name = eintrag.get("Indikator") or ""
        kategorie = indikator_kategorie(name)
        if kategorie != "fundamental":
            continue
        beitrag = beitrag_parsen(eintrag.get("Beitrag"))
        if not beitrag:
            continue  # Kein (oder neutraler) Beitrag → keine Prognose
        db.add(AnalyseSnapshotIndikator(
            snapshot=snapshot,
            indikator_name=_name_normalisieren(name) or name,
            kategorie=kategorie,
            wert=str(eintrag.get("Wert", ""))[:200],
            signal_text=str(eintrag.get("Signal", ""))[:500],
            beitrag_raw=str(eintrag.get("Beitrag")),
            beitrag_numeric=beitrag,
            granularitaet=Granularitaet.INDIKATOR,
        ))
        geschrieben += 1

    return geschrieben


# ---------------------------------------------------------------------------
# Signal-Erfassung
# ---------------------------------------------------------------------------

def richtung_aus_confidence(confidence: float) -> str:
    """Leitet das Richtungssignal aus der Confidence ab (Schwellen wie bisher)."""
    if confidence >= 60:
        return "KAUF"
    if confidence < 40:
        return "VERKAUF"
    return "NEUTRAL"


def signal_erfassen(
    db: Session,
    ticker: str,
    score_result,
    kurs: float,
    datenmodus: str = Datenmodus.LIVE,
    erstellt_von: str = ErstelltVon.SCHEDULER,
    zeitpunkt: Optional[datetime] = None,
    backfill_job_id: Optional[int] = None,
    commit: bool = True,
) -> Optional[AnalyseSnapshot]:
    """Schreibt ein ScoreResult als Snapshot inkl. Indikatoren und Outcomes.

    Zentrale Schreibfunktion der Engine — wird vom Live-Lauf, vom historischen
    Backfill und von der Analyse-Seite genutzt.

    Args:
        score_result: ScoreResult aus services/scoring.py
        kurs: Kurs zum Snapshot-Zeitpunkt
        datenmodus: LIVE (alle Kategorien) oder HISTORISCH (nur technische)
        zeitpunkt: Snapshot-Zeitpunkt (default: jetzt) — beim Replay das
                   historische Datum, NICHT die aktuelle Uhrzeit
        commit: False, wenn der Aufrufer die Transaktion selbst steuert
                (z.B. Backfill, der viele Snapshots gebündelt schreibt)

    Returns:
        Der erzeugte Snapshot, oder None bei ungültigen Eingaben.
    """
    if score_result is None:
        return None
    if not kurs or kurs <= 0:
        logger.warning("signal_erfassen(%s): ungültiger Kurs %s — verworfen.", ticker, kurs)
        return None

    zeitpunkt = zeitpunkt or datetime.utcnow()

    snapshot = AnalyseSnapshot(
        ticker=ticker.upper(),
        snapshot_zeitpunkt=zeitpunkt,
        kurs_bei_snapshot=float(kurs),
        confidence=score_result.confidence,
        confidence_label=score_result.confidence_label,
        richtungssignal=richtung_aus_confidence(score_result.confidence),
        indikator_json=json.dumps(score_result.cat_scores),
        cat_max_json=json.dumps(score_result.cat_max),
        weights_json=json.dumps(score_result.weights),
        checklist_json=json.dumps(score_result.checklist, ensure_ascii=False),
        analyse_modus=AnalyseModus.NEUE_POSITION,
        datenmodus=datenmodus,
        erstellt_von=erstellt_von,
        backfill_job_id=backfill_job_id,
    )
    db.add(snapshot)

    # Einzelindikatoren normalisieren (Basis der Indikator-Auswertung)
    indikatoren_schreiben(db, snapshot, score_result)

    for outcome in outcomes_anlegen(snapshot):
        db.add(outcome)

    if commit:
        db.commit()

    return snapshot


# ---------------------------------------------------------------------------
# Kadenz-Regel
# ---------------------------------------------------------------------------

# Kürzester Horizont — bestimmt, wie oft ein Ticker überhaupt neu bewertet wird.
_MIN_HORIZONT = min(HORIZONTE_TAGE)


def ist_snapshot_faellig(db: Session, ticker: str,
                         richtung_neu: Optional[str] = None,
                         zeitpunkt: Optional[datetime] = None) -> bool:
    """Prüft, ob für einen Ticker ein neuer Snapshot angelegt werden soll.

    Ohne diese Regel würde ein täglicher Lauf bei 7/30/90-Tage-Horizonten
    massiv überlappende, fast identische Beobachtungen erzeugen. Die Statistik
    sähe dann nach hunderten unabhängigen Stichproben aus, wäre real aber nur
    eine Handvoll — Trefferquoten würden dadurch scheinbar signifikant.

    Fällig ist ein Ticker, wenn:
      - noch kein Snapshot existiert,
      - der kürzeste Horizont seit dem letzten Snapshot abgelaufen ist, oder
      - sich das Richtungssignal geändert hat (echtes neues Ereignis).
    """
    zeitpunkt = zeitpunkt or datetime.utcnow()

    letzter = (
        db.query(AnalyseSnapshot)
        .filter(AnalyseSnapshot.ticker == ticker.upper())
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .order_by(AnalyseSnapshot.snapshot_zeitpunkt.desc())
        .first()
    )

    if letzter is None:
        return True

    if letzter.snapshot_zeitpunkt + timedelta(days=_MIN_HORIZONT) <= zeitpunkt:
        return True

    if richtung_neu and richtung_neu != letzter.richtungssignal:
        return True

    return False


# ---------------------------------------------------------------------------
# Phase A — günstiges Gating über das gesamte Universum
# ---------------------------------------------------------------------------

def gating_lauf(db: Session, tickers: Optional[list[str]] = None) -> dict:
    """Ermittelt per Batch-Download, welche Ticker neu bewertet werden müssen.

    Rechnet ausschließlich mit OHLCV-Daten (calc_technical_score) — ein
    Voll-Abruf je Ticker findet erst in Phase B statt, und nur für die
    tatsächlich fälligen.

    Returns:
        {"geprueft": n, "eingereiht": m, "ohne_daten": k}
    """
    from services.market_data_batch import batch_download_ohlcv
    from services.scoring import calc_technical_score
    from snapshot_engine.universe import aktives_universum

    if tickers is None:
        tickers = aktives_universum(db)

    if not tickers:
        logger.warning("Gating: leeres Universum — Lauf übersprungen.")
        return {"geprueft": 0, "eingereiht": 0, "ohne_daten": 0}

    logger.info("Gating: prüfe %d Ticker...", len(tickers))

    # Bereits eingereihte Ticker nicht doppelt aufnehmen
    bereits_offen = {
        row.ticker for row in db.query(SignalLiveQueue.ticker).filter(
            SignalLiveQueue.status == BackfillStatus.AUSSTEHEND).all()
    }

    kursdaten = batch_download_ohlcv(tickers, period="2y", min_bars=200,
                                     pause_sekunden=0.5)

    eingereiht = 0
    ohne_daten = 0
    jetzt = datetime.utcnow()

    for ticker in tickers:
        if ticker in bereits_offen:
            continue

        hist = kursdaten.get(ticker)
        if hist is None:
            ohne_daten += 1
            continue

        try:
            technisch = calc_technical_score(hist)
        except Exception as e:
            logger.warning("Gating: technischer Score für %s fehlgeschlagen: %s",
                           ticker, e, exc_info=True)
            ohne_daten += 1
            continue

        if technisch is None:
            ohne_daten += 1
            continue

        richtung = richtung_aus_confidence(technisch.confidence)
        if not ist_snapshot_faellig(db, ticker, richtung_neu=richtung, zeitpunkt=jetzt):
            continue

        db.add(SignalLiveQueue(
            ticker=ticker,
            eingereiht_am=jetzt,
            status=BackfillStatus.AUSSTEHEND,
            richtung_gating=richtung,
        ))
        eingereiht += 1

    db.commit()
    logger.info("Gating abgeschlossen: %d fällig, %d ohne Daten (von %d geprüft).",
                eingereiht, ohne_daten, len(tickers))

    return {"geprueft": len(tickers), "eingereiht": eingereiht, "ohne_daten": ohne_daten}


# ---------------------------------------------------------------------------
# Phase B — teurer Voll-Abruf je fälligem Ticker
# ---------------------------------------------------------------------------

MAX_VERSUCHE = 3           # Voll-Analyse je Ticker (Phase B)
MAX_OUTCOME_VERSUCHE = 5   # Kursabruf je fälligem Outcome


def queue_abarbeiten(db: Session, limit: int = 10,
                     pause_sekunden: float = 1.5) -> dict:
    """Arbeitet einen Teil der Live-Warteschlange ab (Voll-Analyse je Ticker).

    Bewusst begrenzt: der Job läuft im Intervall erneut, bis die Schlange leer
    ist. Ein Neustart der App setzt einfach dort fort, wo die DB steht.

    Returns:
        {"verarbeitet": n, "erfolgreich": m, "fehlgeschlagen": k, "offen": o}
    """
    import time

    from services.market_data import get_history, get_stock_details
    from services.scoring import calc_full_score

    offene = (
        db.query(SignalLiveQueue)
        .filter(SignalLiveQueue.status == BackfillStatus.AUSSTEHEND)
        .order_by(SignalLiveQueue.eingereiht_am)
        .limit(limit)
        .all()
    )

    if not offene:
        return {"verarbeitet": 0, "erfolgreich": 0, "fehlgeschlagen": 0, "offen": 0}

    erfolgreich = 0
    fehlgeschlagen = 0

    for index, eintrag in enumerate(offene):
        ticker = eintrag.ticker
        eintrag_id = eintrag.id

        try:
            hist = get_history(ticker, period="2y")
            if hist is None or hist.empty:
                raise ValueError("keine Kursdaten")

            details = get_stock_details(ticker)
            info = (details or {}).get("info", {})

            ergebnis = calc_full_score(hist=hist, info=info, ticker=ticker)
            if ergebnis is None:
                raise ValueError("calc_full_score lieferte None")

            snapshot = signal_erfassen(
                db, ticker, ergebnis,
                kurs=float(hist["Close"].iloc[-1]),
                datenmodus=Datenmodus.LIVE,
                erstellt_von=ErstelltVon.SCHEDULER,
                commit=False,
            )
            if snapshot is None:
                raise ValueError("Snapshot konnte nicht erstellt werden")

            eintrag.status = BackfillStatus.FERTIG
            eintrag.fehlermeldung = None
            db.commit()
            erfolgreich += 1
            logger.info("Live-Snapshot %s: Confidence %.1f%% → %s",
                        ticker, ergebnis.confidence, snapshot.richtungssignal)

        except Exception as e:
            # Rollback verwirft auch den Zählerstand — daher nach dem Rollback
            # frisch laden und erst dann hochzählen.
            db.rollback()
            erneut = db.get(SignalLiveQueue, eintrag_id)
            if erneut is not None:
                erneut.versuche = (erneut.versuche or 0) + 1
                erneut.fehlermeldung = str(e)[:500]
                if erneut.versuche >= MAX_VERSUCHE:
                    erneut.status = BackfillStatus.FEHLER
                    logger.error("Live-Snapshot %s endgültig fehlgeschlagen (%d Versuche): %s",
                                 ticker, erneut.versuche, e)
                else:
                    logger.warning("Live-Snapshot %s fehlgeschlagen (Versuch %d/%d): %s",
                                   ticker, erneut.versuche, MAX_VERSUCHE, e)
                db.commit()
            fehlgeschlagen += 1

        if pause_sekunden and index < len(offene) - 1:
            time.sleep(pause_sekunden)

    offen = (
        db.query(SignalLiveQueue)
        .filter(SignalLiveQueue.status == BackfillStatus.AUSSTEHEND)
        .count()
    )

    return {
        "verarbeitet": len(offene),
        "erfolgreich": erfolgreich,
        "fehlgeschlagen": fehlgeschlagen,
        "offen": offen,
    }


# ---------------------------------------------------------------------------
# Outcomes nachtragen
# ---------------------------------------------------------------------------

def outcomes_nachtragen(db: Session, limit: int = 500) -> int:
    """Trägt Kursergebnisse für fällige Outcomes nach.

    WICHTIG — bewertet wird mit dem Kurs zum FÄLLIGKEITSDATUM, nicht mit dem
    aktuellen Kurs. Ein 30-Tage-Horizont, der vor Wochen fällig wurde, würde
    sonst faktisch die Rendite bis heute messen und wäre als
    "30-Tage-Ergebnis" schlicht falsch — genau die Art stiller Verfälschung,
    die diese Engine eigentlich aufdecken soll.

    Returns:
        Anzahl nachgetragener Outcomes.
    """
    from services.market_data_batch import batch_download_ohlcv, kurs_am_stichtag

    jetzt = datetime.utcnow()

    faellige = (
        db.query(AnalyseSnapshotOutcome)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(False))
        .filter(AnalyseSnapshotOutcome.faellig_am <= jetzt)
        .filter(AnalyseSnapshotOutcome.versuche < MAX_OUTCOME_VERSUCHE)
        .order_by(AnalyseSnapshotOutcome.faellig_am)
        .limit(limit)
        .all()
    )

    if not faellige:
        logger.info("Outcomes: nichts fällig.")
        return 0

    # Snapshots gebündelt laden (vermeidet N+1-Abfragen)
    snapshot_ids = {o.snapshot_id for o in faellige}
    snapshots = {
        s.id: s for s in db.query(AnalyseSnapshot).filter(
            AnalyseSnapshot.id.in_(snapshot_ids)).all()
    }

    tickers = sorted({snapshots[o.snapshot_id].ticker
                      for o in faellige if o.snapshot_id in snapshots})
    if not tickers:
        return 0

    # Zeitfenster so wählen, dass es alle Fälligkeiten abdeckt
    frueheste = min(o.faellig_am for o in faellige)
    start = frueheste - timedelta(days=10)

    logger.info("Outcomes: %d fällige Einträge für %d Ticker (ab %s).",
                len(faellige), len(tickers), start.date())

    kursdaten = batch_download_ohlcv(tickers, start=start,
                                     end=jetzt + timedelta(days=1),
                                     pause_sekunden=0.5)

    nachgetragen = 0

    for outcome in faellige:
        snapshot = snapshots.get(outcome.snapshot_id)
        if snapshot is None:
            continue

        hist = kursdaten.get(snapshot.ticker)
        kurs = kurs_am_stichtag(hist, outcome.faellig_am) if hist is not None else None

        if kurs is None:
            # Kein Kurs verfügbar (z.B. delisteter Ticker). Zähler hochsetzen,
            # damit solche Einträge nicht bei jedem Drain-Lauf erneut abgefragt
            # werden — nach MAX_OUTCOME_VERSUCHE fallen sie dauerhaft raus.
            outcome.versuche = (outcome.versuche or 0) + 1
            if outcome.versuche >= MAX_OUTCOME_VERSUCHE:
                logger.warning(
                    "Outcome %s (%dT, fällig %s) endgültig nicht auswertbar — "
                    "keine Kursdaten nach %d Versuchen.",
                    snapshot.ticker, outcome.horizont_tage,
                    outcome.faellig_am.date(), outcome.versuche)
            continue

        outcome.outcome_kurs = kurs
        outcome.outcome_return = round(
            (kurs - snapshot.kurs_bei_snapshot) / snapshot.kurs_bei_snapshot * 100, 2)
        outcome.outcome_zeitpunkt = outcome.faellig_am
        outcome.ausgewertet = True
        outcome.war_erfolgreich = erfolg_bewerten(
            snapshot.richtungssignal, snapshot.kurs_bei_snapshot, kurs)
        nachgetragen += 1

    db.commit()
    logger.info("Outcomes: %d nachgetragen.", nachgetragen)
    return nachgetragen


# ---------------------------------------------------------------------------
# Manueller Komplettlauf (Dashboard-Button)
# ---------------------------------------------------------------------------

def manueller_lauf(db: Session, queue_limit: int = 10) -> dict:
    """Führt Gating, einen Teil der Warteschlange und die Outcomes aus.

    Für den "jetzt ausführen"-Button. Der reguläre Betrieb läuft über den
    Scheduler.
    """
    gating = gating_lauf(db)
    queue = queue_abarbeiten(db, limit=queue_limit)
    outcomes = outcomes_nachtragen(db)

    return {
        "gating": gating,
        "queue": queue,
        "outcomes_nachgetragen": outcomes,
    }
