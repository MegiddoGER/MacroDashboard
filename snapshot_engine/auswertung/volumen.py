"""
snapshot_engine/auswertung/volumen.py — Die Kategorie, über die es keine Messung gab.

BC-01 steht seit dem ersten Durchgang und ist nie widerlegt worden: die
Kategorie „volume" der Engine misst kein Volumen. VWMA ist Momentum(20),
OBV-Slope ist Momentum(20), POC ist Momentum(252). Alle bisherigen Nullbefunde
zu „Volumen" waren damit Aussagen über Momentum unter falscher Flagge.

Dieses Modul misst zum ersten Mal echten Umsatz — aus `database.KursHistorie`,
also ohne einen einzigen neuen Abruf. Es ist der erste wirklich neue Eingang
seit Beginn der Messreihe.

**Dieselbe Prüfung wie alle anderen.** Quintile gegen den Markt, querschnittlich
gerangt je Kalenderwoche und Handelsplatz, Šidák-korrigiert über sämtliche
Zellen des Durchlaufs, danach die Jahresprüfung. Die Maschinerie kommt
unverändert aus `handbuch.py` — eine eigene Auswertung für einen eigenen
Kandidaten wäre genau der Weg, auf dem ein Befund entsteht, den niemand
nachrechnen kann.

**Kein Look-ahead.** Jedes Fenster endet am Snapshot-Zeitpunkt einschliesslich;
es enthält nur Handelstage, die zum Stichtag abgeschlossen waren.

**Kein Eingriff in den Score.** Gemessen wird, mehr nicht. Ob eine dieser
Kennzahlen je eine Empfehlung steuert, ist eine Entscheidung nach der Messung —
und bisher hat keine der sieben geprüften Signalfamilien diese Schwelle
genommen.
"""

import logging
from collections import defaultdict
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from database import KursHistorie
from services.volumen import KENNZAHLEN, kennzahlen_am
from snapshot_engine.models import AnalyseModus, AnalyseSnapshot
from snapshot_engine.auswertung.basis import MIN_STICHPROBE, z_korrigiert
from snapshot_engine.auswertung.handbuch import (
    QUANTILE, _raenge, instrument_lesen, jahresstabilitaet,
)
from snapshot_engine.auswertung.holdout import TRAIN

logger = logging.getLogger(__name__)


def _reihen(db: Session) -> dict[str, tuple[list, list]]:
    """Je Ticker die aufsteigende OHLCV-Reihe plus ihre Datumsspalte.

    Einmal geladen und im Speicher gehalten: 1,47 Mio Zeilen sind rund 200 MB
    als Tupel, und die Alternative wäre eine Abfrage je Snapshot.
    """
    roh: dict[str, list] = defaultdict(list)
    zeilen = (
        db.query(KursHistorie.ticker, KursHistorie.datum,
                 KursHistorie.eroeffnung, KursHistorie.hoch,
                 KursHistorie.tief, KursHistorie.schluss,
                 KursHistorie.volumen)
        .order_by(KursHistorie.ticker, KursHistorie.datum)
        .yield_per(50_000)
    )
    for ticker, datum, o, h, t, s, v in zeilen:
        roh[ticker].append((datum, o, h, t, s, v))

    return {ticker: (reihe, [z[0] for z in reihe]) for ticker, reihe in roh.items()}


def werte_je_kennzahl(db: Session, datenmodus: str = "HISTORISCH"
                      ) -> tuple[dict[str, dict[int, float]], dict[int, tuple]]:
    """Alle Volumenkennzahlen für alle Snapshots, in einem Durchgang.

    Die Reihen einmal zu laden und alle fünf Kennzahlen je Snapshot zugleich
    zu rechnen ist der Unterschied zwischen einem Durchlauf und fünf.
    """
    reihen = _reihen(db)
    logger.info("Volumen: %d Kursreihen geladen.", len(reihen))

    snapshots = (
        db.query(AnalyseSnapshot.id, AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .order_by(AnalyseSnapshot.ticker)
        .all()
    )

    werte: dict[str, dict[int, float]] = {name: {} for name in KENNZAHLEN}
    zuordnung: dict[int, tuple] = {}
    ohne_reihe = 0

    for snapshot_id, ticker, zeitpunkt in snapshots:
        eintrag = reihen.get(ticker)
        if eintrag is None:
            ohne_reihe += 1
            continue
        reihe, daten = eintrag
        gerechnet = kennzahlen_am(reihe, zeitpunkt, daten)
        gesetzt = False
        for name, wert in gerechnet.items():
            if wert is not None:
                werte[name][snapshot_id] = float(wert)
                gesetzt = True
        if gesetzt:
            zuordnung[snapshot_id] = (ticker, zeitpunkt)

    logger.info("Volumen: %d Snapshots, %d ohne Kursreihe. Abdeckung je Kennzahl: %s",
                len(snapshots), ohne_reihe,
                {n: len(w) for n, w in werte.items()})
    return werte, zuordnung


def volumen_handbuch(db: Session, horizonte: Sequence[int] = (7, 30, 90),
                     datenmodus: str = "HISTORISCH",
                     teil: Optional[str] = TRAIN,
                     minimum: int = MIN_STICHPROBE,
                     mit_jahren: bool = True) -> dict:
    """Alle Volumenkennzahlen über alle Horizonte, gemeinsam korrigiert.

    Die Korrektur spannt über sämtliche Zellen dieses Durchlaufs — fünf
    Kennzahlen mal drei Horizonte mal sieben Zellen. Wer je Kennzahl
    korrigierte und danach die beste zitierte, hätte fünfmal getestet und
    einmal bezahlt.

    Returns:
        {"kennzahlen": [...], "jahre": {name: {...}}, "z_korrigiert",
         "anzahl_tests", "abdeckung"}
    """
    werte, zuordnung = werte_je_kennzahl(db, datenmodus)

    anzahl_tests = len(KENNZAHLEN) * len(horizonte) * (QUANTILE + 2)
    z = z_korrigiert(anzahl_tests)
    logger.info("Volumen-Handbuch: %d Tests, z = %.2f.", anzahl_tests, z)

    seiten = []
    jahre: dict[str, dict] = {}
    for name in KENNZAHLEN:
        eigene = werte[name]
        if not eigene:
            logger.warning("Volumen/%s: keine Werte — übersprungen.", name)
            continue
        # Zuordnung auf die Snapshots einschränken, für die DIESE Kennzahl
        # einen Wert trägt. Sonst rangte man gegen Titel, die gar nicht in der
        # Grundgesamtheit sind.
        eigene_zuordnung = {s: zuordnung[s] for s in eigene if s in zuordnung}
        raenge = _raenge(eigene, eigene_zuordnung)
        vorberechnet = (eigene, eigene_zuordnung, len(eigene), raenge)
        for horizont in horizonte:
            seiten.append(instrument_lesen(
                db, name, horizont=horizont, datenmodus=datenmodus, teil=teil,
                minimum=minimum, z=z, vorberechnet=vorberechnet))
        if mit_jahren:
            jahre[name] = jahresstabilitaet(
                db, name, horizont=horizonte[0], datenmodus=datenmodus,
                teil=teil, minimum=minimum, vorberechnet=vorberechnet)

    return {"kennzahlen": seiten, "jahre": jahre, "z_korrigiert": round(z, 2),
            "anzahl_tests": anzahl_tests, "teil": teil,
            "abdeckung": {n: len(w) for n, w in werte.items()}}
