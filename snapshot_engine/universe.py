"""
snapshot_engine/universe.py — Ermittlung des zu trackenden Ticker-Universums.

Basis ist das Screener-Universum (S&P 500 + DAX/MDAX, ~650–750 liquide,
sektor-getaggte Werte) — also genau die Titel, auf denen der Nutzer im
Dashboard tatsächlich nach Gelegenheiten sucht.

Bewusst NICHT data/stock_listings.csv: das ist ein ungefiltertes Verzeichnis
aller ~16.700 gelisteten Symbole (inkl. OTC-Pennystocks, ETFs, Optionsscheine)
und dient ausschließlich der Ticker-Suche in routers/directory.py.

Ergänzt wird das Universum um manuelle Overrides aus SnapshotKonfiguration
(EINSCHLIESSEN = zusätzlich tracken, AUSSCHLIESSEN = überspringen).
"""

import logging

from sqlalchemy.orm import Session

from snapshot_engine.models import KonfigModus, SnapshotKonfiguration

logger = logging.getLogger(__name__)


def screener_universum() -> list[str]:
    """Lädt das Basis-Universum (S&P 500 + DAX/MDAX) aus dem Screener.

    Fällt bei Netzwerkproblemen auf die jeweils verfügbare Teilmenge zurück —
    ein fehlender Wikipedia-Abruf darf den Lauf nicht komplett verhindern.
    """
    from services.screener import get_dax_mdax_tickers, get_sp500_tickers

    tickers: list[str] = []

    sp500 = get_sp500_tickers()
    if sp500 is not None and not sp500.empty:
        tickers.extend(sp500["Symbol"].dropna().astype(str).tolist())
    else:
        logger.warning("Universum: S&P-500-Liste nicht verfügbar.")

    xetra = get_dax_mdax_tickers()
    if xetra is not None and not xetra.empty:
        tickers.extend(xetra["Symbol"].dropna().astype(str).tolist())
    else:
        logger.warning("Universum: DAX/MDAX-Liste nicht verfügbar.")

    return [t.strip().upper() for t in tickers if t and t.strip()]


def aktives_universum(db: Session) -> list[str]:
    """Gibt das effektiv zu trackende Universum zurück.

    Screener-Universum + EINSCHLIESSEN-Overrides − AUSSCHLIESSEN-Overrides.
    """
    tickers = list(dict.fromkeys(screener_universum()))

    try:
        overrides = db.query(SnapshotKonfiguration).filter(
            SnapshotKonfiguration.aktiv.is_(True)).all()
    except Exception as e:
        logger.error("Universum: Overrides nicht ladbar: %s", e, exc_info=True)
        return tickers

    zusaetzlich = {o.ticker.strip().upper() for o in overrides
                   if o.modus == KonfigModus.EINSCHLIESSEN and o.ticker}
    ausgeschlossen = {o.ticker.strip().upper() for o in overrides
                      if o.modus == KonfigModus.AUSSCHLIESSEN and o.ticker}

    vorhandene = set(tickers)
    tickers.extend(sorted(t for t in zusaetzlich if t not in vorhandene))

    ergebnis = [t for t in tickers if t not in ausgeschlossen]

    logger.info("Universum: %d Ticker (%d Screener, +%d manuell, -%d ausgeschlossen).",
                len(ergebnis), len(vorhandene), len(zusaetzlich - vorhandene),
                len(ausgeschlossen & set(tickers)))
    return ergebnis
