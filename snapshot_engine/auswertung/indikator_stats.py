"""
snapshot_engine/auswertung/indikator_stats.py — Auswertung je Einzelindikator.

Beantwortet die eigentliche Kernfrage der Engine: funktioniert RSI? Sagt ein
bullisches FVG tatsächlich steigende Kurse voraus? Trägt der DCF-Wert etwas
bei — oder ist er Rauschen?

Ausgewertet wird nach Richtung des Indikator-Beitrags: ein Indikator, der zum
Zeitpunkt X bullisch beigetragen hat (beitrag_numeric > 0), wird daran
gemessen, ob der Kurs anschließend gestiegen ist — und umgekehrt.

Rein informative Einträge (Beitrag "Info", z.B. ADX/MACD in scoring.py) haben
beitrag_numeric = NULL und werden nicht als Prognose gewertet.
"""

import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from snapshot_engine.models import (
    MIN_BEWEGUNG_PCT, AnalyseModus, AnalyseSnapshot, AnalyseSnapshotIndikator,
    AnalyseSnapshotOutcome, Granularitaet,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, STATUS_OK, anteil_schlaegt_markt, kennzahlen_aus_returns,
    mit_ueberrendite,
)
from snapshot_engine.benchmark import ueberrendite

logger = logging.getLogger(__name__)

RICHTUNG_BULLISCH = "bullisch"
RICHTUNG_BEARISCH = "bearisch"


def _treffer(outcome_return: float, richtung: str) -> bool | None:
    """Trefferbewertung eines Indikator-Signals — identisch zu `erfolg_bewerten`.

    Zuvor galt hier schlicht `r > 0` bzw. `r < 0`, während die Übersichtsseite
    Bewegungen unter MIN_BEWEGUNG_PCT als Rauschen ausschloss. Beide Seiten
    wiesen damit Trefferquoten aus, die nicht vergleichbar waren, ohne dass das
    irgendwo stand. `outcome_return` IST die prozentuale Veränderung gegen den
    Einstiegskurs, die Schwelle lässt sich also direkt anlegen.
    """
    if outcome_return is None or abs(outcome_return) < MIN_BEWEGUNG_PCT:
        return None
    return outcome_return > 0 if richtung == RICHTUNG_BULLISCH else outcome_return < 0


def basisrate(db: Session, horizont: int, datenmodus: str | None = None) -> dict:
    """Unbedingte Vergleichsbasis: was passierte über ALLE Beobachtungen hinweg?

    Ohne diesen Bezugspunkt ist keine Indikator-Zahl interpretierbar: wenn
    Aktien in 55 % aller 7-Tage-Fenster ohnehin steigen, ist ein bullischer
    Indikator mit 55 % Trefferquote wertlos — er misst nur die allgemeine
    Aufwärtsdrift des Marktes, keine Prognosefähigkeit.
    """
    query = (
        db.query(AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.benchmark_return)
        .join(AnalyseSnapshot,
              AnalyseSnapshot.id == AnalyseSnapshotOutcome.snapshot_id)
        .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
    )
    if datenmodus:
        query = query.filter(AnalyseSnapshot.datenmodus == datenmodus)

    leer = {"n": 0, "anteil_positiv": None, "avg_return": None,
            "n_bewertbar": 0, "anteil_positiv_bewertbar": None,
            "anteil_schlaegt_markt": None}
    try:
        zeilen = query.all()
    except Exception as e:
        logger.error("Basisrate fehlgeschlagen: %s", e, exc_info=True)
        return dict(leer)

    returns = [r for r, _ in zeilen]
    if not returns:
        return dict(leer)

    positiv = sum(1 for r in returns if r > 0)

    # Vergleichsbasis unter derselben Mindestbewegung, die auch die
    # Trefferbewertung anlegt — sonst werden ungleiche Grundgesamtheiten
    # verglichen und der ausgewiesene Vorsprung ist systematisch verschoben.
    bewegt = [r for r in returns if abs(r) >= MIN_BEWEGUNG_PCT]
    positiv_bewegt = sum(1 for r in bewegt if r > 0)

    # Unbedingte Marktquote als Bezugspunkt der Überrendite — dieselbe Rolle,
    # die `anteil_positiv_bewertbar` für die absolute Trefferquote spielt.
    anteil_markt = anteil_schlaegt_markt(
        [ueberrendite(r, b) for r, b in zeilen])

    return {
        "n": len(returns),
        "anteil_positiv": round(positiv / len(returns) * 100, 1),
        "avg_return": round(sum(returns) / len(returns), 2),
        "n_bewertbar": len(bewegt),
        "anteil_positiv_bewertbar": (round(positiv_bewegt / len(bewegt) * 100, 1)
                                     if bewegt else None),
        "anteil_schlaegt_markt": (round(anteil_markt, 1)
                                  if anteil_markt is not None else None),
    }


