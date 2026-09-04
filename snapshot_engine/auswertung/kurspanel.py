"""
snapshot_engine/auswertung/kurspanel.py — Beobachtungen aus reinen Kursreihen.

**Wozu es das gibt.** Jede Kandidatenmessung dieses Projekts hing bisher an
`AnalyseSnapshot`: die Snapshots liefern die Stichtage, ihre Outcomes die
Renditen. Das ist richtig, solange die Frage die Snapshots braucht — bei den
zehn Chartinstrumenten tut sie das, denn dort steht die Deutung im Snapshot.

Die Insider-Gegenprobe aus Auftrag C braucht sie nicht. Ihre Frage lautet:
haben in den sechs Monaten vor dem Stichtag mehrere Insider gekauft, und wie
lief der Titel danach gegen seinen Index. Der erste Teil steht in
`InsiderGeschaeft`, der zweite in `KursHistorie`. Kein Indikator, kein Score,
keine SMC-Struktur geht ein.

Der Unterschied ist der Grund, warum diese Datei existiert: Snapshots fuer
4.164 Titel aufzuzeichnen kostet gut zwei Tage Rechenzeit, die Kursreihen
dafuer eine halbe Stunde. Auf einem Universum, das nur fuer eine Gegenprobe
gebraucht wird, ist das der Unterschied zwischen „machbar" und „lohnt nicht".

**Die Semantik ist die der Outcomes, absichtlich bis ins Detail.** Ein Befund
aus diesem Panel muss mit §2n vergleichbar sein, sonst misst die Gegenprobe
etwas anderes als das, was sie pruefen soll:

* Der Horizont zaehlt **Kalendertage**, nicht Handelstage — wie
  `models.faellig_am = zeitpunkt + timedelta(days=horizont)`.
* Basis- und Zielkurs stammen aus **derselben Reihe** und damit derselben
  Anpassungsbasis. Ein Split zwischen zwei Bezugsbasen erzeugte sonst einen
  Scheinverlust; das ist derselbe Grund, aus dem `_basis_kurs_bestimmen` den
  live gespeicherten Kurs verwirft.
* Die Rendite ist in **Prozent**, die Ueberrendite in Prozentpunkten als
  arithmetische Differenz — wie `benchmark.ueberrendite`.
* Der Vergleichsindex richtet sich nach dem **Handelsplatz-Suffix**, nicht
  nach dem Sitz des Unternehmens (`benchmark.benchmark_fuer`), damit keine
  Wechselkursbewegung als Alpha erscheint.

**Ein Unterschied, der Absicht ist.** `market_data_batch.kurs_am_stichtag`
nimmt den naechsten Handelstag ab dem Stichtag, ohne Obergrenze fuer den
Abstand. Auf dem bisherigen Universum ist das harmlos — 611 laufend
gehandelte Titel haben keine Luecken. Auf einem Universum mit kleinen und
teilweise ausgelaufenen Titeln ist es gefaehrlich: endet eine Reihe im Maerz
und faellt der Zielstichtag in den April, liefert `searchsorted` still den
letzten Kurs vor dem Ende, und aus einem 90-Tage-Horizont wird unbemerkt ein
beliebig langer. `_kurs_nahe` setzt deshalb eine Obergrenze
(`MAX_ABSTAND_TAGE`) und gibt sonst None zurueck. Die betroffene Beobachtung
faellt heraus — das ist der Survivorship-Rand, und er gehoert gezaehlt, nicht
gefuellt.
"""

import logging
from bisect import bisect_left
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from database import KursHistorie
from snapshot_engine.benchmark import (
    benchmark_fuer, benchmark_reihen_laden, benoetigte_benchmarks, ueberrendite,
)

logger = logging.getLogger(__name__)


# Wie weit ein gefundener Handelstag hoechstens vom Stichtag entfernt sein
# darf. Vier Kalendertage decken ein langes Wochenende mit Feiertag ab; alles
# darueber ist eine Luecke in der Reihe und keine Boersenpause.
MAX_ABSTAND_TAGE = 4

