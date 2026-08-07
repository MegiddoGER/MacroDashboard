"""
services/market_data_batch.py — Gebündelter OHLCV-Abruf für viele Ticker.

Extrahiert das Chunk-Download-Muster aus services/screener.py, damit die
Signal-Qualitäts-Engine hunderte Ticker abrufen kann, ohne pro Ticker einen
eigenen Netzwerk-Call abzusetzen.

Ein einzelner yf.download()-Aufruf mit 50 Tickern ersetzt 50 Einzelabrufe —
das ist der Unterschied zwischen einem Lauf über das Screener-Universum in
Minuten statt Stunden (und ohne Rate-Limit-Sperre).
"""

import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

OHLCV_SPALTEN = ["Open", "High", "Low", "Close", "Volume"]

# yfinance beantwortet Multi-Ticker-Downloads am zuverlässigsten in dieser
# Größenordnung; darüber häufen sich unvollständige Antworten.
STANDARD_CHUNK_SIZE = 50


def einzelnen_ticker_extrahieren(data: pd.DataFrame, ticker: str,
                                 min_bars: int = 0) -> Optional[pd.DataFrame]:
    """Löst die OHLCV-Daten eines Tickers aus einem Batch-Download heraus.

    yfinance liefert bei Multi-Ticker-Downloads MultiIndex-Spalten
    (Level 0 = Preis, Level 1 = Ticker); bei genau einem Ticker einfache
    Spalten.

    Args:
        data: Rohes Ergebnis von yf.download()
        ticker: Gesuchtes Symbol
        min_bars: Mindestanzahl Bars, sonst None

    Returns:
        DataFrame mit OHLCV-Spalten, oder None.
    """
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if ticker not in data.columns.get_level_values(1):
                return None
            sub = data.xs(ticker, level=1, axis=1)
        else:
            sub = data

        if sub is None or not isinstance(sub, pd.DataFrame) or sub.empty:
            return None

        if not all(spalte in sub.columns for spalte in OHLCV_SPALTEN):
            return None

        sub = sub[OHLCV_SPALTEN].dropna()
        # Leere Frames entstehen bei delisteten Tickern (yfinance liefert dann
        # nur NaN-Zeilen) — die dürfen nie als gültige Daten durchgehen, auch
        # nicht bei min_bars=0.
        if sub.empty or len(sub) < min_bars:
            return None

        return sub

    except (KeyError, IndexError, AttributeError) as e:
        logger.debug("Ticker %s nicht aus Batch extrahierbar: %s", ticker, e)
        return None


def batch_download_ohlcv(
    tickers: list[str],
    period: Optional[str] = "1y",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    chunk_size: int = STANDARD_CHUNK_SIZE,
    min_bars: int = 0,
    pause_sekunden: float = 0.0,
) -> dict[str, pd.DataFrame]:
    """Lädt OHLCV-Daten für viele Ticker in Chunks.

    Args:
        tickers: Symbole
        period: yfinance-Periodenstring (ignoriert, wenn start gesetzt ist)
        start/end: Explizites Zeitfenster (hat Vorrang vor period)
        chunk_size: Ticker je Netzwerk-Call
        min_bars: Ticker mit weniger Bars werden verworfen
        pause_sekunden: Wartezeit zwischen Chunks (Rate-Limit-Schonung)

    Returns:
        Dict {ticker: DataFrame}. Ticker ohne verwertbare Daten fehlen.
    """
    if not tickers:
        return {}

    ergebnis: dict[str, pd.DataFrame] = {}
    eindeutige = list(dict.fromkeys(t for t in tickers if t))
    chunks = [eindeutige[i:i + chunk_size]
              for i in range(0, len(eindeutige), chunk_size)]

    for index, chunk in enumerate(chunks):
        try:
            kwargs: dict = {
                "auto_adjust": True,
                "progress": False,
                "threads": True,
            }
            if start is not None:
                kwargs["start"] = start
                if end is not None:
                    kwargs["end"] = end
            else:
                kwargs["period"] = period

            daten = yf.download(chunk, **kwargs)

            if daten is None or daten.empty:
                logger.warning("Batch-Download: Chunk %d/%d lieferte keine Daten.",
                               index + 1, len(chunks))
                continue

            for ticker in chunk:
                hist = einzelnen_ticker_extrahieren(daten, ticker, min_bars=min_bars)
                if hist is not None:
                    ergebnis[ticker] = hist

        except Exception as e:
            # Ein fehlgeschlagener Chunk darf den Gesamtlauf nicht abbrechen —
            # die betroffenen Ticker fehlen dann schlicht im Ergebnis.
            logger.warning("Batch-Download: Chunk %d/%d fehlgeschlagen: %s",
                           index + 1, len(chunks), e, exc_info=True)

        if pause_sekunden and index < len(chunks) - 1:
            time.sleep(pause_sekunden)

    logger.info("Batch-Download: %d/%d Ticker mit Daten geliefert.",
                len(ergebnis), len(eindeutige))
    return ergebnis


def kurs_am_stichtag(hist: pd.DataFrame, stichtag: datetime) -> Optional[float]:
    """Liefert den Schlusskurs am Stichtag — oder am nächsten Handelstag danach.

    Zwingend nötig für die Outcome-Auswertung: ein fälliges Outcome muss mit
    dem Kurs zu SEINEM Fälligkeitsdatum bewertet werden, nicht mit dem
    aktuellen Kurs. Ein vor Wochen fällig gewordener 30-Tage-Horizont würde
    sonst faktisch die Rendite über den gesamten Zeitraum bis heute messen und
    wäre als "30-Tage-Ergebnis" schlicht falsch.

    Returns:
        Schlusskurs, oder None wenn der Stichtag nach dem letzten Bar liegt.
    """
    if hist is None or hist.empty:
        return None

    try:
        index = hist.index
        # yfinance liefert je nach Markt tz-aware Indizes — Stichtag angleichen.
        ziel = pd.Timestamp(stichtag)
        if getattr(index, "tz", None) is not None:
            ziel = ziel.tz_localize(index.tz) if ziel.tzinfo is None else ziel.tz_convert(index.tz)
        elif ziel.tzinfo is not None:
            ziel = ziel.tz_localize(None)

        position = index.searchsorted(ziel)
        if position >= len(index):
            return None  # Stichtag liegt in der Zukunft → noch nicht bewertbar

        return float(hist["Close"].iloc[position])

    except (TypeError, ValueError, IndexError) as e:
        logger.debug("kurs_am_stichtag fehlgeschlagen (%s): %s", stichtag, e)
        return None
