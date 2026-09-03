"""
snapshot_engine/auswertung/handbuch.py — Wie ist jedes Instrument zu lesen?

Die Frage, um die es in diesem Projekt eigentlich geht, und die §2b nicht
beantworten konnte. Dort stand je Indikator eine Zeile „bullisch" und eine
„bearisch", und alle sechzehn lauteten auf Rauschen — gemessen wurde aber ein
Flag mit **zwei** Werten. Ein Kurs ein halbes Prozent über der SMA 200 und
einer fünfundvierzig Prozent darüber waren derselbe Eingang.

§2h hat auf identischen Zeilen gemessen, was diese Rundung kostet: die stetige
Fassung derselben Größe trug 2,0 bzw. 2,9 pp Spread mit monotonem Verlauf, die
binäre nichts. Prüfen liessen sich damals nur **zwei** der zehn Instrumente —
für die übrigen war im Bestand keine Zahl vorhanden, nur ein Vorzeichen.

Seit dem Neuaufzeichnen trägt jede Indikatorzeile ihre gemessene Größe in
`wert_numeric`. Dieses Modul liest sie und beantwortet je Instrument drei
Dinge: **trägt es, unter welchen Bedingungen, und ab welchem Ausmass.** Kein
Ja/Nein — eine Lesart.

**Querschnittlich gerangt, nicht absolut.** Ränge werden je Kalenderwoche und
Handelsplatz gebildet, wie in `kodierung.py` und `momentum.py`. Ein RSI von 60
bedeutet in einer Hausse etwas anderes als in einem Bärenmarkt; eine absolute
Schwelle über zehn Jahre mischt den Marktzustand in die Aussage. Die Rangform
hält die Zahlen zugleich mit dem Befund aus §2h vergleichbar.

**Die binäre Gegenprobe ist `vorzeichen(wert)`, nicht die alte Aufzeichnung.**
Das ist eine bewusste Entscheidung. Die alte Aufzeichnung hätte für RSI,
Stochastic und Bollinger im Neutralbereich **gar keine Zeile** angelegt — ein
Vergleich mit ihr liefe über verschiedene Grundgesamtheiten und wäre kein
Kontrollversuch mehr. Verglichen wird deshalb „dieselben Zeilen, nur das
Vorzeichen behalten", genau wie in §2h. Wie viele Zeilen die alte Kodierung
überhaupt geführt hätte, weist `abdeckung_alt` je Instrument aus — das ist die
zweite, unabhängige Aussage.

**Mehrfachtests.** Korrigiert wird über ALLE Zellen eines Aufrufs, nicht je
Instrument. Wer zehn Instrumente durchsucht und anschliessend das beste
zitiert, hat zehnmal getestet; eine Korrektur je Instrument wäre zehnmal zum
Preis von einem. `z_korrigiert` steht im Ergebnis, damit die Strenge sichtbar
bleibt. Ein einzelnes Instrument gezielt abzufragen ist ein anderer, schwächer
korrigierter Test — nach einem Durchlauf über alle darf er nicht mehr als
Bestätigung gelten.
"""

import logging
from collections import defaultdict
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from services.cross_sectional_momentum import raenge_je_gruppe
from services.stetige_indikatoren import vorzeichen
from snapshot_engine.benchmark import benchmark_fuer, ueberrendite
from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotIndikator,
    AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, z_korrigiert, zelle_gegen_markt,
)
from snapshot_engine.auswertung.holdout import TRAIN, grenze_lesen, split_filter

logger = logging.getLogger(__name__)


QUANTILE = 5
MIN_QUERSCHNITT = 20
HORIZONTE = (7, 30, 90)

# Instrumente, deren Rohgröße im Mean-Reversion-Sinn zu lesen ist: ein hoher
# Wert ist das VERKAUFS-Signal, nicht das Kaufsignal. Ohne diesen Hinweis
# liest man Q5 als „stark" und übersieht, dass die Engine dort bearisch
# stimmt — der häufigste Fehler beim Lesen dieser Tabelle.
GEGENLAEUFIG = frozenset({"RSI (14)", "Stochastic (14)", "Bollinger Bänder"})


