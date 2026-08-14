"""
snapshot_engine/auswertung/basis.py — Gemeinsame Grundlagen der Auswertung.

Enthält die statistischen Bausteine, die alle Auswertungsmodule teilen:
Mindest-Stichprobengröße, effektive Stichprobengröße bei überlappenden
Beobachtungen und risikoadjustierte Kennzahlen.
"""

import statistics
from typing import Optional, Sequence

from snapshot_engine.models import MIN_BEWEGUNG_PCT

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
# Vergleichsbasis
# ---------------------------------------------------------------------------

def anteil_steigend(returns: Sequence[Optional[float]]) -> Optional[float]:
    """Anteil steigender Fenster unter den BEWERTBAREN Beobachtungen.

    Bewertbar heißt: Bewegung mindestens MIN_BEWEGUNG_PCT — dieselbe Schwelle,
    die `erfolg_bewerten` anlegt. Über alle Zeilen gerechnet wäre die Basisrate
    gegenüber der Trefferquote systematisch verschoben.
    """
    bewegt = [r for r in returns if r is not None and abs(r) >= MIN_BEWEGUNG_PCT]
    if not bewegt:
        return None
    return sum(1 for r in bewegt if r > 0) / len(bewegt) * 100


def basis_trefferquote(anteil: Optional[float],
                       richtungen: Sequence[Optional[int]]) -> Optional[float]:
    """Was dieselbe Richtungsmischung OHNE jede Prognosefähigkeit getroffen hätte.

    Eine Trefferquote ohne diesen Bezugspunkt ist bedeutungslos: steigen Aktien
    in 55 % aller Fenster ohnehin, ist ein Kaufsignal mit 55 % Trefferquote
    genau null wert. Gruppen aus KAUF und VERKAUF werden nach ihrem
    tatsächlichen Mischungsverhältnis gewichtet.
    """
    gerichtet = [ri for ri in richtungen if ri is not None]
    if anteil is None or not gerichtet:
        return None
    n_long = sum(1 for ri in gerichtet if ri > 0)
    n_short = len(gerichtet) - n_long
    return (n_long * anteil + n_short * (100.0 - anteil)) / len(gerichtet)


def mit_basis(kennzahlen: dict, anteil: Optional[float],
              richtungen: Sequence[Optional[int]]) -> dict:
    """Ergänzt eine Kennzahlenzeile um Basisrate und Vorsprung (in Prozentpunkten)."""
    basis = basis_trefferquote(anteil, richtungen)
    quote = kennzahlen.get("trefferquote")
    kennzahlen["basis_trefferquote"] = round(basis, 1) if basis is not None else None
    kennzahlen["vorsprung_pp"] = (round(quote - basis, 1)
                                  if basis is not None and quote is not None else None)
    return kennzahlen


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------

def kennzahlen_aus_returns(returns: Sequence[float],
                           treffer: Optional[Sequence[Optional[bool]]] = None,
                           horizont_tage: int = 0,
                           minimum: int = MIN_STICHPROBE,
                           richtungen: Optional[Sequence[Optional[int]]] = None) -> dict:
    """Berechnet Trefferquote UND risikoadjustierte Kennzahlen.

    Eine reine Trefferquote ist irreführend: 90 % Treffer mit winzigen Gewinnen
    und einem katastrophalen Verlust ist schlechter als 45 % Treffer mit gutem
    Chance-Risiko-Verhältnis. Deshalb werden Erwartungswert und Profitfaktor
    immer mit ausgewiesen.

    Args:
        returns: Kursrenditen in Prozent
        treffer: Optional war_erfolgreich je Beobachtung (None = nicht bewertbar)
        horizont_tage: Für die effektive Stichprobengröße
        minimum: Mindest-Stichprobe (geprüft gegen die EFFEKTIVE Stichprobe)
        richtungen: Optional +1 (long) / -1 (short) / None je Beobachtung.
            Ohne diese Angabe sind die Ertragskennzahlen richtungsblind — ein
            erfolgreiches VERKAUF-Signal mit -8 % würde als Verlust zählen.

    Returns:
        Dict mit status, n, n_effektiv und (falls ausreichend) den Kennzahlen.
    """
    treffer_gegeben = treffer is not None
    if treffer is None:
        treffer = [None] * len(returns)
    if richtungen is None:
        richtungen = [None] * len(returns)

    # Gemeinsam filtern, damit Rendite, Treffer und Richtung ausgerichtet bleiben.
    beobachtungen = [(r, t, ri) for r, t, ri in zip(returns, treffer, richtungen)
                     if r is not None]
    werte = [r for r, _, _ in beobachtungen]
    n = len(werte)
    n_effektiv = effektive_stichprobe(n, horizont_tage) if horizont_tage else n

    # Gegen die EFFEKTIVE Stichprobe prüfen, nicht gegen die rohe Zeilenzahl:
    # 20 Beobachtungen auf 90 Tage sind ~2 unabhängige und tragen keine Quote.
    ausreichend = stichprobe_ausreichend(n_effektiv, minimum)

    ergebnis: dict = {
        "status": STATUS_OK if ausreichend else STATUS_ZU_WENIG_DATEN,
        "n": n,
        "n_effektiv": n_effektiv,
        "min_erforderlich": minimum,
    }

    if not ausreichend:
        return ergebnis

    # Ertrag aus Sicht des Signals: bei VERKAUF ist ein fallender Kurs Gewinn.
    # Beobachtungen ohne Richtung (NEUTRAL) sind keinem Ertrag zuzuordnen.
    ertraege = [r * ri for r, _, ri in beobachtungen if ri is not None]
    gerichtet = bool(ertraege)
    if not gerichtet:
        ertraege = werte

    gewinne = [r for r in ertraege if r > 0]
    verluste = [r for r in ertraege if r < 0]

    avg_gewinn = statistics.fmean(gewinne) if gewinne else 0.0
    avg_verlust = abs(statistics.fmean(verluste)) if verluste else 0.0

    # Trefferquote: bevorzugt die explizite Bewertung (berücksichtigt
    # Richtungssignal und Mindestbewegung), sonst ersatzweise Ertrag > 0.
    if treffer_gegeben:
        bewertbar = [t for _, t, _ in beobachtungen if t is not None]
        trefferquote = (sum(1 for t in bewertbar if t) / len(bewertbar) * 100
                        if bewertbar else None)
        n_bewertbar = len(bewertbar)
    else:
        trefferquote = len(gewinne) / len(ertraege) * 100
        n_bewertbar = len(ertraege)

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
        # avg_return = reine Kursbewegung, avg_ertrag = Sicht des Signals.
        # Bei richtungslosen Gruppen (NEUTRAL) sind beide identisch.
        "gerichtet": gerichtet,
        "avg_ertrag": round(statistics.fmean(ertraege), 2),
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
