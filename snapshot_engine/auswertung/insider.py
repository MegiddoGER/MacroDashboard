"""
snapshot_engine/auswertung/insider.py — Tragen Insiderkäufe? (Auftrag B)

Die zehnte geprüfte Signalfamilie und die vierte mit eigener Quelle. Die
Hypothese ist die des Besitzers und die von Lakonishok/Lee (2001): **jemand
mit Informationsvorsprung kauft am Markt, und das sagt etwas über die
Folgerendite.** Hier ist oben gut — wie bei PEAD (§2e) und den Revisionen
(§2f), anders als bei den Accruals (§2g).

**Zwei Messungen nebeneinander, und die zweite ist die eigentliche.**

1. *Quintile des Netto-Insiderhandels.* Die Form, in der die übrigen neun
   Familien gemessen wurden, damit der Befund vergleichbar bleibt. Die
   Kennzahl ist `npr = (Käufer − Verkäufer) / (Käufer + Verkäufer)` über
   sechs Monate, je Person gezählt.
2. *Ereignisgruppen.* Der Netto-Handel ist in diesem Universum **stark
   linkslastig**: Verkäufe sind Alltag, Käufe am Markt sind selten (gemessen
   an 2024Q1: 8.275 Verkäufe gegen 520 Käufe bei 611 Tickern). Über Ränge
   gerechnet fallen deshalb ganze Quintile auf denselben Wert. Die Frage
   „hat überhaupt jemand gekauft, und waren es mehrere?" ist auf solchen
   Daten die ehrlichere Form — und sie ist zugleich das
   Cluster-Kriterium der Literatur.

**Die Routine-Trennung entscheidet, ob überhaupt etwas gemessen wird.**
Cohen/Malloy/Pomorski (2012): Routinegeschäfte tragen null, opportunistische
82 bp/Monat. Beide Gruppen zusammen ergeben überwiegend Rauschen. Die Trennung
läuft in `services.insider.ist_routine` und ist **punkt-in-zeit** — ein
Vorjahresgeschäft macht eine Person nur dann zur Routine, wenn seine Meldung
zum Auswertungszeitpunkt bereits eingereicht war.

**Der Querschnitt ist US-only.** Form 4 gibt es nur für SEC-Registrierte; wie
bei §2f und §2g fällt der Xetra-Querschnitt unter `MIN_QUERSCHNITT` und ganz
heraus.

**Kursnähe** wird mitgemessen (`auswertung/kursnaehe`), wie seit §2f Regel.
Die Erwartung ist niedrig: ein Kaufentschluss einer Person ist keine
Kursableitung. Die Prüfung ist an §2g geeicht (dort −0,001 gegen 0,473 bei
einem umetikettierten Kurssignal) und kann das jetzt bestätigen oder nicht.
"""

import logging
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from services.cross_sectional_momentum import raenge_je_gruppe
from services.insider import (
    FENSTER_TAGE, MIN_ABSTAND_TAGE, geschaefte_je_ticker, kennzahl_vor,
    routine_kalender,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, mittlere_ueberrendite,
    zelle_gegen_markt, z_korrigiert,
)
from snapshot_engine.auswertung.holdout import TRAIN, grenze_lesen, split_filter
from snapshot_engine.auswertung.kursnaehe import kursnaehe_pruefen
from snapshot_engine.benchmark import benchmark_fuer, ueberrendite
from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)

logger = logging.getLogger(__name__)


QUANTILE = 5
MIN_QUERSCHNITT = 20

# Ab so vielen verschiedenen Käufern im Fenster gilt es als Cluster. Die
# Literatur setzt drei an; bei 611 überwiegend großen Titeln und rund 520
# Marktkäufen je Quartal wäre das eine Gruppe von wenigen Dutzend Zeilen. Zwei
# ist der Kompromiss, der die Gruppe messbar hält — und er wird ausgewiesen,
# nicht versteckt.
CLUSTER_AB = 2

