"""
snapshot_engine/auswertung_adapter.py — Kompatibilitätsschicht.

Stellt die Funktionssignaturen der abgelösten services/signal_history.py
bereit, bedient sie aber aus der Signal-Qualitäts-Engine. Die Aufrufer
(services/cache_core.py, routers/journal.py, services/technical.py) arbeiten
ohne DB-Session — diese Schicht öffnet und schließt sie daher selbst.

Die Kennzahlen stammen jetzt aus einer einzigen Quelle: doppelte, voneinander
abweichende Trefferquoten an verschiedenen Stellen des Dashboards gibt es
damit nicht mehr.
"""

import logging

from database import get_session
from snapshot_engine.auswertung import (
    kalibrierung_berechnen, kelly_parameter, signal_statistik,
)
from snapshot_engine.auswertung.basis import STATUS_OK
from snapshot_engine.auswertung.risk_adjusted import trefferquote

logger = logging.getLogger(__name__)

# Die abgelöste Implementierung wertete 1W/1M/3M aus; 30 Tage entspricht dem
# bisherigen Schwerpunkt (price_1m_later) und ist die übliche Swing-Haltedauer.
STANDARD_HORIZONT = 30


def get_signal_statistics() -> dict:
    """Kennzahlen für die Journal-Seite (Signatur wie zuvor)."""
    session = get_session()
    try:
        stats = signal_statistik(session, horizont=STANDARD_HORIZONT)
        return {
            "total_signals": stats.get("gesamt", 0),
            "evaluated": stats.get("ausgewertet", 0),
            "avg_confidence": stats.get("avg_confidence"),
            "best_ticker": stats.get("bester_ticker"),
            "worst_ticker": stats.get("schlechtester_ticker"),
            "top_signals": stats.get("top_signale", []),
            "flop_signals": stats.get("flop_signale", []),
        }
    except Exception as e:
        logger.error("get_signal_statistics fehlgeschlagen: %s", e, exc_info=True)
        return {"total_signals": 0, "evaluated": 0, "top_signals": [], "flop_signals": []}
    finally:
        session.close()


def calc_hit_rate(days: int = 90) -> dict:
    """Trefferquote (Signatur wie zuvor).

    `days` wird auf den nächstgelegenen verfügbaren Horizont abgebildet.
    """
    from snapshot_engine.models import HORIZONTE_TAGE

    horizont = min(HORIZONTE_TAGE, key=lambda h: abs(h - days))
    session = get_session()
    try:
        werte = trefferquote(session, horizont=horizont)
        return {
            "evaluated": werte.get("ausgewertet", 0),
            "overall_hit_rate": werte.get("trefferquote"),
            "horizon_days": horizont,
            "effective_n": werte.get("n_effektiv", 0),
        }
    except Exception as e:
        logger.error("calc_hit_rate fehlgeschlagen: %s", e, exc_info=True)
        return {"evaluated": 0, "overall_hit_rate": None, "horizon_days": horizont}
    finally:
        session.close()


def calc_calibration_chart() -> list[dict]:
    """Kalibrierungsdaten im bisherigen Format (bucket / hit_rate)."""
    session = get_session()
    try:
        zeilen = kalibrierung_berechnen(session, horizont=STANDARD_HORIZONT)
        return [
            {
                "bucket": z["bereich"],
                "hit_rate": z.get("trefferquote") if z.get("status") == STATUS_OK else None,
                "count": z.get("n", 0),
                "avg_return": z.get("avg_return"),
            }
            for z in zeilen
        ]
    except Exception as e:
        logger.error("calc_calibration_chart fehlgeschlagen: %s", e, exc_info=True)
        return []
    finally:
        session.close()


def kelly_kennzahlen() -> dict | None:
    """Trefferquote und Gewinn/Verlust-Verhältnis für die Positionsgrößen-Rechnung."""
    session = get_session()
    try:
        return kelly_parameter(session)
    except Exception as e:
        logger.error("kelly_kennzahlen fehlgeschlagen: %s", e, exc_info=True)
        return None
    finally:
        session.close()
