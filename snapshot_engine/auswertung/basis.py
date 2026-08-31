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
    """Ergänzt eine Kennzahlenzeile um Basisrate, Vorsprung und dessen Belastbarkeit."""
    basis = basis_trefferquote(anteil, richtungen)
    quote = kennzahlen.get("trefferquote")
    kennzahlen["basis_trefferquote"] = round(basis, 1) if basis is not None else None
    vorsprung = (round(quote - basis, 1)
                 if basis is not None and quote is not None else None)
    kennzahlen["vorsprung_pp"] = vorsprung

    # Ohne Fehlerbalken ist ein Vorsprung nicht bewertbar: +2 pp auf 200
    # effektiven Beobachtungen ist Rauschen, dieselben +2 pp auf 15.000 nicht.
    kennzahlen["vorsprung_fehler_pp"] = fehlerspanne_pp(
        quote, kennzahlen.get("n_effektiv"))
    kennzahlen["vorsprung_signifikant"] = vorsprung_signifikant(
        vorsprung, quote, kennzahlen.get("n_effektiv"))
    return kennzahlen


# ---------------------------------------------------------------------------
# Überrendite gegen den Markt (P1-04)
# ---------------------------------------------------------------------------

# Mindest-Vorsprung, ab dem eine Überrendite als Aussage gilt. Dieselbe
# Schwelle wie MIN_BEWEGUNG_PCT bei der absoluten Bewertung, nur auf die
# Differenz angewandt statt auf die Kursbewegung.
MIN_VORSPRUNG_PP = MIN_BEWEGUNG_PCT

# Die Nullhypothese der Marktquote ist 50, nicht `anteil_steigend`. Genau das
# ist der Sinn von P1-04: der Vergleichsindex hat die Marktbewegung bereits aus
# jeder einzelnen Beobachtung herausgerechnet, deshalb braucht es keine über
# den Gesamtbestand gemittelte Basisrate mehr. Wer ohne Prognosefähigkeit
# rät, liegt gegen den Markt in der Hälfte der Fälle vorn.
MARKT_NULLHYPOTHESE = 50.0


