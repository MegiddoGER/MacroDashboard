"""
services/cross_sectional_momentum.py — Querschnitts-Momentum (P2-02).

Alle bisherigen Indikatoren der Engine sind ABSOLUT: sie schauen einen Titel
allein an und fragen, ob er über seiner SMA 200 liegt, ob sein RSI unter 30
steht, ob der Kurs über dem VWAP notiert. §2b hat gezeigt, dass keiner davon
gegen den Markt einen Vorsprung trägt — und das ist keine Überraschung, wenn
man sich ansieht, was sie messen: sechs Varianten derselben Frage „steigt der
Kurs gerade?", beantwortet ohne jeden Bezug darauf, was die anderen Titel tun.

Querschnitts-Momentum stellt die Frage anders: **nicht ob ein Titel steigt,
sondern ob er stärker steigt als die anderen.** Das ist von Konstruktion her
relativ und misst damit genau die Größe, die seit P1-04 auswertbar ist.

**Warum 12 Monate minus 1 (`LOOKBACK_TAGE` / `SKIP_TAGE`).**
Die klassische Form nach Jegadeesh/Titman rangt über die Rendite der letzten
zwölf Monate, lässt dabei aber den jüngsten Monat aus. Der Grund ist die
kurzfristige Umkehr: auf Wochen- bis Monatssicht laufen Gewinner überdurchschnittlich
oft zurück, auf Jahressicht laufen sie weiter. Wer den letzten Monat mitnimmt,
mischt beide Effekte gegeneinander und misst am Ende keinen von beidem.

**Warum je Handelsplatz gerangt wird.**
Dieselbe Frage wie bei `snapshot_engine/benchmark.py`: eine Rangliste über
Xetra- und US-Titel gemeinsam würde die Wechselkursbewegung als Momentum
ausweisen — in einem Quartal mit starkem Dollar landeten alle US-Titel oben,
unabhängig von ihrer Entwicklung. Die Gruppierung ist deshalb ein Parameter
(`gruppe_fuer`), den die Aufrufstelle setzt; dieses Modul kennt keine
Benchmark-Zuordnung und bleibt frei von der Abhängigkeit.

Das Modul rechnet nur — es lädt nichts. Kursbeschaffung und Zeitachse liegen
bei der Aufrufstelle, damit dieselbe Logik den Live-Pfad und die historische
Auswertung bedienen kann.
"""

import logging
from typing import Callable, Optional, Sequence

logger = logging.getLogger(__name__)

# Rückschau in Kalendertagen. 365 statt „252 Handelstage", weil die
# Aufrufstellen mit Kalenderdaten arbeiten (Snapshot-Zeitpunkte, Stichtage).
LOOKBACK_TAGE = 365

# Der ausgelassene jüngste Monat. Siehe Modulkopf: kurzfristige Umkehr.
SKIP_TAGE = 30

# Unterhalb dieser Besetzung wird KEIN Rang vergeben. Ein Perzentil über sechs
# Titel ist keine Aussage über den Querschnitt, sondern über sechs Titel — und
# an den Rändern des Datenbestands (erste und letzte Wochen) ist die Besetzung
# genau so dünn.
MIN_QUERSCHNITT = 20


def momentum_roh(kurs_beginn: Optional[float],
                 kurs_ende: Optional[float]) -> Optional[float]:
    """Rendite über das Rückschaufenster, in Prozent.

    Beide Kurse müssen aus derselben Reihe stammen — sonst zerlegt ein Split
    dazwischen das Verhältnis. Dasselbe Prinzip wie bei `basis_kurs` der
    Outcomes.
    """
    if kurs_beginn is None or kurs_ende is None or kurs_beginn <= 0:
        return None
    return (kurs_ende - kurs_beginn) / kurs_beginn * 100.0


