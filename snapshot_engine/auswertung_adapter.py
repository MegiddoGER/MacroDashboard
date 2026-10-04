"""
snapshot_engine/auswertung_adapter.py — Kompatibilitätsschicht.

Stellt die Funktionssignaturen der abgelösten services/signal_history.py
bereit, bedient sie aber aus der Signal-Qualitäts-Engine. Die Aufrufer
(services/cache_core.py, services/technical.py) arbeiten ohne DB-Session —
diese Schicht öffnet und schließt sie daher selbst.

Die Kennzahlen stammen jetzt aus einer einzigen Quelle: doppelte, voneinander
abweichende Trefferquoten an verschiedenen Stellen des Dashboards gibt es
damit nicht mehr.
"""

import logging

from database import get_session
from snapshot_engine.auswertung import kelly_parameter
from snapshot_engine.auswertung.risk_adjusted import trefferquote

logger = logging.getLogger(__name__)


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