GRUPPE_KEIN_KAUF = "0 Käufer"
GRUPPE_EIN_KAUF = "1 Käufer"
GRUPPE_CLUSTER = f"{CLUSTER_AB}+ Käufer"


def quintil(rang: Optional[float]) -> Optional[int]:
    """Quintil 1–5 zu einem Perzentilrang. 5 ist der stärkste Nettokauf."""
    if rang is None:
        return None
    return min(QUANTILE, int(rang // (100.0 / QUANTILE)) + 1)


def kaeufergruppe(anzahl: int) -> str:
    """Ereignisgruppe zur Zahl verschiedener Käufer im Fenster.

    Sie ist immer bestimmbar, wo eine Kennzahl vorliegt — `kennzahl_vor`
    liefert die Käuferzahl als Ganzzahl oder gar nichts. Genau darin liegt
    ihr Vorteil gegenüber dem Quintil: sie braucht keinen Querschnitt.
    """
    if anzahl <= 0:
        return GRUPPE_KEIN_KAUF
    if anzahl < CLUSTER_AB:
        return GRUPPE_EIN_KAUF
    return GRUPPE_CLUSTER


# ---------------------------------------------------------------------------
# Zuordnung und Ränge
# ---------------------------------------------------------------------------

def _kennzahlen_je_snapshot(db: Session, datenmodus: str,
                            fenster_tage: int = FENSTER_TAGE
                            ) -> tuple[dict[int, dict], dict[int, tuple]]:
    """Je Snapshot der Netto-Insiderhandel der vorangegangenen Monate.

    Returns:
        ({snapshot_id: Kennzahlen aus `kennzahl_vor`},
         {snapshot_id: (ticker, zeitpunkt)})

    Snapshots ohne jede Meldung im Fenster tragen **keine** Kennzahl — sie
    fallen heraus statt als „null Käufer, null Verkäufer" zu zählen. Ein
    Titel, über den nichts gemeldet wurde, ist nicht dasselbe wie einer, bei
    dem Insider verkauft und nicht gekauft haben.
    """
    reihen = geschaefte_je_ticker(db)
    kalender = routine_kalender(reihen)
    logger.info("Insider: %d Ticker mit Geschäften, %d Personen-Monate im "
                "Kalender.", len(reihen), len(kalender))

    snapshots = (
        db.query(AnalyseSnapshot.id, AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .all()
    )

    werte: dict[int, dict] = {}
    zuordnung: dict[int, tuple] = {}
    ohne = 0
    for snapshot_id, ticker, zeitpunkt in snapshots:
        kennzahl = kennzahl_vor(reihen.get(ticker), zeitpunkt, kalender,
                                fenster_tage=fenster_tage,
                                min_abstand_tage=MIN_ABSTAND_TAGE)
        if kennzahl is None:
            ohne += 1
            continue
        werte[snapshot_id] = kennzahl
        zuordnung[snapshot_id] = (ticker, zeitpunkt)

    logger.info("Insider: %d Snapshots mit Meldung im %d-Tage-Fenster, %d ohne.",
                len(werte), fenster_tage, ohne)
    return werte, zuordnung


def npr_raenge(werte: dict[int, dict], zuordnung: dict[int, tuple],
               feld: str = "npr",
               minimum_querschnitt: int = MIN_QUERSCHNITT) -> dict[int, float]:
    """Perzentilrang des Netto-Insiderhandels je Snapshot, je Woche und Platz.

    Die Kalenderwoche ist nötig, weil die Snapshots nicht auf gemeinsamen
    Stichtagen liegen — dieselbe Begründung wie in `momentum.py` und
    `accruals.py`.
    """
    eimer: dict[tuple, dict[str, Optional[float]]] = defaultdict(dict)
    verweise: dict[tuple, list[tuple]] = defaultdict(list)

    for snapshot_id, kennzahl in werte.items():
        wert = kennzahl.get(feld)
        if wert is None:
            continue
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

    logger.info("Insider: %d Snapshots gerangt (%s).", len(raenge), feld)
    return raenge


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

def _beobachtungen(db: Session, horizont: int, datenmodus: str,
                   teil: Optional[str]) -> list[tuple]:
    """(snapshot_id, Rendite, Benchmarkrendite) der auswertbaren Zeilen."""
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
    return query.all()


def insider_auswerten(db: Session, horizont: int = 30,
                      datenmodus: str = "HISTORISCH",
                      teil: Optional[str] = TRAIN,
                      minimum: int = MIN_STICHPROBE,
                      fenster_tage: int = FENSTER_TAGE,
                      z_tests: Optional[int] = None,
                      mit_kursnaehe: bool = True) -> dict:
    """Netto-Insiderhandel gegen den Markt — als Quintile und als Ereignis.

    Args:
        z_tests: Anzahl Tests für die Šidák-Korrektur. Ohne Angabe wird über
            die Zellen DIESES Aufrufs korrigiert. Ein Durchlauf über mehrere
            Horizonte muss die Gesamtzahl übergeben, sonst ist die Korrektur
            zu milde — derselbe Fehler, den `handbuch()` vermeidet.

    Returns:
        {"basis_markt", "basis_ertrag", "n_gesamt", "quintile", "spread_pp",
         "gruppen", "gruppen_opportunistisch", "cluster_vorsprung_pp",
         "z_korrigiert", "kursnaehe", "zaehlwerk", "teil", "horizont_tage",
         "fenster_tage"}

    `spread_pp` ist **Q5 minus Q1** — hoher minus niedriger Nettokauf. Positiv
    heißt: die Hypothese bestätigt sich.
    """
    werte, zuordnung = _kennzahlen_je_snapshot(db, datenmodus, fenster_tage)
    raenge = npr_raenge(werte, zuordnung)

    zaehlwerk = {"zeilen": 0, "ohne_kennzahl": 0, "ohne_rang": 0,
                 "verwertet": 0}
    quintile: dict[int, list[tuple]] = defaultdict(list)
    gruppen: dict[str, list[tuple]] = defaultdict(list)
    gruppen_opp: dict[str, list[tuple]] = defaultdict(list)
    alle: list[Optional[float]] = []

    for snapshot_id, ret, benchmark in _beobachtungen(
            db, horizont, datenmodus, teil):
        zaehlwerk["zeilen"] += 1
        kennzahl = werte.get(snapshot_id)
        if kennzahl is None:
            zaehlwerk["ohne_kennzahl"] += 1
            continue
        zaehlwerk["verwertet"] += 1
        u = ueberrendite(ret, benchmark)
        alle.append(u)

        # Die Ereignisgruppe steht IMMER — sie braucht keinen Querschnitt.
        gruppen[kaeufergruppe(kennzahl["kaeufer"])].append((ret, u))
        gruppen_opp[kaeufergruppe(
            kennzahl["opportunistische_kaeufer"])].append((ret, u))

        q = quintil(raenge.get(snapshot_id))
        if q is None:
            zaehlwerk["ohne_rang"] += 1
            continue
        quintile[q].append((ret, u))

    logger.info("Insider: %d Zeilen, %d verwertet, %d ohne Rang.",
                zaehlwerk["zeilen"], zaehlwerk["verwertet"],
                zaehlwerk["ohne_rang"])

    ergebnis: dict = {
        "basis_markt": None, "basis_ertrag": None, "n_gesamt": 0,
        "quintile": [], "spread_pp": None, "gruppen": [],
        "gruppen_opportunistisch": [], "cluster_vorsprung_pp": None,
        "z_korrigiert": None, "kursnaehe": None, "zaehlwerk": zaehlwerk,
        "teil": teil, "horizont_tage": horizont, "fenster_tage": fenster_tage,
    }
    if not gruppen:
        return ergebnis

    basis_markt = anteil_schlaegt_markt(alle)
    basis_ertrag = mittlere_ueberrendite(alle)
    anzahl = z_tests if z_tests else (
        len(quintile) + len(gruppen) + len(gruppen_opp))
    z = z_korrigiert(anzahl)

    def _zeilen(sammlung: dict, schluesselname: str) -> list[dict]:
        return [
            {schluesselname: schluessel, "horizont_tage": horizont,
             "teil": teil,
             **zelle_gegen_markt([r for r, _ in sammlung[schluessel]],
                                 [u for _, u in sammlung[schluessel]],
                                 basis_markt, horizont, minimum=minimum, z=z,
                                 basis_ertrag=basis_ertrag)}
            for schluessel in sorted(sammlung)
        ]

    quintil_zeilen = _zeilen(quintile, "quintil")
    gruppen_zeilen = _zeilen(gruppen, "gruppe")
    gruppen_opp_zeilen = _zeilen(gruppen_opp, "gruppe")

    ergebnis.update({
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "basis_ertrag": (round(basis_ertrag, 3)
                         if basis_ertrag is not None else None),
        "n_gesamt": zaehlwerk["verwertet"],
        "quintile": quintil_zeilen,
        "spread_pp": _spread(quintil_zeilen),
        "gruppen": gruppen_zeilen,
        "gruppen_opportunistisch": gruppen_opp_zeilen,
        "cluster_vorsprung_pp": _cluster_vorsprung(gruppen_zeilen),
        "z_korrigiert": round(z, 2),
    })

    if mit_kursnaehe:
        # Auf den Rängen und nicht auf den Rohwerten — wie in §2g, weil auch
        # die Auswertung auf Rängen läuft.
        ergebnis["kursnaehe"] = kursnaehe_pruefen(
            db, raenge, zuordnung, datenmodus=datenmodus)

    return ergebnis


def _spread(zeilen: list[dict]) -> Optional[float]:
    """Q5 minus Q1 in Prozentpunkten — hoher minus niedriger Nettokauf."""
    je_quintil = {z["quintil"]: z.get("markt_trefferquote") for z in zeilen}
    hoch, niedrig = je_quintil.get(QUANTILE), je_quintil.get(1)
    if hoch is None or niedrig is None:
        return None
    return round(hoch - niedrig, 1)


def _cluster_vorsprung(zeilen: list[dict]) -> Optional[float]:
    """Clustergruppe minus Gruppe ohne Käufer, in Prozentpunkten.

    Das eigentliche Maß dieser Familie: nicht „wo im Querschnitt steht der
    Titel", sondern „haben mehrere Insider gekauft oder keiner".
    """
    je_gruppe = {z["gruppe"]: z.get("markt_trefferquote") for z in zeilen}
    cluster, ohne = je_gruppe.get(GRUPPE_CLUSTER), je_gruppe.get(GRUPPE_KEIN_KAUF)
    if cluster is None or ohne is None:
        return None
    return round(cluster - ohne, 1)


# ---------------------------------------------------------------------------
# Jahresstabilität — die Hürde, an der neun Familien gescheitert sind
# ---------------------------------------------------------------------------

def insider_jahresstabilitaet(db: Session, horizont: int = 30,
                              datenmodus: str = "HISTORISCH",
                              teil: Optional[str] = TRAIN,
                              minimum: int = MIN_STICHPROBE,
                              fenster_tage: int = FENSTER_TAGE) -> dict:
    """Hält der Cluster-Vorsprung über die Kalenderjahre sein Vorzeichen?

    **Das schärfste Kriterium dieses Projekts** (siehe
    `handbuch.jahresstabilitaet`): neun Familien haben gepoolt einen Vorsprung
    gezeigt und ihn nach Jahren getrennt wieder verloren. Wer einen Kandidaten
    vorschlägt, muss zuerst sagen können, warum er hier nicht scheitert.

    Gemessen wird auf den **Ereignisgruppen**, nicht auf den Quintilen: die
    Gruppen brauchen keinen Querschnitt und bleiben deshalb auch in Jahren
    stehen, in denen zu wenige Titel je Woche eine Kennzahl tragen.

    **Jedes Jahr bekommt seine eigene Marktbasis** — der Anteil der Titel, die
    ihren Index schlagen, schwankt zwischen Marktphasen um mehrere
    Prozentpunkte. Gegen eine gemeinsame Basis gerechnet misst man die
    Marktbreite des Jahres statt des Signals.

    Returns:
        {"jahre": [...], "jahre_gesamt", "vorzeichen_gleich",
         "ertrag_jahre_gesamt", "ertrag_vorzeichen_gleich", ...}
    """
    werte, zuordnung = _kennzahlen_je_snapshot(db, datenmodus, fenster_tage)

    je_jahr: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    basis_je_jahr: dict[int, list] = defaultdict(list)

    for snapshot_id, ret, benchmark in _beobachtungen(
            db, horizont, datenmodus, teil):
        kennzahl = werte.get(snapshot_id)
        if kennzahl is None:
            continue
        jahr = zuordnung[snapshot_id][1].year
        u = ueberrendite(ret, benchmark)
        je_jahr[jahr][kaeufergruppe(kennzahl["kaeufer"])].append((ret, u))
        basis_je_jahr[jahr].append(u)

    zeilen = []
    z = z_korrigiert(max(1, len(je_jahr)) * 2)  # zwei Enden je Jahr
    for jahr in sorted(je_jahr):
        gruppen = je_jahr[jahr]
        if GRUPPE_CLUSTER not in gruppen or GRUPPE_KEIN_KAUF not in gruppen:
            continue
        basis = anteil_schlaegt_markt(basis_je_jahr[jahr])
        ertrag = mittlere_ueberrendite(basis_je_jahr[jahr])
        oben = zelle_gegen_markt([r for r, _ in gruppen[GRUPPE_CLUSTER]],
                                 [u for _, u in gruppen[GRUPPE_CLUSTER]],
                                 basis, horizont, minimum=minimum, z=z,
                                 basis_ertrag=ertrag)
        unten = zelle_gegen_markt([r for r, _ in gruppen[GRUPPE_KEIN_KAUF]],
                                  [u for _, u in gruppen[GRUPPE_KEIN_KAUF]],
                                  basis, horizont, minimum=minimum, z=z,
                                  basis_ertrag=ertrag)
        hoch, tief = oben.get("markt_trefferquote"), unten.get("markt_trefferquote")
        e_hoch = oben.get("ueberrendite_vorsprung_pp")
        e_tief = unten.get("ueberrendite_vorsprung_pp")
        zeilen.append({
            "jahr": jahr,
            "n": sum(len(v) for v in gruppen.values()),
            "n_cluster": len(gruppen[GRUPPE_CLUSTER]),
            "basis_markt": round(basis, 1) if basis is not None else None,
            "cluster_vorsprung_pp": oben.get("markt_vorsprung_pp"),
            "ohne_kauf_vorsprung_pp": unten.get("markt_vorsprung_pp"),
            "spread_pp": (None if hoch is None or tief is None
                          else round(hoch - tief, 1)),
            "ertrag_spread_pp": (None if e_hoch is None or e_tief is None
                                 else round(e_hoch - e_tief, 3)),
            "cluster_signifikant": oben.get("signifikant_korrigiert"),
        })

    spreads = [z_["spread_pp"] for z_ in zeilen if z_["spread_pp"] is not None]
    positiv = sum(1 for s in spreads if s > 0)
    ertraege = [z_["ertrag_spread_pp"] for z_ in zeilen
                if z_["ertrag_spread_pp"] is not None]
    ertrag_positiv = sum(1 for s in ertraege if s > 0)
    return {
        "horizont_tage": horizont, "teil": teil, "fenster_tage": fenster_tage,
        "jahre": zeilen, "jahre_gesamt": len(spreads),
        "vorzeichen_gleich": max(positiv, len(spreads) - positiv),
        "ertrag_jahre_gesamt": len(ertraege),
        "ertrag_vorzeichen_gleich": max(ertrag_positiv,
                                        len(ertraege) - ertrag_positiv),
    }
