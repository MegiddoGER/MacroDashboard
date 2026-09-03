"""
snapshot_engine/backfill_service.py — Historischer Replay der technischen Analyse.

Läuft die Kurshistorie eines Tickers Schritt für Schritt ab und erzeugt zu
jedem Stichtag einen Snapshot, als wäre die Analyse damals durchgeführt worden.
Da die "Zukunft" im bereits geladenen Kursverlauf steckt, werden die Outcomes
im selben Durchgang mitberechnet — es muss nichts abgewartet werden.

LOOK-AHEAD-BIAS — der entscheidende Punkt:
    Es wird ausschließlich calc_technical_score() verwendet (trend, volume,
    oscillator, optional SMC). Fundamentaldaten und News-Sentiment stammen
    grundsätzlich aus der Gegenwart (get_stock_details()/News-APIs) und wären
    im Replay Wissen aus der Zukunft. Sie werden deshalb nie berechnet; die
    entstehenden Snapshots tragen datenmodus=HISTORISCH und ihre
    fundamental-/sentiment-Kategorien bleiben leer (cat_max=0).

ÜBERLEBENSVERZERRUNG (Survivorship Bias):
    Das Universum ist die HEUTIGE Index-Zusammensetzung. Titel, die in der
    Vergangenheit aus S&P 500 / DAX / MDAX geflogen oder delistet sind, fehlen
    vollständig. Die historischen Kennzahlen sind dadurch systematisch etwas
    zu optimistisch. Das ist mit den verfügbaren Daten nicht behebbar und wird
    in der Oberfläche offengelegt statt kaschiert.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from services.scoring import SCORE_VERSION
from snapshot_engine.models import (
    HORIZONTE_TAGE, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotIndikator,
    AnalyseSnapshotOutcome, BackfillStatus, Datenmodus, ErstelltVon,
    Granularitaet, SignalBackfillJob, SignalBackfillTickerStatus,
    beitrag_parsen, erfolg_bewerten,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------

# Rollendes Fenster je Bewertung — entspricht dem Live-Abruf (period="2y"),
# damit historische und Live-Scores auf derselben Datenbasis beruhen.
FENSTER_BARS = 500

# Mindest-Historie, bevor überhaupt bewertet werden kann (SMA 200 + Vorlauf).
MIN_VORLAUF_BARS = 250

# Neubewertung alle N Handelstage. Entspricht dem kürzesten Horizont, damit
# aufeinanderfolgende 7-Tage-Beobachtungen sich nicht überlappen.
KADENZ_BARS = 7

# Zeitbudget je Drain-Tick — der Job darf den Webserver nicht ausbremsen.
MAX_SEKUNDEN_JE_SCHRITT = 45
MAX_TICKER_JE_SCHRITT = 15

# Ticker je Netzwerk-Call (mehrjährige Historie → kleinere Chunks als beim Live-Lauf)
BACKFILL_CHUNK_SIZE = 20

# Fehlversuche beim Kursabruf, bevor ein Ticker endgültig aufgegeben wird.
MAX_TICKER_VERSUCHE = 3


# ---------------------------------------------------------------------------
# Job-Verwaltung
# ---------------------------------------------------------------------------

def backfill_starten(db: Session, historie_jahre: int = 5,
                     include_smc: bool = True,
                     tickers: Optional[list[str]] = None) -> SignalBackfillJob:
    """Legt einen neuen Backfill-Lauf an (verarbeitet wird er vom Drain-Job).

    Das Ticker-Universum wird eingefroren, damit der Lauf deterministisch
    bleibt, auch wenn sich die Index-Zusammensetzung zwischenzeitlich ändert.
    """
    from snapshot_engine.universe import aktives_universum

    laufender = (
        db.query(SignalBackfillJob)
        .filter(SignalBackfillJob.status.in_(
            [BackfillStatus.AUSSTEHEND, BackfillStatus.LAEUFT]))
        .first()
    )
    if laufender is not None:
        # Ein Job gilt nur dann als aktiv, wenn er noch offene Ticker hat. Der
        # Übergang auf FERTIG passiert erst beim nächsten Drain-Schritt — ohne
        # diese Prüfung würde ein längst abgearbeiteter Lauf jeden neuen Start
        # blockieren und stattdessen sich selbst zurückgeben.
        offen = (
            db.query(SignalBackfillTickerStatus)
            .filter(SignalBackfillTickerStatus.job_id == laufender.id)
            .filter(SignalBackfillTickerStatus.status == BackfillStatus.AUSSTEHEND)
            .count()
        )
        if offen > 0:
            logger.info("Backfill: Lauf #%d ist bereits aktiv (%d Ticker offen).",
                        laufender.id, offen)
            return laufender

        laufender.status = BackfillStatus.FERTIG
        laufender.beendet_am = laufender.beendet_am or datetime.utcnow()
        db.commit()
        logger.info("Backfill: abgearbeiteten Lauf #%d abgeschlossen — starte neuen Lauf.",
                    laufender.id)

    if tickers is None:
        tickers = aktives_universum(db)
    tickers = list(dict.fromkeys(t.upper() for t in tickers if t))

    job = SignalBackfillJob(
        status=BackfillStatus.LAEUFT,
        gestartet_am=datetime.utcnow(),
        ticker_liste_json=json.dumps(tickers),
        historie_jahre=historie_jahre,
        include_smc=include_smc,
        ticker_gesamt=len(tickers),
        ticker_fertig=0,
        ticker_fehler=0,
        snapshots_erstellt=0,
    )
    db.add(job)
    db.flush()

    db.add_all([
        SignalBackfillTickerStatus(
            job_id=job.id, ticker=ticker, status=BackfillStatus.AUSSTEHEND)
        for ticker in tickers
    ])
    db.commit()

    logger.info("Backfill #%d gestartet: %d Ticker, %d Jahre, SMC=%s.",
                job.id, len(tickers), historie_jahre, include_smc)
    return job


def backfill_abbrechen(db: Session, job_id: Optional[int] = None) -> bool:
    """Bricht den laufenden Backfill ab (bereits erzeugte Daten bleiben)."""
    query = db.query(SignalBackfillJob).filter(
        SignalBackfillJob.status.in_([BackfillStatus.AUSSTEHEND, BackfillStatus.LAEUFT]))
    if job_id is not None:
        query = query.filter(SignalBackfillJob.id == job_id)

    job = query.first()
    if job is None:
        return False

    job.status = BackfillStatus.ABGEBROCHEN
    job.beendet_am = datetime.utcnow()
    db.commit()
    logger.info("Backfill #%d abgebrochen.", job.id)
    return True


def aktiver_job(db: Session) -> Optional[SignalBackfillJob]:
    """Gibt den aktuell laufenden Backfill-Job zurück (falls vorhanden)."""
    return (
        db.query(SignalBackfillJob)
        .filter(SignalBackfillJob.status == BackfillStatus.LAEUFT)
        .order_by(SignalBackfillJob.id.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Drain-Schritt
# ---------------------------------------------------------------------------

def backfill_schritt(db: Session,
                     max_sekunden: float = MAX_SEKUNDEN_JE_SCHRITT,
                     max_ticker: int = MAX_TICKER_JE_SCHRITT) -> dict:
    """Verarbeitet eine begrenzte Scheibe des laufenden Backfills.

    Der Fortschritt steckt vollständig in SignalBackfillTickerStatus — ein
    Neustart der App setzt daher einfach beim nächsten offenen Ticker fort.

    Returns:
        {"job_id": ..., "verarbeitet": n, "snapshots": m} oder {} wenn nichts läuft.
    """
    job = aktiver_job(db)
    if job is None:
        return {}

    offene = (
        db.query(SignalBackfillTickerStatus)
        .filter(SignalBackfillTickerStatus.job_id == job.id)
        .filter(SignalBackfillTickerStatus.status == BackfillStatus.AUSSTEHEND)
        # Noch unversuchte Ticker zuerst; wiederholt gescheiterte rutschen nach
        # hinten, statt die Warteschlange in einer engen Schleife zu blockieren.
        .order_by(SignalBackfillTickerStatus.versuche.asc(),
                  SignalBackfillTickerStatus.id.asc())
        .limit(max_ticker)
        .all()
    )

    if not offene:
        job.status = BackfillStatus.FERTIG
        job.beendet_am = datetime.utcnow()
        db.commit()
        logger.info("Backfill #%d abgeschlossen: %d Ticker, %d Snapshots.",
                    job.id, job.ticker_fertig or 0, job.snapshots_erstellt or 0)
        return {"job_id": job.id, "verarbeitet": 0, "snapshots": 0, "fertig": True}

    from services import kurshistorie
    from services.market_data_batch import batch_download_ohlcv

    start_zeit = time.perf_counter()
    tickers = [e.ticker for e in offene]
    start_datum = datetime.utcnow() - timedelta(days=365 * (job.historie_jahre or 5) + 30)

    kursdaten = batch_download_ohlcv(
        tickers, start=start_datum, chunk_size=BACKFILL_CHUNK_SIZE,
        min_bars=MIN_VORLAUF_BARS, pause_sekunden=0.5)

    verarbeitet = 0
    snapshots_gesamt = 0
    kurszeilen_gesamt = 0

    for eintrag in offene:
        if time.perf_counter() - start_zeit > max_sekunden:
            break  # Zeitbudget aufgebraucht — Rest im nächsten Tick

        hist = kursdaten.get(eintrag.ticker)
        if hist is None:
            # Fehlende Kursdaten können zwei Ursachen haben: der Ticker hat
            # tatsächlich zu wenig Historie — oder der Batch-Download ist
            # vorübergehend gescheitert (Rate-Limit, Netzwerk). Erst nach
            # mehreren Versuchen endgültig aufgeben, sonst verliert ein
            # einzelner Aussetzer einen ganzen Chunk aus dem Lauf.
            eintrag.versuche = (eintrag.versuche or 0) + 1
            eintrag.bearbeitet_am = datetime.utcnow()
            if eintrag.versuche >= MAX_TICKER_VERSUCHE:
                eintrag.status = BackfillStatus.ZU_WENIG_HISTORIE
                eintrag.fehlermeldung = (
                    f"keine Kursdaten nach {eintrag.versuche} Versuchen")
                job.ticker_fehler = (job.ticker_fehler or 0) + 1
                verarbeitet += 1
                logger.warning("Backfill: %s endgültig ohne Kursdaten (%d Versuche).",
                               eintrag.ticker, eintrag.versuche)
            else:
                # Bleibt AUSSTEHEND; die Sortierung nach `versuche` schiebt den
                # Ticker ans Ende der Warteschlange statt ihn sofort erneut zu ziehen.
                eintrag.fehlermeldung = f"Kursabruf fehlgeschlagen (Versuch {eintrag.versuche})"
            db.commit()
            continue

        try:
            # BC-04, Schritt 1: die Rohreihe festhalten, BEVOR sie abgespielt
            # wird. Bisher wurde sie hier abgerufen, durch den Score geschickt
            # und verworfen — was blieb, war die Deutung (+1/−1). Jede spätere
            # Frage nach einer anderen Auflösung oder Kennzahl kostete deshalb
            # einen neuen Durchlauf mit neuen Abrufen.
            #
            # Kein zusätzlicher Abruf: `hist` liegt bereits vor.
            # `auto_adjust=True` in `batch_download_ohlcv` — die Reihe ist
            # bereinigt, und `angepasst` hält das fest.
            #
            # Im selben try/commit wie der Replay: schlägt der Ticker fehl,
            # rollt auch seine Reihe zurück. Ein halb geschriebener Ticker
            # wäre schlimmer als ein fehlender.
            kurszeilen = kurshistorie.reihe_speichern(
                db, eintrag.ticker, hist, angepasst=True)

            anzahl = _ticker_replayen(db, eintrag.ticker, hist, job)
            eintrag.status = BackfillStatus.FERTIG
            eintrag.snapshots_erstellt = anzahl
            eintrag.bearbeitet_am = datetime.utcnow()
            job.ticker_fertig = (job.ticker_fertig or 0) + 1
            job.snapshots_erstellt = (job.snapshots_erstellt or 0) + anzahl
            snapshots_gesamt += anzahl
            kurszeilen_gesamt += kurszeilen
            db.commit()

        except Exception as e:
            db.rollback()
            erneut = db.get(SignalBackfillTickerStatus, eintrag.id)
            if erneut is not None:
                erneut.status = BackfillStatus.FEHLER
                erneut.fehlermeldung = str(e)[:500]
                erneut.bearbeitet_am = datetime.utcnow()
            aktueller_job = db.get(SignalBackfillJob, job.id)
            if aktueller_job is not None:
                aktueller_job.ticker_fehler = (aktueller_job.ticker_fehler or 0) + 1
                aktueller_job.letzter_fehler = f"{eintrag.ticker}: {e}"[:500]
            db.commit()
            job = db.get(SignalBackfillJob, job.id)
            logger.error("Backfill: %s fehlgeschlagen: %s", eintrag.ticker, e, exc_info=True)

        verarbeitet += 1

    logger.info(
        "Backfill #%d: %d Ticker verarbeitet, %d Snapshots, %d Kurszeilen (%.1fs).",
        job.id, verarbeitet, snapshots_gesamt, kurszeilen_gesamt,
        time.perf_counter() - start_zeit)

    return {"job_id": job.id, "verarbeitet": verarbeitet,
            "snapshots": snapshots_gesamt, "kurszeilen": kurszeilen_gesamt}


# ---------------------------------------------------------------------------
# Replay eines einzelnen Tickers
# ---------------------------------------------------------------------------

def _ticker_replayen(db: Session, ticker: str, hist, job: SignalBackfillJob) -> int:
    """Läuft die Historie eines Tickers ab und schreibt Snapshots + Outcomes.

    Die Outcomes werden direkt aus demselben Kursverlauf berechnet — beim
    Replay ist die "Zukunft" jedes Stichtags bereits bekannt.
    """
    from services.market_data_batch import kurs_am_stichtag
    from services.scoring import calc_technical_score
    from snapshot_engine.snapshot_service import (
        indikatoren_schreiben, richtung_aus_confidence,
    )

    include_smc = bool(job.include_smc)
    letztes_datum = hist.index[-1].to_pydatetime().replace(tzinfo=None)

    # Bereits vorhandene Stichtage überspringen (Backfill mehrfach startbar)
    vorhandene = {
        zeitpunkt for (zeitpunkt,) in db.query(AnalyseSnapshot.snapshot_zeitpunkt)
        .filter(AnalyseSnapshot.ticker == ticker)
        .filter(AnalyseSnapshot.datenmodus == Datenmodus.HISTORISCH)
        .all()
    }

    erzeugt = 0
    letzte_richtung: Optional[str] = None

    for position in range(MIN_VORLAUF_BARS, len(hist), KADENZ_BARS):
        fenster = hist.iloc[max(0, position - FENSTER_BARS):position + 1]
        if len(fenster) < MIN_VORLAUF_BARS:
            continue

        stichtag = hist.index[position].to_pydatetime().replace(tzinfo=None)
        if stichtag in vorhandene:
            continue

        try:
            ergebnis = calc_technical_score(fenster, include_smc=include_smc)
        except Exception as e:
            logger.debug("Replay %s @ %s: Score fehlgeschlagen: %s", ticker, stichtag, e)
            continue

        if ergebnis is None:
            continue

        kurs = float(fenster["Close"].iloc[-1])
        if kurs <= 0:
            continue

        richtung = richtung_aus_confidence(ergebnis.confidence)
        letzte_richtung = richtung

        snapshot = AnalyseSnapshot(
            ticker=ticker,
            snapshot_zeitpunkt=stichtag,
            kurs_bei_snapshot=kurs,
            confidence=ergebnis.confidence,
            confidence_label=ergebnis.confidence_label,
            richtungssignal=richtung,
            indikator_json=json.dumps(ergebnis.cat_scores),
            cat_max_json=json.dumps(ergebnis.cat_max),
            weights_json=json.dumps(ergebnis.weights),
            checklist_json=json.dumps(ergebnis.checklist, ensure_ascii=False),
            score_version=SCORE_VERSION,
            analyse_modus=AnalyseModus.NEUE_POSITION,
            datenmodus=Datenmodus.HISTORISCH,
            erstellt_von=ErstelltVon.BACKFILL,
            backfill_job_id=job.id,
        )
        db.add(snapshot)

        indikatoren_schreiben(db, snapshot, ergebnis)

        # Outcomes direkt mitberechnen, soweit die Historie sie hergibt
        for horizont in HORIZONTE_TAGE:
            faellig = stichtag + timedelta(days=horizont)
            outcome = AnalyseSnapshotOutcome(
                snapshot=snapshot,
                horizont_tage=horizont,
                faellig_am=faellig,
                ausgewertet=False,
            )
            if faellig <= letztes_datum:
                outcome_kurs = kurs_am_stichtag(hist, faellig)
                if outcome_kurs is not None:
                    outcome.outcome_kurs = outcome_kurs
                    # Split-sicher ohne Zusatzaufwand: `kurs` und `outcome_kurs`
                    # stammen beide aus `hist`, also aus einem einzigen
                    # einheitlich bereinigten Download.
                    outcome.basis_kurs = kurs
                    outcome.outcome_return = round((outcome_kurs - kurs) / kurs * 100, 2)
                    outcome.outcome_zeitpunkt = faellig
                    outcome.ausgewertet = True
                    outcome.war_erfolgreich = erfolg_bewerten(richtung, kurs, outcome_kurs)
            db.add(outcome)

        erzeugt += 1

    return erzeugt
