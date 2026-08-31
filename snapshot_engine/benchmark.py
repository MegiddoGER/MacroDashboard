"""
snapshot_engine/benchmark.py — Marktrendite je Outcome (P1-04).

Bisher war jede Trefferquote absolut: „57 % der Kaufsignale stiegen." Ohne
Bezug zum Markt sagt das wenig — in einem Zeitraum, in dem 57 % aller Aktien
stiegen, ist das exakt null Leistung. Die Basisrate (`basis.anteil_steigend`)
mildert das, aber nur im Mittel über den gesamten Bestand: sie kann nicht
trennen, ob ein einzelnes Signal in einer starken oder schwachen Marktphase lag.

Dieses Modul hinterlegt je Outcome die Rendite eines Vergleichsindex über
DASSELBE Fenster. Damit wird aus einer Trefferquote eine Überrendite, und aus
„lag richtig" wird „schlug den Markt".

**Warum je Markt und nicht ein einziger Index.**
Die Überrendite ist eine Differenz zweier Prozentzahlen. Sie ist nur dann
sauber, wenn beide in derselben Währung gemessen sind: eine Xetra-Aktie in EUR
gegen den S&P 500 in USD zu rechnen würde die Wechselkursbewegung als Alpha
ausweisen. Der Index richtet sich deshalb nach dem Handelsplatz des Tickers,
nicht nach dem Sitz des Unternehmens — das hält auch P4-03 (Währungen werden
nirgends verrechnet) aus dieser Rechnung heraus.

**Warum das billig ist.**
Anders als die Outcomes selbst braucht das keine 611 Kursreihen, sondern vier.
Die Indexreihen werden einmal geladen und im Speicher nachgeschlagen; das
Nachtragen von 256.705 Bestands-Outcomes ist damit reine Rechenzeit ohne
weitere Netzabrufe.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# Handelsplatz-Suffix → Vergleichsindex. Der Schlüssel "" gilt für Ticker ohne
# Suffix, also die US-Notierungen (504 der 611 Ticker im Bestand).
#
# .DE/.F  Xetra bzw. Frankfurt → DAX. Auch MDAX-Werte werden gegen den DAX
#         gemessen: ein breiter Heimatmarktindex ist der übliche Bezug, und ein
#         eigener MDAX-Bezug würde die Vergleichbarkeit zwischen den beiden
#         Segmenten aufheben, ohne die Währungsfrage anders zu beantworten.
# .SW     SIX Swiss (CHF) → SMI
# .PA     Euronext Paris (EUR) → CAC 40
# .KS     Korea (KRW) → KOSPI
BENCHMARK_JE_SUFFIX: dict[str, str] = {
    "": "^GSPC",        # S&P 500 (USD)
    "DE": "^GDAXI",     # DAX (EUR)
    "F": "^GDAXI",      # Frankfurt — gleiche Währung, gleicher Markt
    "SW": "^SSMI",      # SMI (CHF)
    "PA": "^FCHI",      # CAC 40 (EUR)
    "KS": "^KS11",      # KOSPI (KRW)
}

# Ticker mit unbekanntem Suffix bekommen KEINEN Benchmark. Ein falscher Index
# wäre schlimmer als keiner: er erzeugt eine Überrendite, die in Wahrheit eine
# Währungs- oder Marktdifferenz ist, und die fällt später niemandem mehr auf.
BENCHMARK_UNBEKANNT: Optional[str] = None


def benchmark_fuer(ticker: str) -> Optional[str]:
    """Vergleichsindex für einen Ticker, oder None bei unbekanntem Markt."""
    if not ticker:
        return BENCHMARK_UNBEKANNT
    teile = ticker.rsplit(".", 1)
    suffix = teile[1].upper() if len(teile) == 2 else ""
    return BENCHMARK_JE_SUFFIX.get(suffix, BENCHMARK_UNBEKANNT)


def benoetigte_benchmarks(tickers) -> list[str]:
    """Die Indizes, die für eine Menge von Tickern gebraucht werden."""
    return sorted({b for b in (benchmark_fuer(t) for t in tickers) if b})


def rendite(hist: Optional[pd.DataFrame], von: datetime,
            bis: datetime) -> Optional[float]:
    """Indexrendite in Prozent zwischen zwei Stichtagen.

    Beide Kurse stammen aus derselben Reihe und damit derselben
    Anpassungsbasis — dasselbe Prinzip wie bei `basis_kurs` der Outcomes, wo
    ein Split zwischen zwei Bezugsbasen sonst einen Scheinverlust erzeugt.

    Returns:
        Rendite in Prozent, oder None wenn einer der Stichtage nicht gedeckt ist.
    """
    if hist is None or getattr(hist, "empty", True):
        return None

    from services.market_data_batch import kurs_am_stichtag

    kurs_von = kurs_am_stichtag(hist, von)
    kurs_bis = kurs_am_stichtag(hist, bis)
    if not kurs_von or kurs_von <= 0 or kurs_bis is None:
        return None
    return (kurs_bis - kurs_von) / kurs_von * 100.0


def ueberrendite(outcome_return: Optional[float],
                 benchmark_return: Optional[float]) -> Optional[float]:
    """Überrendite in Prozentpunkten: Titel minus Markt.

    Arithmetische Differenz, nicht geometrisch. Bei Horizonten von 7 bis 90
    Tagen und Renditen im niedrigen einstelligen Prozentbereich liegt der
    Unterschied zwischen beiden Definitionen weit unter der Fehlerspanne der
    Trefferquoten; die einfache Differenz ist dafür ohne Zwischenrechnung
    lesbar und lässt sich direkt aufsummieren.
    """
    if outcome_return is None or benchmark_return is None:
        return None
    return outcome_return - benchmark_return


def erfolg_gegen_benchmark(richtungssignal: str,
                           outcome_return: Optional[float],
                           benchmark_return: Optional[float],
                           mindest_vorsprung_pp: float) -> Optional[bool]:
    """Bewertet ein Signal gegen den Markt statt gegen null.

    Das ist die eigentliche Frage: ein KAUF in einem Monat, in dem der Index um
    8 % gestiegen ist, war keine gute Empfehlung, nur weil der Titel um 2 %
    zulegte. `erfolg_bewerten` in models.py hätte ihn als Treffer gezählt.

    NEUTRAL bleibt unbewertet, und Überrenditen unterhalb von
    `mindest_vorsprung_pp` gelten als Rauschen — dieselbe Logik wie
    MIN_BEWEGUNG_PCT bei der absoluten Bewertung, nur auf die Differenz
    angewandt.

    Returns:
        True/False, oder None wenn nicht bewertbar.
    """
    if richtungssignal not in ("KAUF", "VERKAUF"):
        return None
    diff = ueberrendite(outcome_return, benchmark_return)
    if diff is None or abs(diff) < mindest_vorsprung_pp:
        return None
    return diff > 0 if richtungssignal == "KAUF" else diff < 0


def benchmark_reihen_laden(benchmarks: list[str], von: datetime,
                           bis: datetime) -> dict[str, pd.DataFrame]:
    """Lädt die Indexreihen einmalig für das gesamte Zeitfenster.

    Der Puffer vorn und hinten deckt Feiertage und Wochenenden ab, damit
    `kurs_am_stichtag` auch an Randterminen einen Handelstag findet.
    """
    if not benchmarks:
        return {}

    from services.market_data_batch import batch_download_ohlcv

    reihen = batch_download_ohlcv(
        benchmarks,
        start=von - timedelta(days=10),
        end=bis + timedelta(days=10),
    )
    fehlend = [b for b in benchmarks if b not in reihen]
    if fehlend:
        logger.warning("Benchmark-Reihen fehlen: %s — betroffene Outcomes "
                       "bleiben ohne Vergleichswert.", ", ".join(fehlend))
    return reihen