def mit_ueberrendite(kennzahlen: dict,
                     ueberrenditen: Sequence[Optional[float]],
                     richtungen: Sequence[Optional[int]],
                     horizont_tage: int = 0) -> dict:
    """Ergänzt eine Kennzahlenzeile um die Bewertung gegen den Markt.

    Tritt NEBEN die absolute Trefferquote, ersetzt sie nicht. Beide werden
    gebraucht: die absolute Quote bleibt mit allen bisher belegten Zahlen
    vergleichbar, und wo die beiden auseinanderlaufen, saß Marktphase statt
    Signalqualität.

    Gerechnet wird auf der Überrendite aus Sicht des Signals -- bei VERKAUF
    ist ein Rückstand des Titels gegenüber dem Index ein Treffer. Ungerichtete
    Beobachtungen (NEUTRAL) tragen nichts bei.

    `ueberrendite_abdeckung_pct` ist Teil des Ergebnisses und keine Beigabe:
    solange der Bestandsnachtrag läuft, hat nur ein Teil der Zeilen einen
    Vergleichswert, und eine Marktquote über 200 von 256.705 Zeilen darf
    nicht wie eine Aussage über den Bestand aussehen.

    Bezugsgröße der Abdeckung sind die GERICHTETEN Beobachtungen, nicht alle:
    NEUTRAL ist gegen den Markt ohnehin nicht bewertbar, und gegen `n`
    gerechnet wäre ein fehlender Benchmark von einem fehlenden
    Richtungssignal nicht mehr zu unterscheiden.

    Args:
        kennzahlen: Zeile aus `kennzahlen_aus_returns`, wird ergänzt.
        ueberrenditen: Titel minus Index in Prozentpunkten, None wo kein
            Vergleichswert vorliegt.
        richtungen: +1 (long) / -1 (short) / None je Beobachtung.
        horizont_tage: Für die effektive Stichprobe.
    """
    gerichtet = [u * ri for u, ri in zip(ueberrenditen, richtungen)
                 if u is not None and ri is not None]

    n_gerichtet = sum(1 for ri in richtungen if ri is not None)
    kennzahlen["ueberrendite_n"] = len(gerichtet)
    kennzahlen["ueberrendite_abdeckung_pct"] = (
        round(len(gerichtet) / n_gerichtet * 100, 1) if n_gerichtet else None)

    # Alles Weitere braucht eine Stichprobe. Fehlt sie, bleiben die Felder
    # None -- sichtbar leer ist besser als eine Zahl ohne Deckung.
    kennzahlen.setdefault("ueberrendite_mittel_pp", None)
    kennzahlen.setdefault("markt_trefferquote", None)
    kennzahlen.setdefault("markt_vorsprung_pp", None)
    kennzahlen.setdefault("markt_fehler_pp", None)
    kennzahlen.setdefault("markt_signifikant", None)

    n_effektiv = (effektive_stichprobe(len(gerichtet), horizont_tage)
                  if horizont_tage else len(gerichtet))
    kennzahlen["ueberrendite_n_effektiv"] = n_effektiv
    kennzahlen["ueberrendite_status"] = (
        STATUS_OK if stichprobe_ausreichend(n_effektiv) else STATUS_ZU_WENIG_DATEN)
    if kennzahlen["ueberrendite_status"] != STATUS_OK:
        return kennzahlen

    # Mittelwert über ALLE gerichteten Beobachtungen, auch die knappen: das
    # ist der Ertrag gegenüber dem Markt, und ein Vorsprung von 0,1 pp ist
    # dafür ein echter Beitrag, nur eben ein kleiner.
    kennzahlen["ueberrendite_mittel_pp"] = round(statistics.fmean(gerichtet), 2)

    # Die Quote dagegen zählt nur, was über dem Rauschen liegt -- dieselbe
    # Trennung wie zwischen avg_return und trefferquote.
    bewertbar = [g for g in gerichtet if abs(g) >= MIN_VORSPRUNG_PP]
    if not bewertbar:
        return kennzahlen

    quote = sum(1 for g in bewertbar if g > 0) / len(bewertbar) * 100
    kennzahlen["markt_trefferquote"] = round(quote, 1)
    vorsprung = quote - MARKT_NULLHYPOTHESE
    kennzahlen["markt_vorsprung_pp"] = round(vorsprung, 1)
    kennzahlen["markt_fehler_pp"] = fehlerspanne_pp(quote, n_effektiv)
    kennzahlen["markt_signifikant"] = vorsprung_signifikant(
        vorsprung, quote, n_effektiv)
    return kennzahlen


# ---------------------------------------------------------------------------
# Belastbarkeit einer Trefferquote
# ---------------------------------------------------------------------------

# 1,96 Standardfehler ≈ 95-%-Konfidenzintervall.
Z_95 = 1.96


def fehlerspanne_pp(trefferquote: Optional[float],
                    n_effektiv: Optional[int]) -> Optional[float]:
    """Halbe Breite des 95-%-Konfidenzintervalls einer Trefferquote, in Prozentpunkten.

    Gerechnet wird über die EFFEKTIVE Stichprobe, nicht über die Zeilenzahl:
    überlappende Beobachtungen messen weitgehend denselben Kursverlauf und
    dürfen die Genauigkeit nicht vortäuschen.

    Die Basisrate stützt sich auf zehntausende Beobachtungen; ihr eigener
    Fehler ist dagegen vernachlässigbar, weshalb hier nur der Fehler der
    verglichenen Gruppe eingeht.
    """
    if trefferquote is None or not n_effektiv or n_effektiv <= 0:
        return None
    p = max(0.0, min(1.0, trefferquote / 100.0))
    standardfehler = (p * (1.0 - p) / n_effektiv) ** 0.5
    return round(Z_95 * standardfehler * 100.0, 1)


def vorsprung_signifikant(vorsprung_pp: Optional[float],
                          trefferquote: Optional[float],
                          n_effektiv: Optional[int]) -> Optional[bool]:
    """Übersteigt der Vorsprung gegenüber der Basisrate die Zufallsschwankung?

    None, wenn es nichts zu beurteilen gibt (fehlende Werte oder Stichprobe).
    """
    spanne = fehlerspanne_pp(trefferquote, n_effektiv)
    if vorsprung_pp is None or spanne is None:
        return None
    return abs(vorsprung_pp) > spanne


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
