"""
snapshot_engine/auswertung/basis.py — Gemeinsame Grundlagen der Auswertung.

Enthält die statistischen Bausteine, die alle Auswertungsmodule teilen:
Mindest-Stichprobengröße, effektive Stichprobengröße bei überlappenden
Beobachtungen und risikoadjustierte Kennzahlen.
"""

import statistics
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# Stichproben-Gating
# ---------------------------------------------------------------------------

# Unterhalb dieser Anzahl wird KEINE Trefferquote ausgewiesen. Bei 15-20
# Indikatoren, 5 Kategorien, mehreren Horizonten und hunderten Tickern findet
# man sonst zwangsläufig "signifikante" Muster, die reiner Zufall sind.
MIN_STICHPROBE = 20

STATUS_OK = "ok"
STATUS_ZU_WENIG_DATEN = "zu_wenig_daten"


def stichprobe_ausreichend(n: int, minimum: int = MIN_STICHPROBE) -> bool:
    return n >= minimum


# ---------------------------------------------------------------------------
# Effektive Stichprobengröße
# ---------------------------------------------------------------------------

# Neubewertungs-Kadenz in Handelstagen (siehe backfill_service.KADENZ_BARS).
KADENZ_HANDELSTAGE = 7
HANDELSTAGE_JE_KALENDERTAG = 5 / 7


def effektive_stichprobe(n: int, horizont_tage: int) -> int:
    """Schätzt die Anzahl *unabhängiger* Beobachtungen.

    Snapshots entstehen alle ~7 Handelstage, die Auswertungshorizonte sind
    aber bis zu 90 Kalendertage lang. Aufeinanderfolgende Beobachtungen messen
    daher weitgehend denselben Kursverlauf — 300 Zeilen mit 90-Tage-Horizont
    sind statistisch eher ~23 unabhängige Beobachtungen.

    Diese Zahl auszuweisen verhindert, dass eine Trefferquote solider wirkt,
    als die Datenlage hergibt.
    """
    if n <= 0:
        return 0
    horizont_handelstage = max(1.0, horizont_tage * HANDELSTAGE_JE_KALENDERTAG)
    ueberlappung = max(1.0, horizont_handelstage / KADENZ_HANDELSTAGE)
    return max(1, int(n / ueberlappung))


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------

def kennzahlen_aus_returns(returns: Sequence[float],
                           treffer: Optional[Sequence[Optional[bool]]] = None,
                           horizont_tage: int = 0,
                           minimum: int = MIN_STICHPROBE) -> dict:
    """Berechnet Trefferquote UND risikoadjustierte Kennzahlen.

    Eine reine Trefferquote ist irreführend: 90 % Treffer mit winzigen Gewinnen
    und einem katastrophalen Verlust ist schlechter als 45 % Treffer mit gutem
    Chance-Risiko-Verhältnis. Deshalb werden Erwartungswert und Profitfaktor
    immer mit ausgewiesen.

    Args:
        returns: Renditen in Prozent
        treffer: Optional war_erfolgreich je Beobachtung (None = nicht bewertbar)
        horizont_tage: Für die effektive Stichprobengröße
        minimum: Mindest-Stichprobe

    Returns:
        Dict mit status, n, n_effektiv und (falls ausreichend) den Kennzahlen.
    """
    werte = [r for r in returns if r is not None]
    n = len(werte)

    ergebnis: dict = {
        "status": STATUS_OK if stichprobe_ausreichend(n, minimum) else STATUS_ZU_WENIG_DATEN,
        "n": n,
        "n_effektiv": effektive_stichprobe(n, horizont_tage) if horizont_tage else n,
        "min_erforderlich": minimum,
    }

    if not stichprobe_ausreichend(n, minimum):
        return ergebnis

    gewinne = [r for r in werte if r > 0]
    verluste = [r for r in werte if r < 0]

    avg_gewinn = statistics.fmean(gewinne) if gewinne else 0.0
    avg_verlust = abs(statistics.fmean(verluste)) if verluste else 0.0

    # Trefferquote: bevorzugt die explizite Bewertung (berücksichtigt
    # Richtungssignal und Mindestbewegung), sonst ersatzweise return > 0.
    if treffer is not None:
        bewertbar = [t for t in treffer if t is not None]
        trefferquote = (sum(1 for t in bewertbar if t) / len(bewertbar) * 100
                        if bewertbar else None)
        n_bewertbar = len(bewertbar)
    else:
        trefferquote = len(gewinne) / n * 100
        n_bewertbar = n

    # Erwartungswert je Beobachtung (in Prozentpunkten)
    if trefferquote is not None:
        p = trefferquote / 100
        erwartungswert = p * avg_gewinn - (1 - p) * avg_verlust
    else:
        erwartungswert = None

    summe_gewinne = sum(gewinne)
    summe_verluste = abs(sum(verluste))

    ergebnis.update({
        "trefferquote": round(trefferquote, 1) if trefferquote is not None else None,
        "n_bewertbar": n_bewertbar,
        "avg_return": round(statistics.fmean(werte), 2),
        "median_return": round(statistics.median(werte), 2),
        "stdev_return": round(statistics.stdev(werte), 2) if n > 1 else 0.0,
        "avg_gewinn": round(avg_gewinn, 2),
        "avg_verlust": round(avg_verlust, 2),
        "erwartungswert": round(erwartungswert, 2) if erwartungswert is not None else None,
        "profitfaktor": (round(summe_gewinne / summe_verluste, 2)
                         if summe_verluste > 0 else None),
        "bester": round(max(werte), 2),
        "schlechtester": round(min(werte), 2),
    })

    return ergebnis
