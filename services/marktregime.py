"""
services/marktregime.py — Unter welcher Bedingung gilt ein Signal? (P2-03)

Der Befund aus §2h, der dieses Modul auslöst: drei unabhängig konstruierte
Signale — stetiger Trend, stetiger SMA-Cross, Analysten-Zielrevision — zeigen
**dasselbe Jahresmuster**. Stark 2020, 2022 und 2024, negativ 2021. Dass drei
verschiedene Bauweisen dieselben Jahre gut und dieselben Jahre schlecht finden,
sagt: die fehlende Größe ist nicht ein viertes Signal, sondern die Bedingung,
unter der ein Signal gilt.

**Warum nicht der ADX, wie P2-03 es formuliert.** Der ADX braucht Tageshochs
und -tiefs. Der Snapshot-Bestand führt nur Schlusskurse im Achttagetakt; er
ließe sich daraus nicht rekonstruieren, sondern nur nachbauen — und ein
nachgebauter ADX auf acht Tagen wäre eine andere Größe als die, die in
`services/technical.py` berechnet wird. Der ADX ist außerdem eine Eigenschaft
des **einzelnen Titels**; das gemessene Muster ist über alle Titel gleichzeitig
sichtbar und damit marktweit. Gemessen wird deshalb das Regime des **Index**.

Zwei Größen, beide aus den Indexreihen, beide punkt-in-zeit:

- `vola` — annualisierte realisierte Volatilität der Tagesrenditen über die
  letzten `VOLA_FENSTER_TAGE`. Das Regime heißt HOCH, wenn sie über ihrem
  eigenen **nachlaufenden** Median der letzten zwei Jahre liegt.
- `ueber_ma` — steht der Index über seinem eigenen langen gleitenden Mittel?

**Kein optimierter Schwellenwert.** Die Grenze ist der nachlaufende Median der
Größe selbst, nicht ein Wert, der die Trennung schön macht. Das ist der
Unterschied zu `schwellensuche.py`: dort wurden dreizehn Kandidaten geprüft und
die Korrektur entsprechend geweitet; hier gibt es genau eine Regel, die zu
jedem Zeitpunkt aus der eigenen Vergangenheit folgt. Wer die Grenze stattdessen
über den Gesamtzeitraum legt (etwa als Terzil), hat die Zukunft mitbenutzt.

**Kein Look-ahead.** Jede Größe endet `MIN_ABSTAND_TAGE` vor dem Stichtag. Ein
Index-Schlusskurs desselben Tages stünde erst nach Handelsschluss fest, ein
Snapshot kann früher entstanden sein.
"""

import logging
import math
import statistics
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# Fenster der realisierten Volatilität, in Handelstagen der Indexreihe.
VOLA_FENSTER = 63          # rund ein Quartal
# Nachlaufender Vergleichszeitraum, aus dem der Median stammt.
VOLA_VERGLEICH = 504       # rund zwei Jahre
# Langes Mittel für die Richtungsfrage.
MA_FENSTER = 200

MIN_ABSTAND_TAGE = 1

HOCH = "HOCH"
NIEDRIG = "NIEDRIG"
AUF = "AUF"
AB = "AB"


def _schlusskurse(rahmen) -> list[tuple[datetime, float]]:
    """(Datum, Schlusskurs) einer Indexreihe, aufsteigend und zonenlos."""
    import pandas as pd

    if rahmen is None or len(rahmen) == 0 or "Close" not in rahmen.columns:
        return []
    index = pd.DatetimeIndex(rahmen.index)
    if index.tz is not None:
        index = index.tz_localize(None)

    reihe = []
    for zeitpunkt, kurs in zip(index, rahmen["Close"]):
        if kurs is None or pd.isna(kurs) or float(kurs) <= 0:
            continue
        reihe.append((zeitpunkt.to_pydatetime(), float(kurs)))
    reihe.sort(key=lambda e: e[0])
    return reihe


