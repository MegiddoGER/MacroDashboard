"""
snapshot_engine/auswertung/kursnaehe.py — Ist der Eingang wirklich neu?

Die ausführbare Fassung der Regel aus §2f. Dort war die Zielrevision der
Analysten auf sieben Tagen beidseitig signifikant und monoton über alle fünf
Quintile — und trotzdem kein eigenständiger Eingang: ihr Rang korreliert mit
**0,47** zur Kursrendite der vorangegangenen 90 Tage. Analysten folgen dem
Kurs. Der Befund war überwiegend umetikettiertes Momentum, gemessen auf einem
Horizont, auf dem kurzfristige Fortsetzung ohnehin am ehesten auftritt.

Die Lehre daraus, und der Grund für dieses Modul: **eine fundamentale Quelle
ist noch keine fundamentale Größe.** Alles bisher Gemessene war kursbasiert und
still; ein neuer Kandidat verdient die Bezeichnung „nicht aus Kursen ableitbar"
erst, wenn das gemessen ist und nicht nur plausibel klingt.

Die Prüfung kostet eine Abfrage und gehört ab jetzt zu jeder Signalmessung.
Sie beweist nichts für sich allein — eine hohe Korrelation widerlegt einen
Befund nicht, sie erklärt ihn. Aber sie unterscheidet einen Eingang, der etwas
Neues in den Score trüge, von einem, der eine bereits gemessene Null unter
anderem Namen wiederholt.

**Kursreihen kommen aus den Snapshots, nicht aus neuen Abrufen** — dieselbe
Begründung wie in `momentum.py`: alle HISTORISCH-Snapshots eines Tickers
stammen aus einer einzigen abgespielten Kursreihe und damit aus derselben
Anpassungsbasis, weshalb ein Verhältnis zwischen zwei von ihnen split-sicher
ist.
"""

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from services.cross_sectional_momentum import momentum_roh, naechster_kurs
from snapshot_engine.models import AnalyseModus, AnalyseSnapshot

logger = logging.getLogger(__name__)


# Rückschaufenster der Vergleichsrendite. 90 Tage, weil das die Spanne ist, auf
# der sich die Frage stellt: bildet der Eingang die jüngste Kursentwicklung ab?
FENSTER_TAGE = 90

# Ab hier gilt ein Eingang als weitgehend kursgetrieben. Kein Naturgesetz,
# sondern eine Marke zum Einordnen: die Zielrevision der Analysten lag bei
# 0,47, das Querschnitts-Momentum läge per Konstruktion nahe 1,0.
SCHWELLE_KURSNAH = 0.30


def _raenge(werte: Sequence[float]) -> list[float]:
    """Positionsränge mit Durchschnittsrang für Bindungsgruppen."""
    sortiert = sorted(range(len(werte)), key=lambda i: werte[i])
    raenge = [0.0] * len(werte)
    i = 0
    while i < len(sortiert):
        j = i
        while j + 1 < len(sortiert) and werte[sortiert[j + 1]] == werte[sortiert[i]]:
            j += 1
        mittel = (i + j) / 2.0
        for k in range(i, j + 1):
            raenge[sortiert[k]] = mittel
        i = j + 1
    return raenge


def rangkorrelation(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    """Spearman-Rangkorrelation zweier gleich langer Reihen.

    Rang statt Rohwert, weil beide Größen schwere Ränder haben: eine einzelne
    Kurszielanhebung um 1875 Prozent oder eine Kursverdreifachung würde eine
    Produkt-Moment-Korrelation dominieren.
    """
    import statistics

    if len(a) != len(b) or len(a) < 3:
        return None
    ra, rb = _raenge(a), _raenge(b)
    try:
        return statistics.correlation(ra, rb)
    except statistics.StatisticsError:
        # Eine der Reihen ist konstant — dann gibt es keine Korrelation.
        return None


def kursreihen(db: Session, datenmodus: str = "HISTORISCH") -> dict[str, list[tuple]]:
    """Je Ticker die nach Datum sortierte Reihe (Zeitpunkt, Kurs)."""
    reihen: dict[str, list[tuple]] = defaultdict(list)
    zeilen = (
        db.query(AnalyseSnapshot.ticker, AnalyseSnapshot.snapshot_zeitpunkt,
                 AnalyseSnapshot.kurs_bei_snapshot)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .order_by(AnalyseSnapshot.ticker, AnalyseSnapshot.snapshot_zeitpunkt)
        .all()
    )
    for ticker, zeitpunkt, kurs in zeilen:
        if kurs and kurs > 0:
            reihen[ticker].append((zeitpunkt, kurs))
    return reihen


def kursnaehe_pruefen(db: Session, werte: dict[int, float],
                      zuordnung: dict[int, tuple],
                      datenmodus: str = "HISTORISCH",
                      fenster_tage: int = FENSTER_TAGE) -> dict:
    """Wie stark bildet ein Eingang die vorangegangene Kursentwicklung ab?

    Args:
        werte: {snapshot_id: Signalwert oder Rang}.
        zuordnung: {snapshot_id: (ticker, zeitpunkt)}.

    Returns:
        {"n", "rangkorrelation", "kursnah", "fenster_tage"} — `kursnah` ist
        None, wenn sich nichts berechnen ließ.
    """
    reihen = kursreihen(db, datenmodus)

    signal: list[float] = []
    rendite: list[float] = []
    for snapshot_id, wert in werte.items():
        eintrag = zuordnung.get(snapshot_id)
        if eintrag is None or wert is None:
            continue
        ticker, zeitpunkt = eintrag
        reihe = reihen.get(ticker)
        beginn = naechster_kurs(reihe, zeitpunkt - timedelta(days=fenster_tage))
        # Das Fenster endet einen Tag VOR dem Snapshot, damit die
        # Vergleichsrendite denselben Informationsstand hat wie das Signal.
        ende = naechster_kurs(reihe, zeitpunkt - timedelta(days=1))
        lauf = momentum_roh(beginn, ende)
        if lauf is None:
            continue
        signal.append(float(wert))
        rendite.append(lauf)

    korrelation = rangkorrelation(signal, rendite)
    ergebnis = {
        "n": len(signal),
        "rangkorrelation": None if korrelation is None else round(korrelation, 3),
        "kursnah": (None if korrelation is None
                    else abs(korrelation) >= SCHWELLE_KURSNAH),
        "fenster_tage": fenster_tage,
    }
    logger.info("Kursnähe: n=%d, Rangkorrelation=%s (Schwelle %.2f).",
                ergebnis["n"], ergebnis["rangkorrelation"], SCHWELLE_KURSNAH)
    return ergebnis