# Abstand zwischen zwei Stichtagen desselben Tickers. Sieben Tage ergeben je
# Titel und Jahr rund 52 Beobachtungen — dieselbe Groessenordnung wie der
# Snapshot-Bestand, der woechentlich aufgezeichnet wurde.
#
# Beobachtungen desselben Tickers ueberlappen sich damit auf 30 und 90 Tagen
# stark. Das ist bei den Snapshots nicht anders und in §2n bereits
# ausgewiesen: 10.166 Zeilen sind auf 90 Tagen 1.106 unabhaengige
# Beobachtungen. Wer aus diesem Panel Signifikanz rechnet, muss dieselbe
# Korrektur anwenden.
STICHTAG_ABSTAND_TAGE = 7


class Beobachtung:
    """Eine Zeile des Panels — Stichtag, Rendite, Marktrendite.

    Traegt bewusst dieselben Felder, die `insider._beobachtungen` aus den
    Outcomes zieht, damit die Auswertung nicht zwischen zwei Quellen
    unterscheiden muss.
    """

    __slots__ = ("id", "ticker", "zeitpunkt", "rendite", "benchmark_rendite")

    def __init__(self, id: int, ticker: str, zeitpunkt: datetime,
                 rendite: float, benchmark_rendite: Optional[float]):
        self.id = id
        self.ticker = ticker
        self.zeitpunkt = zeitpunkt
        self.rendite = rendite
        self.benchmark_rendite = benchmark_rendite

    def __repr__(self) -> str:
        return (f"Beobachtung({self.ticker} {self.zeitpunkt:%Y-%m-%d} "
                f"{self.rendite:+.2f}%)")


def _reihe_laden(db: Session, ticker: str
                 ) -> tuple[list[datetime], list[float]]:
    """Die gespeicherte Kursreihe eines Tickers als zwei parallele Listen.

    Zwei Listen statt eines DataFrames, weil je Ticker einige tausend
    Nachschlaege folgen und `bisect` auf einer Liste um Groessenordnungen
    billiger ist als ein pandas-Index-Zugriff.
    """
    zeilen = (
        db.query(KursHistorie.datum, KursHistorie.schluss)
        .filter(KursHistorie.ticker == ticker)
        .filter(KursHistorie.schluss.isnot(None))
        .order_by(KursHistorie.datum)
        .all()
    )
    return [z[0] for z in zeilen], [float(z[1]) for z in zeilen]


def _kurs_nahe(daten: list[datetime], kurse: list[float], stichtag: datetime,
               max_abstand: int = MAX_ABSTAND_TAGE) -> Optional[float]:
    """Schlusskurs am Stichtag oder am naechsten Handelstag danach.

    Anders als `kurs_am_stichtag` mit einer Obergrenze fuer den Abstand —
    siehe Modul-Docstring. Liegt kein Handelstag innerhalb des Fensters,
    ist das Ergebnis None und die Beobachtung faellt heraus.
    """
    if not daten:
        return None
    position = bisect_left(daten, stichtag)
    if position >= len(daten):
        return None
    if (daten[position] - stichtag).days > max_abstand:
        return None
    return kurse[position]


def _benchmark_rendite(reihe, von: datetime, bis: datetime) -> Optional[float]:
    """Indexrendite ueber dasselbe Fenster, in Prozent."""
    from snapshot_engine.benchmark import rendite
    return rendite(reihe, von, bis)