def regime_reihe(rahmen) -> list[dict]:
    """Regimezustand je Handelstag einer Indexreihe.

    Returns:
        Liste aus {datum, vola, vola_regime, ueber_ma, richtungs_regime},
        aufsteigend nach Datum. Zustände, für die das Fenster noch nicht voll
        ist, tragen None — sie fallen später aus der Auswertung, statt mit
        einer halben Historie geraten zu werden.
    """
    kurse = _schlusskurse(rahmen)
    if len(kurse) < 2:
        return []

    # Log-Renditen, damit die Volatilität additiv über die Zeit ist.
    renditen: list[Optional[float]] = [None]
    for (_, vorher), (_, jetzt) in zip(kurse, kurse[1:]):
        renditen.append(math.log(jetzt / vorher) if vorher > 0 else None)

    ergebnis: list[dict] = []
    vola_verlauf: list[float] = []

    for i, (datum, kurs) in enumerate(kurse):
        vola = None
        fenster = [r for r in renditen[max(1, i - VOLA_FENSTER + 1):i + 1]
                   if r is not None]
        if len(fenster) >= VOLA_FENSTER // 2:
            # Annualisiert mit 252 Handelstagen — die übliche Konvention, und
            # für einen Vergleich mit dem eigenen Median ohnehin nur ein
            # Skalenfaktor.
            vola = statistics.pstdev(fenster) * math.sqrt(252) * 100.0

        vola_regime = None
        if vola is not None:
            # Der Median stammt aus der VERGANGENHEIT dieser Reihe, nicht aus
            # dem Gesamtzeitraum. Sonst entschiede die Zukunft mit darüber, was
            # damals als hohe Volatilität galt.
            vergleich = vola_verlauf[-VOLA_VERGLEICH:]
            if len(vergleich) >= VOLA_VERGLEICH // 2:
                vola_regime = HOCH if vola > statistics.median(vergleich) else NIEDRIG
            vola_verlauf.append(vola)

        ueber_ma = None
        if i + 1 >= MA_FENSTER:
            mittel = sum(k for _, k in kurse[i + 1 - MA_FENSTER:i + 1]) / MA_FENSTER
            ueber_ma = kurs > mittel

        ergebnis.append({
            "datum": datum,
            "vola": vola,
            "vola_regime": vola_regime,
            "ueber_ma": ueber_ma,
            "richtungs_regime": None if ueber_ma is None else (AUF if ueber_ma else AB),
        })

    besetzt = sum(1 for e in ergebnis if e["vola_regime"] is not None)
    logger.info("Regime: %d Handelstage, davon %d mit vollständigem Fenster.",
                len(ergebnis), besetzt)
    return ergebnis


def regime_am(reihe: Optional[list[dict]], zeitpunkt: datetime,
              min_abstand_tage: int = MIN_ABSTAND_TAGE) -> Optional[dict]:
    """Der letzte Regimezustand, der zum Zeitpunkt sicher bekannt war.

    Ein Index-Schlusskurs steht erst nach Handelsschluss fest; ein Snapshot
    kann früher am selben Tag entstanden sein. Deshalb der Abstand, aus
    demselben Grund wie in `services/pead.py`.
    """
    if not reihe or zeitpunkt is None:
        return None
    grenze = zeitpunkt - timedelta(days=min_abstand_tage)
    for eintrag in reversed(reihe):
        if eintrag["datum"] <= grenze:
            return eintrag
    return None


def regime_reihen_laden(benchmarks: list[str], von: datetime,
                        bis: datetime) -> dict[str, list[dict]]:
    """Regimereihen je Index, über `benchmark.benchmark_reihen_laden`.

    Der Vorlauf ist kein Komfort, sondern notwendig: der nachlaufende Median
    braucht zwei Jahre Historie, bevor er den ersten Zustand liefern kann.
    """
    from snapshot_engine.benchmark import benchmark_reihen_laden

    vorlauf = von - timedelta(days=int((VOLA_VERGLEICH + VOLA_FENSTER) * 1.6))
    rahmen = benchmark_reihen_laden(benchmarks, vorlauf, bis)

    reihen: dict[str, list[dict]] = {}
    for name, daten in rahmen.items():
        reihe = regime_reihe(daten)
        if reihe:
            reihen[name] = reihe
    fehlend = [b for b in benchmarks if b not in reihen]
    if fehlend:
        logger.warning("Regimereihen fehlen: %s — betroffene Snapshots bleiben "
                       "ohne Regime.", ", ".join(fehlend))
    return reihen
