"""
snapshot_engine/auswertung — Auswertung der Signal-Qualität.

Alle Kennzahlen werden ausschließlich aus der Datenbank berechnet (keine
Kursabrufe). Öffentliche API:

    kennzahlen_berechnen()    — Kernkennzahlen je Horizont und Richtungssignal
    bestand_ermitteln()       — Datenbestand (LIVE vs. HISTORISCH, offen/fertig)
    indikator_leaderboard()   — Bewertung je Einzelindikator
    kategorie_leaderboard()   — Bewertung je Score-Kategorie
    kalibrierung_berechnen()  — Ergebnis je Confidence-Bereich
    kalibrierung_bewerten()   — Kurzfazit zur Aussagekraft der Confidence
    kelly_parameter()         — Trefferquote/CRV für die Positionsgrößen-Rechnung

Drei Grundsätze gelten überall:
  1. LIVE und HISTORISCH werden nie vermischt (unterschiedliche Datenbasis).
  2. Unterhalb der Mindest-Stichprobe wird keine Quote ausgewiesen.
  3. Neben der Trefferquote steht immer eine risikoadjustierte Kennzahl.
"""

from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, STATUS_OK, STATUS_ZU_WENIG_DATEN,
    effektive_stichprobe, kennzahlen_aus_returns,
)
from snapshot_engine.auswertung.kennzahlen import (
    bestand_ermitteln, kennzahlen_berechnen,
)
from snapshot_engine.auswertung.indikator_stats import (
    indikator_leaderboard, kategorie_leaderboard,
)
from snapshot_engine.auswertung.kalibrierung import (
    kalibrierung_berechnen, kalibrierung_bewerten,
)
from snapshot_engine.auswertung.risk_adjusted import (
    kelly_parameter, signal_statistik,
)

__all__ = [
    "MIN_STICHPROBE",
    "STATUS_OK",
    "STATUS_ZU_WENIG_DATEN",
    "bestand_ermitteln",
    "effektive_stichprobe",
    "indikator_leaderboard",
    "kalibrierung_berechnen",
    "kalibrierung_bewerten",
    "kategorie_leaderboard",
    "kelly_parameter",
    "kennzahlen_aus_returns",
    "kennzahlen_berechnen",
    "signal_statistik",
]