def panel_bauen(db: Session, tickers: Iterable[str], horizont: int,
                von: Optional[datetime] = None,
                bis: Optional[datetime] = None,
                abstand_tage: int = STICHTAG_ABSTAND_TAGE,
                max_abstand: int = MAX_ABSTAND_TAGE) -> list[Beobachtung]:
    """Baut die Beobachtungen aus `KursHistorie`.

    Args:
        tickers: Das Universum. Titel ohne gespeicherte Reihe fallen still
            heraus — sie sind der Survivorship-Rand und werden gezaehlt.
        horizont: Kalendertage bis zur Faelligkeit (7, 30 oder 90).
        von/bis: Zeitraum der STICHTAGE. `bis` bezieht sich auf den Stichtag,
            nicht auf die Faelligkeit; Beobachtungen, deren Zielkurs noch
            nicht vorliegt, fallen ohnehin heraus.

    Returns:
        Liste von `Beobachtung`, aufsteigend je Ticker und Stichtag. Die `id`
        ist fortlaufend und hat ausserhalb dieses Panels keine Bedeutung.
    """
    tickers = [t for t in dict.fromkeys(tickers) if t]
    if not tickers:
        return []

    von = von or datetime(2016, 1, 1)
    bis = bis or datetime.now()

    benchmark_reihen = benchmark_reihen_laden(
        benoetigte_benchmarks(tickers), von, bis + timedelta(days=horizont))

    beobachtungen: list[Beobachtung] = []
    naechste_id = 0
    ohne_reihe = ohne_basis = ohne_ziel = 0

    for ticker in tickers:
        daten, kurse = _reihe_laden(db, ticker)
        if not daten:
            ohne_reihe += 1
            continue

        index = benchmark_fuer(ticker)
        reihe = benchmark_reihen.get(index) if index else None

        stichtag = max(von, daten[0])
        letzter = min(bis, daten[-1])
        while stichtag <= letzter:
            basis = _kurs_nahe(daten, kurse, stichtag, max_abstand)
            if basis is None or basis <= 0:
                ohne_basis += 1
                stichtag += timedelta(days=abstand_tage)
                continue

            faellig = stichtag + timedelta(days=horizont)
            ziel = _kurs_nahe(daten, kurse, faellig, max_abstand)
            if ziel is None:
                # Der Regelfall am rechten Rand und bei ausgelaufenen Reihen.
                ohne_ziel += 1
                stichtag += timedelta(days=abstand_tage)
                continue

            beobachtungen.append(Beobachtung(
                id=naechste_id,
                ticker=ticker,
                zeitpunkt=stichtag,
                rendite=round((ziel - basis) / basis * 100, 4),
                benchmark_rendite=_benchmark_rendite(reihe, stichtag, faellig),
            ))
            naechste_id += 1
            stichtag += timedelta(days=abstand_tage)

    logger.info(
        "Kurspanel %dT: %d Beobachtungen ueber %d Ticker "
        "(%d ohne Reihe, %d ohne Basiskurs, %d ohne Zielkurs).",
        horizont, len(beobachtungen), len(tickers) - ohne_reihe,
        ohne_reihe, ohne_basis, ohne_ziel)
    return beobachtungen


def als_auswertungsform(beobachtungen: list[Beobachtung]
                        ) -> tuple[dict[int, tuple], list[tuple]]:
    """Bringt das Panel in die Form, die `insider_auswerten` erwartet.

    Returns:
        ({id: (ticker, zeitpunkt)},
         [(id, rendite, benchmark_rendite), ...])

    Damit ist das Panel gegen die Outcome-Abfrage austauschbar, ohne dass die
    Auswertung zwei Codepfade fuehren muss.
    """
    zuordnung = {b.id: (b.ticker, b.zeitpunkt) for b in beobachtungen}
    zeilen = [(b.id, b.rendite, b.benchmark_rendite) for b in beobachtungen]
    return zuordnung, zeilen


def abdeckung_je_jahr(beobachtungen: list[Beobachtung]) -> dict[int, int]:
    """Beobachtungen je Kalenderjahr — der Blick vor der Jahresstabilitaet.

    §2n hat gezeigt, warum das noetig ist: das einzige negative Jahr war das
    duennste (272 Cluster-Zeilen gegen 1.000-2.000 in den Vorjahren). Wer die
    Jahresverteilung nicht kennt, deutet Rauschen als Regimewechsel.
    """
    je_jahr: dict[int, int] = {}
    for b in beobachtungen:
        je_jahr[b.zeitpunkt.year] = je_jahr.get(b.zeitpunkt.year, 0) + 1
    return dict(sorted(je_jahr.items()))