def _vorsprung(kennzahlen: dict, basis: dict, richtung: str) -> dict:
    """Vergleicht eine Indikator-Zeile mit der unbedingten Basisrate.

    `vorsprung_pp` in Prozentpunkten: positiv bedeutet, der Indikator trifft
    häufiger als der reine Zufall im selben Zeitraum. Werte nahe 0 heißen:
    der Indikator sagt nichts, was der Markt nicht ohnehin getan hätte.
    """
    anteil = basis.get("anteil_positiv_bewertbar")
    if anteil is None or kennzahlen.get("trefferquote") is None:
        return {"basis_trefferquote": None, "vorsprung_pp": None}

    # Für bearische Signale ist die Vergleichsbasis der Anteil FALLENDER Fenster.
    basis_quote = anteil if richtung == RICHTUNG_BULLISCH else 100.0 - anteil

    return {
        "basis_trefferquote": round(basis_quote, 1),
        "vorsprung_pp": round(kennzahlen["trefferquote"] - basis_quote, 1),
    }


def indikator_leaderboard(db: Session, horizont: int = 7,
                          datenmodus: str | None = None,
                          minimum: int = MIN_STICHPROBE,
                          nur_echte_indikatoren: bool = True) -> list[dict]:
    """Bewertet jeden Einzelindikator getrennt nach bullischem/bearischem Signal.

    Args:
        horizont: Auswertungshorizont in Tagen
        datenmodus: LIVE/HISTORISCH einschränken (None = alle)
        minimum: Mindest-Stichprobe je Zeile
        nur_echte_indikatoren: Migrierte Kategorie-Zeilen ausschließen

    Returns:
        Liste von Dicts, sortiert nach Erwartungswert (beste zuerst).
        Zeilen unterhalb der Mindest-Stichprobe bleiben enthalten, sind aber
        über `status` als unzureichend markiert — sie zu verschweigen würde
        verbergen, wofür schlicht noch Daten fehlen.
    """
    query = (
        # Bewusst nur die benötigten Spalten statt ganzer ORM-Objekte: bei
        # ~700k Indikator-Zeilen ist der Unterschied zwischen Tupeln und
        # hydrierten Entitäten der zwischen einer schnellen und einer
        # unbenutzbaren Seite.
        db.query(AnalyseSnapshotIndikator.indikator_name,
                 AnalyseSnapshotIndikator.kategorie,
                 AnalyseSnapshotIndikator.beitrag_numeric,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.benchmark_return)
        .join(AnalyseSnapshot,
              AnalyseSnapshot.id == AnalyseSnapshotIndikator.snapshot_id)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshotIndikator.beitrag_numeric.isnot(None))
        .filter(AnalyseSnapshotIndikator.beitrag_numeric != 0)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
    )

    if datenmodus:
        query = query.filter(AnalyseSnapshot.datenmodus == datenmodus)
    if nur_echte_indikatoren:
        query = query.filter(
            AnalyseSnapshotIndikator.granularitaet == Granularitaet.INDIKATOR)

    try:
        zeilen = query.all()
    except Exception as e:
        logger.error("Indikator-Leaderboard fehlgeschlagen: %s", e, exc_info=True)
        return []

    # Gruppieren nach (Indikator, Signalrichtung)
    gruppen: dict[tuple, list] = defaultdict(list)
    kategorien: dict[str, str] = {}

    for name, kategorie, beitrag, outcome_return, benchmark_return in zeilen:
        richtung = RICHTUNG_BULLISCH if beitrag > 0 else RICHTUNG_BEARISCH
        # Rendite und Vergleichswert bleiben als Paar beieinander — getrennte
        # Listen liefen bei der Gruppierung auseinander.
        gruppen[(name, richtung)].append((outcome_return, benchmark_return))
        if kategorie:
            kategorien[name] = kategorie

    basis = basisrate(db, horizont, datenmodus)

    ergebnis = []
    for (name, richtung), paare in gruppen.items():
        returns = [r for r, _ in paare]
        # Ein bullischer Indikator "trifft", wenn der Kurs steigt;
        # ein bearischer, wenn er fällt. Bewegungen unterhalb der
        # Mindestschwelle gelten als Rauschen und bleiben unbewertet.
        treffer = [_treffer(r, richtung) for r in returns]
        richtungen = [1 if richtung == RICHTUNG_BULLISCH else -1] * len(returns)

        kennzahlen = mit_ueberrendite(
            kennzahlen_aus_returns(
                returns, treffer, horizont_tage=horizont, minimum=minimum,
                richtungen=richtungen),
            [ueberrendite(r, b) for r, b in paare], richtungen,
            basis.get("anteil_schlaegt_markt"),
            horizont_tage=horizont, minimum=minimum)

        ergebnis.append({
            "indikator": name,
            "kategorie": kategorien.get(name),
            "richtung": richtung,
            "horizont_tage": horizont,
            **kennzahlen,
            **_vorsprung(kennzahlen, basis, richtung),
        })

    # Auswertbare Zeilen zuerst, darin nach Erwartungswert
    ergebnis.sort(
        key=lambda z: (
            z["status"] == STATUS_OK,
            z.get("erwartungswert") if z.get("erwartungswert") is not None else -999,
        ),
        reverse=True,
    )
    return ergebnis


