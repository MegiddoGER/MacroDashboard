"""
services/stetige_indikatoren.py — Dieselben Konzepte, ohne die Quantisierung.

Die sechzehn Indikatorrichtungen der Engine liegen im Bestand als **genau zwei
Werte** vor: +1 oder −1. Gemessen an 274.839 Zeilen trägt „Trend (SMA 200)"
bei 62 Prozent +1 und bei 38 Prozent −1, und mehr steht dort nicht. Ein Kurs
ein halbes Prozent über der Linie und einer fünfundvierzig Prozent darüber
sind derselbe Eingang. Es gibt keine Stärke, keinen Neutralbereich, und im
Feld `wert` steht bei den Trendindikatoren nicht der Abstand, sondern der
Kurs — die Größe selbst wurde nie gespeichert.

Das ist der Grund für dieses Modul. Ein Flag, das bei 62 Prozent aller
Beobachtungen gesetzt ist, ist kein Flag, sondern eine Zustandsbeschreibung;
was in der Praxis „Kaufsignal" heißt, feuert selten und mit Stärke. Die
Nullbefunde aus §2b sagen also streng genommen nur, dass **diese Kodierung**
nichts trägt — nicht, dass Trend oder Chartlage nichts tragen.

**Was hier gerechnet wird und was das kostet.** Die Reihen stammen aus den
Snapshot-Kursen, nicht aus neuen Abrufen — dieselbe Begründung wie in
`auswertung/momentum.py`: alle HISTORISCH-Snapshots eines Tickers stammen aus
einer einzigen abgespielten Kursreihe und damit aus derselben Anpassungsbasis,
weshalb ein Verhältnis zwischen zwei von ihnen split-sicher ist.

Der Preis ist die Auflösung. Die Kadenz beträgt im Median **acht Tage**, ein
Fenster von 280 Kalendertagen (rund 200 Handelstage) hat damit etwa
**35 Stützstellen** statt 200. Das ist eine belastbare Näherung eines
gleitenden Mittels, aber keine exakte SMA 200. Für die Frage, um die es geht —
trägt die *Stärke* etwas, das das Vorzeichen wegwirft — reicht sie; ein
positiver Befund würde eine exakte Nachrechnung rechtfertigen, ein negativer
bleibt entsprechend schwächer als einer auf exakten Reihen.

**Kein Look-ahead.** Das Fenster endet am Snapshot-Zeitpunkt und enthält nur
Kurse bis dorthin. Der Kurs des Stichtags selbst gehört dazu — er ist zu
diesem Zeitpunkt bekannt, und ein gleitendes Mittel schließt ihn per
Definition ein.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Sequence

logger = logging.getLogger(__name__)


# Fensterlängen in KALENDERTAGEN, nicht in Handelstagen: die Snapshots liegen
# auf Kalenderabständen, und eine Umrechnung in Handelstage wäre bei acht Tagen
# Kadenz eine Scheingenauigkeit.
FENSTER_LANG_TAGE = 280      # ≈ 200 Handelstage — das Gegenstück zur SMA 200
FENSTER_KURZ_TAGE = 70       # ≈ 50 Handelstage — das Gegenstück zur SMA 50

# Mindestbesetzung eines Fensters. Bei acht Tagen Kadenz erwartet das lange
# Fenster rund 35 Stützstellen; unter 20 ist der Mittelwert von Lücken in der
# Reihe getrieben statt vom Kursverlauf.
MIN_STUETZSTELLEN_LANG = 20
MIN_STUETZSTELLEN_KURZ = 6


def gleitender_mittelwert(reihe: Optional[Sequence[tuple]], zeitpunkt: datetime,
                          fenster_tage: int, minimum: int) -> Optional[float]:
    """Mittlerer Kurs im Fenster (zeitpunkt − fenster_tage, zeitpunkt].

    Args:
        reihe: nach Datum sortierte (Zeitpunkt, Kurs)-Paare.

    Returns:
        None, wenn das Fenster zu dünn besetzt ist. Das ist kein Randfall,
        sondern der Normalfall am Anfang jeder Reihe — die ersten Monate eines
        Tickers tragen kein langes Fenster.
    """
    if not reihe or zeitpunkt is None:
        return None

    untergrenze = zeitpunkt - timedelta(days=fenster_tage)
    kurse = []
    # Rückwärts, weil das Fenster am Ende der sortierten Reihe liegt.
    for datum, kurs in reversed(reihe):
        if datum > zeitpunkt:
            continue
        if datum <= untergrenze:
            break
        if kurs and kurs > 0:
            kurse.append(kurs)

    if len(kurse) < minimum:
        return None
    return sum(kurse) / len(kurse)


def _kurs_am(reihe: Optional[Sequence[tuple]], zeitpunkt: datetime) -> Optional[float]:
    """Letzter Kurs bis einschließlich zeitpunkt."""
    if not reihe:
        return None
    for datum, kurs in reversed(reihe):
        if datum <= zeitpunkt and kurs and kurs > 0:
            return kurs
    return None


def sma_abstand(reihe: Optional[Sequence[tuple]], zeitpunkt: datetime,
                fenster_tage: int = FENSTER_LANG_TAGE,
                minimum: int = MIN_STUETZSTELLEN_LANG) -> Optional[float]:
    """Abstand des Kurses zum langen Mittel, in Prozent.

    Die stetige Fassung von „Trend (SMA 200)". Die binäre Fassung der Engine
    ist exakt das Vorzeichen dieser Zahl — das macht den Vergleich zu einem
    echten Kontrollversuch: gleiche Zeilen, gleiches Konzept, einziger
    Unterschied ist die weggeworfene Stärke.
    """
    mittel = gleitender_mittelwert(reihe, zeitpunkt, fenster_tage, minimum)
    kurs = _kurs_am(reihe, zeitpunkt)
    if mittel is None or kurs is None or mittel <= 0:
        return None
    return (kurs / mittel - 1.0) * 100.0


def ma_spreizung(reihe: Optional[Sequence[tuple]], zeitpunkt: datetime,
                 kurz_tage: int = FENSTER_KURZ_TAGE,
                 lang_tage: int = FENSTER_LANG_TAGE,
                 minimum_kurz: int = MIN_STUETZSTELLEN_KURZ,
                 minimum_lang: int = MIN_STUETZSTELLEN_LANG) -> Optional[float]:
    """Abstand des kurzen zum langen Mittel, in Prozent.

    Die stetige Fassung des SMA-Cross-Gedankens. Bewusst 70 gegen 280 Tage und
    nicht 20 gegen 50 wie im Original: ein 28-Tage-Fenster hätte bei acht Tagen
    Kadenz drei bis vier Stützstellen und wäre kein Mittel mehr, sondern
    Rauschen mit Mittelwertzeichen.
    """
    kurz = gleitender_mittelwert(reihe, zeitpunkt, kurz_tage, minimum_kurz)
    lang = gleitender_mittelwert(reihe, zeitpunkt, lang_tage, minimum_lang)
    if kurz is None or lang is None or lang <= 0:
        return None
    return (kurz / lang - 1.0) * 100.0


def vorzeichen(wert: Optional[float]) -> Optional[int]:
    """+1 / −1 — die Kodierung der Engine, auf demselben Wert gerechnet.

    Genau null gilt als bullisch, wie in `services/scoring.py`: dort entsteht
    das Flag aus einem `>=`-Vergleich, und ein Kurs exakt auf der Linie
    bekommt +1. Der Fall ist praktisch nicht besetzt, aber die Kontrolle muss
    die Engine nachbilden und nicht verbessern.
    """
    if wert is None:
        return None
    return 1 if wert >= 0 else -1
