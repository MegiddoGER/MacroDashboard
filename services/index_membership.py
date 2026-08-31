"""
services/index_membership.py — Wann ein Titel in den Index kam (P4-07).

Die Signal-Engine misst auf einem Universum, das die **heutige**
Index-Mitgliedschaft rückwärts abspielt. Für die meisten Indikatoren ist das
eine Randnotiz; für Querschnitts-Momentum (P2-02) ist es die zentrale
Bedrohung, weil Momentum auf genau der Größe rangt, die über Index-Aufnahme
entscheidet: der vergangenen Rendite.

Konkret sind es zwei verschiedene Verzerrungen:

- **Aufnahmen.** Ein Titel, der 2025 in den S&P 500 kam, steckt im Universum
  mit seiner gesamten Vorgeschichte — und er kam meist nach starker
  Entwicklung hinein. Genau diese Titel besetzen die oberen Momentum-Dezile,
  und zwar mit einer Vergangenheit, die im Nachhinein garantiert gut aussieht.
  **Diese Hälfte lässt sich prüfen**, und darum geht es hier.
- **Ausschlüsse.** Titel, die nach schlechter Entwicklung aus dem Index
  geflogen sind, fehlen ganz. Sie hätten die unteren Dezile besetzt; deren
  gemessene Rendite ist dadurch zu gut. Diese Hälfte wirkt also GEGEN einen
  gefundenen Momentum-Vorsprung und lässt sich mit dieser Quelle nicht
  schließen — Wikipedia führt die Änderungshistorie seit einem Seitenumbau
  nicht mehr.

Quelle ist dieselbe Wikipedia-Tabelle, aus der `services/screener.py` die
Konstituenten liest, nur die bislang ungenutzte Spalte `Date added`. Kein
Schlüssel nötig, kein zusätzlicher Abruf gegenüber dem Screener.

**Nur der S&P 500.** Für Xetra kommt das Universum aus einer lokalen CSV ohne
Aufnahmedaten; dort ist die Prüfung nicht möglich und liefert bewusst
„unbekannt" statt einer Vermutung.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

WIKIPEDIA_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Spalten der Komponententabelle, gegen eine echte Antwort geprüft
# (2026-08-31: 503 Zeilen, alle 503 mit Datum).
SPALTE_SYMBOL = "Symbol"
SPALTE_DATUM = "Date added"


def sp500_aufnahmedaten() -> Optional[dict[str, datetime]]:
    """Ticker → Datum der Aufnahme in den S&P 500.

    Returns:
        Dict der **heutigen** Mitglieder, oder None wenn die Tabelle nicht
        ladbar war. None heißt „unbekannt", nicht „leer": eine leere Zuordnung
        würde stromabwärts wie „kein Titel war je Mitglied" aussehen und die
        Survivorship-Prüfung stillschweigend alles verwerfen lassen.
    """
    try:
        import pandas as pd
        import requests

        import config

        html = requests.get(
            WIKIPEDIA_SP500,
            headers={"User-Agent": config.SCRAPER_USER_AGENT},
            timeout=30,
        ).text
        tabelle = pd.read_html(html)[0]
    except Exception as e:
        logger.warning("S&P-500-Aufnahmedaten nicht ladbar: %s — "
                       "Survivorship-Prüfung entfällt.", e)
        return None

    if SPALTE_SYMBOL not in tabelle.columns or SPALTE_DATUM not in tabelle.columns:
        logger.warning("S&P-500-Tabelle ohne erwartete Spalten (%s) — "
                       "Wikipedia-Struktur geändert?", list(tabelle.columns)[:6])
        return None

    import pandas as pd

    # Gattungspunkt wie im Screener auf yfinance-Schreibweise bringen (BRK.B → BRK-B).
    symbole = tabelle[SPALTE_SYMBOL].astype(str).str.replace(".", "-", regex=False)
    daten = pd.to_datetime(tabelle[SPALTE_DATUM], errors="coerce")

    ergebnis: dict[str, datetime] = {}
    for symbol, datum in zip(symbole, daten):
        if pd.isna(datum):
            continue
        ergebnis[symbol.strip().upper()] = datum.to_pydatetime()

    fehlend = len(tabelle) - len(ergebnis)
    logger.info("S&P-500-Aufnahmedaten: %d Mitglieder, %d ohne verwertbares Datum.",
                len(ergebnis), fehlend)
    return ergebnis


def war_mitglied(ticker: str, zeitpunkt: datetime,
                 aufnahmedaten: Optional[dict[str, datetime]]) -> Optional[bool]:
    """War der Titel zu diesem Zeitpunkt bereits Index-Mitglied?

    Returns:
        True/False, oder **None wenn es sich nicht entscheiden lässt**.

    Der None-Fall ist der wichtige. Ein Ticker, der nicht in der Tabelle steht,
    ist entweder gar kein S&P-Wert (jeder Xetra-Titel) oder ein früheres
    Mitglied, das inzwischen entfernt wurde. Diese beiden Fälle sind aus der
    heutigen Tabelle nicht zu unterscheiden — sie als „nicht Mitglied" zu
    zählen würde das halbe Universum verwerfen, als „Mitglied" würde es die
    Prüfung wirkungslos machen. Dieselbe Entscheidung wie bei
    `benchmark.BENCHMARK_UNBEKANNT`: lieber „unbekannt" als geraten.
    """
    if not aufnahmedaten or not ticker or zeitpunkt is None:
        return None
    aufnahme = aufnahmedaten.get(ticker.strip().upper())
    if aufnahme is None:
        return None
    return zeitpunkt >= aufnahme