def kategorie_leaderboard(db: Session, horizont: int = 7,
                          datenmodus: str | None = None,
                          minimum: int = MIN_STICHPROBE) -> list[dict]:
    """Wie indikator_leaderboard, aber auf Ebene der fünf Score-Kategorien."""
    query = (
        # Bewusst nur die benötigten Spalten statt ganzer ORM-Objekte: bei
        # ~700k Indikator-Zeilen ist der Unterschied zwischen Tupeln und
        # hydrierten Entitäten der zwischen einer schnellen und einer
        # unbenutzbaren Seite.
        db.query(AnalyseSnapshotIndikator.indikator_name,
                 AnalyseSnapshotIndikator.kategorie,
                 AnalyseSnapshotIndikator.beitrag_numeric,
                 AnalyseSnapshotOutcome.outcome_return,
                 AnalyseSnapshotOutcome.benchmark_return)
        .join(AnalyseSnapshot,
              AnalyseSnapshot.id == AnalyseSnapshotIndikator.snapshot_id)
        .join(AnalyseSnapshotOutcome,
              AnalyseSnapshotOutcome.snapshot_id == AnalyseSnapshot.id)
        .filter(AnalyseSnapshotOutcome.horizont_tage == horizont)
        .filter(AnalyseSnapshotOutcome.ausgewertet.is_(True))
        .filter(AnalyseSnapshotOutcome.outcome_return.isnot(None))
        .filter(AnalyseSnapshotIndikator.beitrag_numeric.isnot(None))
        .filter(AnalyseSnapshotIndikator.beitrag_numeric != 0)
        .filter(AnalyseSnapshotIndikator.kategorie.isnot(None))
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
    )
    if datenmodus:
        query = query.filter(AnalyseSnapshot.datenmodus == datenmodus)

    try:
        zeilen = query.all()
    except Exception as e:
        logger.error("Kategorie-Leaderboard fehlgeschlagen: %s", e, exc_info=True)
        return []

    gruppen: dict[tuple, list] = defaultdict(list)
    for _name, kategorie, beitrag, outcome_return, benchmark_return in zeilen:
        richtung = RICHTUNG_BULLISCH if beitrag > 0 else RICHTUNG_BEARISCH
        gruppen[(kategorie, richtung)].append((outcome_return, benchmark_return))

    basis = basisrate(db, horizont, datenmodus)

    ergebnis = []
    for (kategorie, richtung), paare in gruppen.items():
        returns = [r for r, _ in paare]
        treffer = [_treffer(r, richtung) for r in returns]
        richtungen = [1 if richtung == RICHTUNG_BULLISCH else -1] * len(returns)
        kennzahlen = mit_ueberrendite(
            kennzahlen_aus_returns(returns, treffer,
                                   horizont_tage=horizont, minimum=minimum,
                                   richtungen=richtungen),
            [ueberrendite(r, b) for r, b in paare], richtungen,
            basis.get("anteil_schlaegt_markt"),
            horizont_tage=horizont, minimum=minimum)
        ergebnis.append({
            "kategorie": kategorie,
            "richtung": richtung,
            "horizont_tage": horizont,
            **kennzahlen,
            **_vorsprung(kennzahlen, basis, richtung),
        })

    ergebnis.sort(
        key=lambda z: (
            z["status"] == STATUS_OK,
            z.get("erwartungswert") if z.get("erwartungswert") is not None else -999,
        ),
        reverse=True,
    )
    return ergebnis