def perzentil_raenge(werte: dict[str, Optional[float]],
                     minimum: int = MIN_QUERSCHNITT) -> dict[str, float]:
    """Ordnet jedem Ticker seinen Perzentilrang im Querschnitt zu (0–100).

    0 ist der schwächste, 100 der stärkste Titel des Querschnitts. Gleiche
    Werte bekommen denselben Rang (Durchschnittsrang), damit eine Gruppe
    identischer Werte nicht künstlich gespreizt wird.

    Ein Rang ist eine Aussage ÜBER DEN QUERSCHNITT, nicht über den Titel:
    dieselbe Rendite kann in einem Quartal Rang 90 und im nächsten Rang 30
    bedeuten. Genau das ist der Punkt — der Marktanteil der Bewegung ist
    herausgerechnet, ohne dass ein Index dafür nötig wäre.

    Returns:
        Nur Ticker mit Wert; leer, wenn der Querschnitt zu dünn besetzt ist.
    """
    gefuellt = {t: w for t, w in werte.items() if w is not None}
    if len(gefuellt) < minimum:
        return {}

    sortiert = sorted(gefuellt.items(), key=lambda p: p[1])
    n = len(sortiert)
    if n == 1:
        return {sortiert[0][0]: 50.0}

    raenge: dict[str, float] = {}
    i = 0
    while i < n:
        # Bindungsgruppe bestimmen und allen denselben Durchschnittsrang geben.
        j = i
        while j + 1 < n and sortiert[j + 1][1] == sortiert[i][1]:
            j += 1
        mittlerer_index = (i + j) / 2.0
        rang = mittlerer_index / (n - 1) * 100.0
        for k in range(i, j + 1):
            raenge[sortiert[k][0]] = round(rang, 2)
        i = j + 1

    return raenge


def raenge_je_gruppe(werte: dict[str, Optional[float]],
                     gruppe_fuer: Callable[[str], Optional[str]],
                     minimum: int = MIN_QUERSCHNITT) -> dict[str, float]:
    """Perzentilränge, getrennt je Gruppe (in der Praxis: je Handelsplatz).

    Titel ohne Gruppe bekommen keinen Rang. Das ist dieselbe Entscheidung wie
    bei `benchmark.BENCHMARK_UNBEKANNT`: ein Rang gegen die falsche
    Vergleichsgruppe wäre schlimmer als keiner, weil er später wie eine
    Aussage aussieht.
    """
    je_gruppe: dict[str, dict[str, Optional[float]]] = {}
    for ticker, wert in werte.items():
        gruppe = gruppe_fuer(ticker)
        if gruppe is None:
            continue
        je_gruppe.setdefault(gruppe, {})[ticker] = wert

    ergebnis: dict[str, float] = {}
    for gruppe, teilmenge in je_gruppe.items():
        raenge = perzentil_raenge(teilmenge, minimum)
        if not raenge:
            logger.debug("Querschnitt zu dünn (%s): %d Titel, mindestens %d nötig.",
                         gruppe, len(teilmenge), minimum)
        ergebnis.update(raenge)
    return ergebnis


def dezil(rang: Optional[float]) -> Optional[int]:
    """Dezil 1–10 zu einem Perzentilrang; 10 ist das stärkste."""
    if rang is None:
        return None
    return min(10, int(rang // 10) + 1)


def normiert(rang: Optional[float]) -> Optional[float]:
    """Perzentilrang auf die Skala [−1, +1], wie sie die Score-Kategorien nutzen.

    Damit ließe sich der Rang ohne Umrechnung als Kategorie-Score führen —
    aber erst, wenn er einen belegten Vorsprung zeigt. Bis dahin wird er nur
    gemessen (siehe CONTEXT.md §7: nichts in den Score, was nicht belegt ist).
    """
    if rang is None:
        return None
    return round(rang / 50.0 - 1.0, 4)


def naechster_kurs(reihe: Optional[Sequence[tuple]], ziel,
                   toleranz_tage: int = 10):
    """Kurs aus einer nach Datum sortierten Reihe, möglichst nah am Zieldatum.

    Args:
        reihe: aufsteigend sortierte (datetime, kurs)-Paare eines Tickers
        ziel: gesuchtes Datum
        toleranz_tage: darüber hinaus gilt der Wert als nicht vorhanden

    Die Toleranz ist nötig, weil die Snapshot-Kadenz in HANDELSTAGEN läuft
    (~10 Kalendertage). Ohne sie träfe ein Zieldatum fast nie eine Zeile; mit
    einer zu großen wäre das Rückschaufenster unscharf. None statt eines
    entfernten Nachbarn zu liefern ist die konservative Wahl.
    """
    import bisect

    if not reihe:
        return None

    daten = [z for z, _ in reihe]
    i = bisect.bisect_left(daten, ziel)

    kandidaten = []
    if i < len(reihe):
        kandidaten.append(reihe[i])
    if i > 0:
        kandidaten.append(reihe[i - 1])
    if not kandidaten:
        return None

    zeitpunkt, kurs = min(kandidaten, key=lambda p: abs((p[0] - ziel).days))
    if abs((zeitpunkt - ziel).days) > toleranz_tage:
        return None
    return kurs