def quintil(rang: Optional[float]) -> Optional[int]:
    """Quintil 1–5 zu einem Perzentilrang; 5 ist der höchste Rohwert."""
    if rang is None:
        return None
    return min(QUANTILE, int(rang // (100.0 / QUANTILE)) + 1)


# ---------------------------------------------------------------------------
# Bestand
# ---------------------------------------------------------------------------

def instrumente(db: Session, datenmodus: str = "HISTORISCH") -> list[str]:
    """Welche Instrumente tragen überhaupt Rohwerte?

    Absichtlich aus dem Bestand gelesen und nicht aus `_SIGNAL_INDIKATOREN`:
    gefragt ist, was gemessen VORLIEGT. Ein Instrument, das der Schreibpfad
    kennt, aber im Bestand nicht führt, gehört nicht in ein Handbuch, das
    Zahlen verspricht.
    """
    zeilen = (
        db.query(AnalyseSnapshotIndikator.indikator_name)
        .join(AnalyseSnapshot,
              AnalyseSnapshot.id == AnalyseSnapshotIndikator.snapshot_id)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .filter(AnalyseSnapshotIndikator.wert_numeric.isnot(None))
        .distinct()
        .all()
    )
    return sorted(name for (name,) in zeilen)


def _werte(db: Session, indikator: str, datenmodus: str) -> tuple[dict, dict, int]:
    """Rohwert je Snapshot, Zuordnung, und die Zeilenzahl der alten Kodierung.

    Der dritte Rückgabewert ist die Zahl der Zeilen mit `beitrag_numeric != 0`
    — also genau das, was die frühere Aufzeichnung geführt hätte. Er beweist
    den Abdeckungsgewinn, ohne den Kontrollversuch zu verunreinigen.
    """
    zeilen = (
        db.query(AnalyseSnapshot.id, AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt,
                 AnalyseSnapshotIndikator.wert_numeric,
                 AnalyseSnapshotIndikator.beitrag_numeric)
        .join(AnalyseSnapshotIndikator,
              AnalyseSnapshotIndikator.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .filter(AnalyseSnapshotIndikator.indikator_name == indikator)
        .filter(AnalyseSnapshotIndikator.wert_numeric.isnot(None))
        .all()
    )

    werte: dict[int, float] = {}
    zuordnung: dict[int, tuple] = {}
    alt = 0
    for snapshot_id, ticker, zeitpunkt, wert, beitrag in zeilen:
        werte[snapshot_id] = float(wert)
        zuordnung[snapshot_id] = (ticker, zeitpunkt)
        if beitrag:
            alt += 1
    return werte, zuordnung, alt


def _raenge(werte: dict[int, float], zuordnung: dict[int, tuple],
            minimum_querschnitt: int = MIN_QUERSCHNITT) -> dict[int, float]:
    """Perzentilrang je Snapshot, gebildet je Kalenderwoche und Handelsplatz."""
    eimer: dict[tuple, dict[str, Optional[float]]] = defaultdict(dict)
    verweise: dict[tuple, list[tuple]] = defaultdict(list)

    for snapshot_id, wert in werte.items():
        ticker, zeitpunkt = zuordnung[snapshot_id]
        jahr, woche, _ = zeitpunkt.isocalendar()
        eimer[(jahr, woche)][ticker] = wert
        verweise[(jahr, woche)].append((snapshot_id, ticker))

    raenge: dict[int, float] = {}
    for schluessel, gruppe in eimer.items():
        gerangt = raenge_je_gruppe(gruppe, benchmark_fuer, minimum_querschnitt)
        for snapshot_id, ticker in verweise[schluessel]:
            if ticker in gerangt:
                raenge[snapshot_id] = gerangt[ticker]
    return raenge


# ---------------------------------------------------------------------------
# Ein Instrument, ein Horizont
# ---------------------------------------------------------------------------

def _gruppieren(db: Session, werte: dict, raenge: dict, horizont: int,
                datenmodus: str, teil: Optional[str]) -> tuple[dict, dict, list, dict]:
    """Ordnet Outcomes den Quintilen und dem Vorzeichen zu — identische Zeilen."""
    query = (
        db.query(AnalyseSnapshot.id,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.benchmark_return)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
    )
    if teil:
        query = split_filter(query, teil, grenze_lesen())

    zaehlwerk = {"zeilen": 0, "ohne_wert": 0, "ohne_rang": 0, "verwertet": 0}
    stetig: dict[int, list[tuple]] = defaultdict(list)
    binaer: dict[int, list[tuple]] = defaultdict(list)
    alle: list[Optional[float]] = []

    for snapshot_id, ret, benchmark in query.all():
        zaehlwerk["zeilen"] += 1
        wert = werte.get(snapshot_id)
        if wert is None:
            zaehlwerk["ohne_wert"] += 1
            continue
        q = quintil(raenge.get(snapshot_id))
        vz = vorzeichen(wert)
        if q is None or vz is None:
            # Ohne Rang faellt die Zeile aus BEIDEN Fassungen — sonst waere
            # der Vergleich keiner. Derselbe Grund wie in kodierung.py.
            zaehlwerk["ohne_rang"] += 1
            continue
        zaehlwerk["verwertet"] += 1
        u = ueberrendite(ret, benchmark)
        alle.append(u)
        stetig[q].append((ret, u))
        binaer[vz].append((ret, u))

    return stetig, binaer, alle, zaehlwerk


def _spread(zeilen: list[dict], schluessel: str, oben, unten) -> Optional[float]:
    """Oben minus unten in Prozentpunkten — für beide Fassungen gleich gebaut."""
    je_gruppe = {z[schluessel]: z.get("markt_trefferquote") for z in zeilen}
    hoch, tief = je_gruppe.get(oben), je_gruppe.get(unten)
    if hoch is None or tief is None:
        return None
    return round(hoch - tief, 1)


def _monoton(zeilen: list[dict]) -> Optional[bool]:
    """Steigt die Marktquote über die Quintile durchgehend?

    Die eigentliche Qualitätsprüfung. Eine einzelne herausragende Zelle ist
    bei fünf Tests ein Zufallskandidat; eine durchgehende Treppe ist es nicht.
    Ohne diese Angabe liest man einen Spread als Fund, der aus zwei
    Ausreissern an den Enden besteht.
    """
    quoten = [z.get("markt_trefferquote") for z in sorted(
        zeilen, key=lambda z: z["quintil"])]
    if any(q is None for q in quoten) or len(quoten) < 2:
        return None
    steigend = all(b >= a for a, b in zip(quoten, quoten[1:]))
    fallend = all(b <= a for a, b in zip(quoten, quoten[1:]))
    return steigend or fallend


def instrument_lesen(db: Session, indikator: str, horizont: int = 7,
                     datenmodus: str = "HISTORISCH",
                     teil: Optional[str] = TRAIN,
                     minimum: int = MIN_STICHPROBE,
                     z: Optional[float] = None,
                     vorberechnet: Optional[tuple] = None) -> dict:
    """Die Handbuchseite eines Instruments auf einem Horizont.

    Args:
        z: Kritischer z-Wert aus `z_korrigiert`. Bei einem Durchlauf über
            mehrere Instrumente vom Aufrufer vorgegeben, damit über ALLE
            Zellen korrigiert wird (siehe Modul-Docstring).
        vorberechnet: (werte, zuordnung, alt, raenge) aus einem früheren
            Aufruf. Die Rangbildung ist horizontunabhängig und der teuerste
            Teil; sie je Horizont zu wiederholen wäre dreifache Arbeit für
            dasselbe Ergebnis.

    Returns:
        {"indikator", "horizont_tage", "teil", "basis_markt", "n", "stetig",
         "binaer", "spread_stetig_pp", "spread_binaer_pp", "monoton",
         "abdeckung_alt", "gegenlaeufig", "z_korrigiert", "zaehlwerk"}
    """
    if vorberechnet is None:
        werte, zuordnung, alt = _werte(db, indikator, datenmodus)
        raenge = _raenge(werte, zuordnung)
    else:
        werte, zuordnung, alt, raenge = vorberechnet

    stetig, binaer, alle, zaehlwerk = _gruppieren(
        db, werte, raenge, horizont, datenmodus, teil)

    ergebnis: dict = {
        "indikator": indikator, "horizont_tage": horizont, "teil": teil,
        "basis_markt": None, "n": 0, "stetig": [], "binaer": [],
        "spread_stetig_pp": None, "spread_binaer_pp": None, "monoton": None,
        "abdeckung_alt": alt, "abdeckung_neu": len(werte),
        "gegenlaeufig": indikator in GEGENLAEUFIG,
        "z_korrigiert": None if z is None else round(z, 2),
        "zaehlwerk": zaehlwerk,
    }
    if not stetig:
        return ergebnis

    basis_markt = anteil_schlaegt_markt(alle)
    if z is None:
        z = z_korrigiert(len(stetig) + len(binaer))
        ergebnis["z_korrigiert"] = round(z, 2)

    def _zeilen(gruppen: dict, schluessel: str) -> list[dict]:
        return [
            {schluessel: k, "horizont_tage": horizont, "teil": teil,
             **zelle_gegen_markt([r for r, _ in gruppen[k]],
                                 [u for _, u in gruppen[k]],
                                 basis_markt, horizont, minimum=minimum, z=z)}
            for k in sorted(gruppen)
        ]

    zeilen_stetig = _zeilen(stetig, "quintil")
    zeilen_binaer = _zeilen(binaer, "vorzeichen")

    ergebnis.update({
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "n": sum(len(v) for v in stetig.values()),
        "stetig": zeilen_stetig,
        "binaer": zeilen_binaer,
        "spread_stetig_pp": _spread(zeilen_stetig, "quintil", QUANTILE, 1),
        "spread_binaer_pp": _spread(zeilen_binaer, "vorzeichen", 1, -1),
        "monoton": _monoton(zeilen_stetig),
    })
    return ergebnis


# ---------------------------------------------------------------------------
# Das Handbuch
# ---------------------------------------------------------------------------

def jahresstabilitaet(db: Session, indikator: str, horizont: int = 7,
                      datenmodus: str = "HISTORISCH",
                      teil: Optional[str] = TRAIN,
                      minimum: int = MIN_STICHPROBE,
                      vorberechnet: Optional[tuple] = None) -> dict:
    """Haelt der Spread ueber die Kalenderjahre sein Vorzeichen?

    **Das schaerfste Kriterium dieses Projekts.** Acht von acht bisherigen
    Kandidaten sind hier gestorben, und zwar immer auf dieselbe Weise: gepoolt
    ein Vorsprung, nach Jahren getrennt ein einzelnes Regime, das ihn traegt,
    und andere, die ihn umkehren. Querschnitts-Momentum trug in genau einem
    von fuenf Regimen (+4,8 pp) und kehrte sich 2020 um (unterstes Dezil
    +11,9 pp). Gepoolt blieben +0,2 pp.

    **Die Raenge werden global gebildet, nicht je Jahr.** Dieselbe
    Entscheidung wie in `regime.py`: ein Rang je Jahr wuerde die Frage
    veraendern — dann verglichen sich Titel nur noch innerhalb desselben
    Jahres, und die Aussage waere eine andere als die des Handbuchs.

    **Jedes Jahr bekommt seine eigene Marktbasis.** Der Anteil der Titel, die
    ihren Index schlagen, schwankt erheblich zwischen Marktphasen — in §2i
    lagen 44,3 % und 58,7 % nebeneinander, also 4,2 pp Unterschied allein aus
    der Basis. Wer gegen eine gemeinsame Basis rechnet, misst die Marktbreite
    des Jahres statt des Signals.

    Returns:
        {"indikator", "horizont_tage", "jahre": [...], "vorzeichen_gleich",
         "jahre_gesamt", "spread_gepoolt_pp"}
    """
    if vorberechnet is None:
        werte, zuordnung, alt = _werte(db, indikator, datenmodus)
        raenge = _raenge(werte, zuordnung)
    else:
        werte, zuordnung, alt, raenge = vorberechnet

    query = (
        db.query(AnalyseSnapshot.id,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.benchmark_return)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
    )
    if teil:
        query = split_filter(query, teil, grenze_lesen())

    # {jahr: {quintil: [(rendite, ueberrendite)]}} plus alle Ueberrenditen
    # des Jahres fuer dessen eigene Basis.
    je_jahr: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    basis_je_jahr: dict[int, list] = defaultdict(list)

    for snapshot_id, ret, benchmark in query.all():
        wert = werte.get(snapshot_id)
        if wert is None:
            continue
        q = quintil(raenge.get(snapshot_id))
        if q is None:
            continue
        jahr = zuordnung[snapshot_id][1].year
        u = ueberrendite(ret, benchmark)
        je_jahr[jahr][q].append((ret, u))
        basis_je_jahr[jahr].append(u)

    zeilen = []
    for jahr in sorted(je_jahr):
        gruppen = je_jahr[jahr]
        if 1 not in gruppen or QUANTILE not in gruppen:
            continue
        basis = anteil_schlaegt_markt(basis_je_jahr[jahr])
        z = z_korrigiert(len(je_jahr) * 2)  # zwei Enden je Jahr
        oben = zelle_gegen_markt([r for r, _ in gruppen[QUANTILE]],
                                 [u for _, u in gruppen[QUANTILE]],
                                 basis, horizont, minimum=minimum, z=z)
        unten = zelle_gegen_markt([r for r, _ in gruppen[1]],
                                  [u for _, u in gruppen[1]],
                                  basis, horizont, minimum=minimum, z=z)
        hoch, tief = oben.get("markt_trefferquote"), unten.get("markt_trefferquote")
        zeilen.append({
            "jahr": jahr,
            "n": sum(len(v) for v in gruppen.values()),
            "basis_markt": round(basis, 1) if basis is not None else None,
            "q5_vorsprung_pp": oben.get("markt_vorsprung_pp"),
            "q1_vorsprung_pp": unten.get("markt_vorsprung_pp"),
            "spread_pp": (None if hoch is None or tief is None
                          else round(hoch - tief, 1)),
            "q5_signifikant": oben.get("signifikant_korrigiert"),
        })

    spreads = [z["spread_pp"] for z in zeilen if z["spread_pp"] is not None]
    positiv = sum(1 for s in spreads if s > 0)
    return {
        "indikator": indikator, "horizont_tage": horizont, "teil": teil,
        "jahre": zeilen, "jahre_gesamt": len(spreads),
        # Das eigentliche Kriterium: wie oft traegt der Spread dasselbe
        # Vorzeichen wie die Mehrheit? Bei neun Jahren ist fuenf reiner Zufall.
        "vorzeichen_gleich": max(positiv, len(spreads) - positiv),
    }


def handbuch(db: Session, horizonte: Sequence[int] = HORIZONTE,
             namen: Optional[Sequence[str]] = None,
             datenmodus: str = "HISTORISCH",
             teil: Optional[str] = TRAIN,
             minimum: int = MIN_STICHPROBE) -> dict:
    """Alle Instrumente über alle Horizonte, mit einer gemeinsamen Korrektur.

    Die Korrektur spannt über sämtliche Zellen des Durchlaufs — sieben je
    Instrument und Horizont (fünf Quintile, zwei Vorzeichen). Bei zehn
    Instrumenten und drei Horizonten sind das 210 Tests, und genau so viele
    hat man gerechnet. Wer stattdessen je Instrument korrigiert und danach das
    beste zitiert, betreibt die Mehrfachtest-Inflation, gegen die dieses
    Projekt die halbe Messreihe verloren hat.

    Returns:
        {"instrumente": [...], "z_korrigiert", "anzahl_tests", "teil",
         "datenmodus", "horizonte"}
    """
    namen = list(namen) if namen else instrumente(db, datenmodus)
    if not namen:
        logger.warning("Handbuch: keine Instrumente mit Rohwerten im Bestand.")
        return {"instrumente": [], "z_korrigiert": None, "anzahl_tests": 0,
                "teil": teil, "datenmodus": datenmodus,
                "horizonte": list(horizonte)}

    # (QUANTILE + 2): fünf Quintile plus die zwei Vorzeichengruppen.
    anzahl_tests = len(namen) * len(horizonte) * (QUANTILE + 2)
    z = z_korrigiert(anzahl_tests)
    logger.info("Handbuch: %d Instrumente x %d Horizonte = %d Tests, z = %.2f.",
                len(namen), len(horizonte), anzahl_tests, z)

    seiten = []
    for name in namen:
        werte, zuordnung, alt = _werte(db, name, datenmodus)
        raenge = _raenge(werte, zuordnung)
        logger.info("Handbuch/%s: %d Rohwerte, %d gerangt (alte Kodierung: %d).",
                    name, len(werte), len(raenge), alt)
        for horizont in horizonte:
            seiten.append(instrument_lesen(
                db, name, horizont=horizont, datenmodus=datenmodus, teil=teil,
                minimum=minimum, z=z,
                vorberechnet=(werte, zuordnung, alt, raenge)))

    return {"instrumente": seiten, "z_korrigiert": round(z, 2),
            "anzahl_tests": anzahl_tests, "teil": teil,
            "datenmodus": datenmodus, "horizonte": list(horizonte)}
