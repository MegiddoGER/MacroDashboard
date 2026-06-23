"""
snapshot_engine/snapshot_service.py — Kern-Logik der Snapshot Engine.

Erstellt Snapshots (eingefrorene Analysen) und trägt nachträglich
die tatsächlichen Kurs-Returns nach.
"""

import json
import warnings
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from snapshot_engine.models import AnalyseSnapshot, SnapshotKonfiguration


# ---------------------------------------------------------------------------
# Einzelnen Snapshot erstellen
# ---------------------------------------------------------------------------

def snapshot_erstellen(ticker: str, db: Session) -> bool:
    """Erstellt einen Analyse-Snapshot für einen einzelnen Ticker.

    Ruft Kursdaten und Analyse direkt ab (nicht gecached),
    speichert das Ergebnis als neuen AnalyseSnapshot.

    Returns:
        True bei Erfolg, False bei Fehler.
    """
    try:
        # Kursabruf — direkt, nicht via cached_history
        from services.market_data import get_history, get_stock_details

        hist = get_history(ticker, period="1y")
        if hist is None or hist.empty:
            print(f"[Snapshot] Keine Kursdaten für {ticker} — überspringe.")
            return False

        details = get_stock_details(ticker)
        if details is None:
            print(f"[Snapshot] Keine Details für {ticker} — überspringe.")
            return False

        info = details.get("info", {})

        # Analyse via Scoring Engine
        from services.scoring import calc_full_score

        result = calc_full_score(hist=hist, info=info, ticker=ticker)
        if result is None:
            print(f"[Snapshot] calc_full_score lieferte None für {ticker} — überspringe.")
            return False

        # Richtungssignal aus Confidence ableiten
        if result.confidence >= 60:
            richtungssignal = "KAUF"
        elif result.confidence < 40:
            richtungssignal = "VERKAUF"
        else:
            richtungssignal = "NEUTRAL"

        # Aktueller Kurs
        kurs_bei_snapshot = float(hist["Close"].iloc[-1])

        # Zeitfenster aus Konfiguration laden
        konfig = db.query(SnapshotKonfiguration).filter(
            SnapshotKonfiguration.ticker == ticker
        ).first()
        zeitfenster = konfig.zeitfenster_tage if konfig else 7

        # Snapshot speichern
        snapshot = AnalyseSnapshot(
            ticker=ticker,
            snapshot_zeitpunkt=datetime.utcnow(),
            kurs_bei_snapshot=kurs_bei_snapshot,
            confidence=result.confidence,
            confidence_label=result.confidence_label,
            richtungssignal=richtungssignal,
            indikator_json=json.dumps(result.cat_scores),
            zeitfenster_tage=zeitfenster,
            ausgewertet=False,
        )
        db.add(snapshot)
        db.commit()
        print(f"[Snapshot] ✓ {ticker}: Confidence {result.confidence:.1f}%, Signal {richtungssignal}")
        return True

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[Snapshot] ✗ Fehler bei {ticker}: {e}")
        return False


# ---------------------------------------------------------------------------
# Alle aktiven Ticker durchlaufen
# ---------------------------------------------------------------------------

def alle_snapshots_ausfuehren(db: Session) -> dict:
    """Führt Snapshots für alle aktiven Ticker aus.

    Returns:
        Dict mit Zusammenfassung: {"erfolgreich": n, "fehlgeschlagen": m, "ticker_fehler": [...]}
    """
    ergebnis = {"erfolgreich": 0, "fehlgeschlagen": 0, "ticker_fehler": []}

    try:
        aktive_ticker = db.query(SnapshotKonfiguration).filter(
            SnapshotKonfiguration.aktiv == True
        ).all()
    except Exception as e:
        print(f"[Snapshot] Fehler beim Laden der Konfiguration: {e}")
        return ergebnis

    print(f"[Snapshot] Starte Snapshot-Run für {len(aktive_ticker)} Ticker...")

    for konfig in aktive_ticker:
        erfolg = snapshot_erstellen(konfig.ticker, db)
        if erfolg:
            ergebnis["erfolgreich"] += 1
        else:
            ergebnis["fehlgeschlagen"] += 1
            ergebnis["ticker_fehler"].append(konfig.ticker)

    print(f"[Snapshot] Run abgeschlossen: {ergebnis['erfolgreich']} OK, "
          f"{ergebnis['fehlgeschlagen']} Fehler.")
    return ergebnis


# ---------------------------------------------------------------------------
# Outcomes nachträglich befüllen
# ---------------------------------------------------------------------------

def outcomes_nachtragen(db: Session) -> int:
    """Trägt die tatsächlichen Kurs-Returns nach, sobald das Zeitfenster abgelaufen ist.

    Lädt alle nicht-ausgewerteten Snapshots, deren Zeitfenster abgelaufen ist,
    holt den aktuellen Kurs und berechnet den Return.

    Returns:
        Anzahl erfolgreich nachgetragener Outcomes.
    """
    jetzt = datetime.utcnow()
    nachgetragen = 0

    try:
        offene_snapshots = db.query(AnalyseSnapshot).filter(
            AnalyseSnapshot.ausgewertet == False
        ).all()
    except Exception as e:
        print(f"[Snapshot] Fehler beim Laden offener Snapshots: {e}")
        return 0

    for snapshot in offene_snapshots:
        # Prüfe ob Zeitfenster abgelaufen
        faellig_am = snapshot.snapshot_zeitpunkt + timedelta(days=snapshot.zeitfenster_tage)
        if faellig_am > jetzt:
            continue  # Noch nicht fällig

        try:
            from services.market_data import get_history

            hist = get_history(snapshot.ticker, period="5d")
            if hist is None or hist.empty:
                print(f"[Snapshot] Outcome-Nachtrag: Keine Kursdaten für {snapshot.ticker} — "
                      f"wird beim nächsten Lauf erneut versucht.")
                continue

            outcome_kurs = float(hist["Close"].iloc[-1])
            outcome_return = (
                (outcome_kurs - snapshot.kurs_bei_snapshot) / snapshot.kurs_bei_snapshot * 100
            )

            snapshot.outcome_kurs = outcome_kurs
            snapshot.outcome_return = round(outcome_return, 2)
            snapshot.outcome_zeitpunkt = jetzt
            snapshot.ausgewertet = True
            db.commit()

            print(f"[Snapshot] Outcome für {snapshot.ticker}: "
                  f"{outcome_return:+.2f}% (Signal war {snapshot.richtungssignal})")
            nachgetragen += 1

        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            print(f"[Snapshot] Outcome-Fehler bei {snapshot.ticker}: {e}")
            # ausgewertet bleibt False → nächster Lauf versucht es erneut

    if nachgetragen > 0:
        print(f"[Snapshot] {nachgetragen} Outcomes nachgetragen.")
    else:
        print("[Snapshot] Keine fälligen Outcomes zum Nachtragen.")

    return nachgetragen
