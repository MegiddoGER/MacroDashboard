"""
snapshot_engine/auswertung/nettoemission.py — Traegt die Nettoemission? (P2-06)

Elfte Signalfamilie, und die erste, die nach §2o gemessen wird — also unter
der Lehre, die dort gezogen wurde: **ein Befund auf Large Cap sagt nichts
darueber, ob er auf kleineren Titeln haelt.** Der Insider-Clusterkauf stand
auf 592 grossen Titeln bei +3,1 pp und auf 4.161 Titeln bei −0,0 pp.

Deshalb laeuft diese Messung von vornherein ueber das erweiterte Universum:
`panel=` nimmt die Beobachtungen aus `auswertung/kurspanel.py` entgegen, die
direkt aus den Kursreihen entstehen und keine Snapshots brauchen. Der Weg
ueber die Outcomes bleibt als Alternative bestehen, ist hier aber die engere
Messung.

**Warum diese Familie ueberhaupt.** `LITERATUR.md` §6.3 fuehrt sie als
staerksten Einzelkandidaten des Dokuments — und als einzige gepruefte
Familie, fuer die die Literatur ausdruecklich Robustheit ueber kleine UND
grosse Firmen berichtet. Sie ist damit die einzige, die die Groessenwarnung
aus §3 uebersteht.

**Das Vorzeichen: unten ist gut** — wie bei den Accruals (§2g), anders als
bei PEAD (§2e) und den Analystenrevisionen (§2f). Pontiff/Woodgate (2008)
erwarten, dass Firmen, die Aktien ausgeben, schlechter laufen als Firmen, die
zurueckkaufen. Traegt das Signal, liegt Quintil 1 (staerkste Rueckkaeufer)
ueber und Quintil 5 (staerkste Emittenten) unter der Marktquote.
`spread_pp` ist deshalb **Q1 minus Q5**, damit ein positiver Wert auch hier
„Hypothese bestaetigt" heisst und nicht je Modul etwas anderes.

**Die Vorabfrage aus §5** („warum scheitert es nicht an der
Jahresstabilitaet?") hat hier eine Antwort vor der Messung: das Vorzeichen
stammt nicht aus einem Marktregime, sondern aus einer
Unternehmensentscheidung. Emissionen haeufen sich in Hochphasen — der Effekt
beruht gerade darauf. Ob das reicht, entscheidet
`nettoemission_jahresstabilitaet`, nicht dieser Absatz.

**Der Querschnitt ist US-only**, wie §2f, §2g und §2n: Aktienzahlen aus der
SEC gibt es nur fuer SEC-Filer. Der deutsche Teil des Universums faellt unter
`MIN_QUERSCHNITT` und damit heraus.
"""

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from services.cross_sectional_momentum import raenge_je_woche
from services.nettoemission import nettoemission_je_ticker
from snapshot_engine.benchmark import benchmark_fuer, ueberrendite
from snapshot_engine.models import (
    AnalyseModus, AnalyseSnapshot, AnalyseSnapshotOutcome,
)
from snapshot_engine.auswertung.basis import (
    MIN_STICHPROBE, anteil_schlaegt_markt, mittlere_ueberrendite,
    zelle_gegen_markt, z_korrigiert,
)
from snapshot_engine.auswertung.holdout import (
    TRAIN, grenze_lesen, split_filter, split_zuordnen,
)
from snapshot_engine.auswertung.kursnaehe import kursnaehe_pruefen

logger = logging.getLogger(__name__)


QUANTILE = 5
MIN_QUERSCHNITT = 20

# Ab diesem Alter gilt eine Kennzahl als ueberholt. Zwei Jahre wie bei den
# Accruals: Raum fuer verspaetete Einreichungen, ohne dass ein Titel dauerhaft
# an einer Zahl von vor fuenf Jahren gemessen wird.
MAX_ALTER_TAGE = 730

# Sicherheitsabstand zwischen Bekanntwerden und Stichtag, in Kalendertagen —
# `bekannt_ab` traegt keine Uhrzeit, also gilt der Tag der Einreichung selbst
# noch nicht als bekannt. Dieselbe Regel wie in `services/pead.py`.
MIN_ABSTAND_TAGE = 1


def quintil(rang: Optional[float]) -> Optional[int]:
    """Quintil 1-5 zu einem Perzentilrang.

    1 ist die NIEDRIGSTE Nettoemission — die staerksten Rueckkaeufer, und
    nach Pontiff/Woodgate die besseren Titel. Wie bei den Accruals ist hier
    unten gut.
    """
    if rang is None:
        return None
    return min(QUANTILE, int(rang // (100.0 / QUANTILE)) + 1)


def letzte_kennzahl_vor(reihe, zeitpunkt):
    """Die zuletzt oeffentlich gewesene Nettoemission vor einem Stichtag.

    Args:
        reihe: nach `bekannt_ab` sortierte [(zeitpunkt, wert)] eines Tickers.

    Returns:
        (bekannt_ab, wert) oder None, wenn nichts Gueltiges vorliegt.

    Zwei Grenzen, beide bewusst: `MIN_ABSTAND_TAGE` haelt den
    Einreichungstag selbst noch draussen, `MAX_ALTER_TAGE` wirft eine
    Kennzahl weg, die zu alt ist, um noch etwas ueber die Firma zu sagen.
    """
    if not reihe:
        return None
    grenze = zeitpunkt - timedelta(days=MIN_ABSTAND_TAGE)
    treffer = None
    for bekannt_ab, wert in reihe:
        if bekannt_ab > grenze:
            break
        treffer = (bekannt_ab, wert)
    if treffer is None:
        return None
    if (zeitpunkt - treffer[0]).days > MAX_ALTER_TAGE:
        return None
    return treffer


# ---------------------------------------------------------------------------
# Zuordnung und Raenge
# ---------------------------------------------------------------------------

def _werte_zu_zuordnung(db: Session, zuordnung: dict[int, tuple]
                        ) -> tuple[dict[int, float], dict[int, tuple]]:
    """Je Beobachtung die zuletzt oeffentlich gewesene Nettoemission.

    `zuordnung` ist {id: (ticker, zeitpunkt)} — dieselbe Form, die das
    Kurspanel und die Snapshot-Abfrage liefern, damit es nur einen Codepfad
    gibt.
    """
    reihen = nettoemission_je_ticker(db)
    logger.info("Nettoemission: Kennzahlen fuer %d Ticker geladen.", len(reihen))

    werte: dict[int, float] = {}
    behalten: dict[int, tuple] = {}
    ohne = 0
    for beobachtung_id, (ticker, zeitpunkt) in zuordnung.items():
        treffer = letzte_kennzahl_vor(reihen.get(ticker), zeitpunkt)
        if treffer is None:
            ohne += 1
            continue
        werte[beobachtung_id] = treffer[1]
        behalten[beobachtung_id] = (ticker, zeitpunkt)

    logger.info("Nettoemission: %d Beobachtungen mit gueltiger Kennzahl "
                "(max. %d Tage alt), %d ohne.", len(werte), MAX_ALTER_TAGE, ohne)
    return werte, behalten


def _werte_je_snapshot(db: Session, datenmodus: str
                       ) -> tuple[dict[int, float], dict[int, tuple]]:
    """Dasselbe ueber die Snapshots statt ueber das Kurspanel."""
    snapshots = (
        db.query(AnalyseSnapshot.id, AnalyseSnapshot.ticker,
                 AnalyseSnapshot.snapshot_zeitpunkt)
        .filter(AnalyseSnapshot.datenmodus == datenmodus)
        .filter(AnalyseSnapshot.analyse_modus == AnalyseModus.NEUE_POSITION)
        .all()
    )
    zuordnung = {s_id: (ticker, zeitpunkt)
                 for s_id, ticker, zeitpunkt in snapshots}
    return _werte_zu_zuordnung(db, zuordnung)


def nettoemission_raenge(werte: dict[int, float], zuordnung: dict[int, tuple],
                         minimum_querschnitt: int = MIN_QUERSCHNITT
                         ) -> dict[int, float]:
    """Perzentilrang der Nettoemission, je Kalenderwoche und Handelsplatz.

    Der Querschnitt ist noetig, weil die Kennzahl absolut wenig aussagt: eine
    Emission von zwei Prozent ist in einem Jahr viel und im naechsten wenig.
    Die Kalenderwoche als Eimer folgt `momentum.py` und `accruals.py`;
    gegenueber einer Groesse, die sich nur jaehrlich aendert, ist sie fein
    genug.

    Die Trennung nach Handelsplatz ist dieselbe Entscheidung wie in
    `benchmark.py`: eine gemeinsame Rangliste ueber Xetra und US wiese
    Waehrungs- und Marktunterschiede als Emissionsverhalten aus.

    Die Eimerlogik selbst steht seit der Groessentrennung in
    `cross_sectional_momentum.raenge_je_woche` — die Groessenklassen brauchen
    exakt dieselbe, und zwei Kopien hiessen, dass eine spaetere Korrektur nur
    in einer davon ankommt.
    """
    raenge = raenge_je_woche(werte, zuordnung, benchmark_fuer,
                             minimum_querschnitt)
    logger.info("Nettoemission: %d Beobachtungen gerangt.", len(raenge))
    return raenge


def _beobachtungen(db: Session, horizont: int, datenmodus: str,
                   teil: Optional[str]) -> list[tuple]:
    """(id, rendite, benchmark_rendite) aus den Outcomes."""
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


def _vorbereiten(db: Session, horizont: int, datenmodus: str,
                 teil: Optional[str], panel: Optional[list],
                 mit_kursnaehe: bool):
    """Gemeinsamer Kopf von Auswertung und Jahrespruefung.

    Beide brauchen dieselben drei Dinge (Werte, Raenge, Beobachtungen) und
    dieselbe Holdout-Behandlung. Sie zweimal zu schreiben hiesse, dass eine
    spaetere Korrektur nur an einer Stelle ankommt.
    """
    if panel is not None:
        from snapshot_engine.auswertung.kurspanel import als_auswertungsform
        panel_zuordnung, panel_zeilen = als_auswertungsform(panel)
        werte, zuordnung = _werte_zu_zuordnung(db, panel_zuordnung)
        # Die Holdout-Trennung greift auf diesem Weg ueber den Stichtag, nicht
        # ueber die Query. Ohne sie liefe die Messung ueber den gesamten
        # Bestand und verbrauchte den Holdout stillschweigend — der teuerste
        # denkbare Fehler hier, weil er nicht ruecknehmbar ist.
        grenze = grenze_lesen()
        if teil:
            panel_zeilen = [
                z for z in panel_zeilen
                if z[0] in zuordnung
                and split_zuordnen(zuordnung[z[0]][1], grenze) == teil
            ]
        beobachtungen = panel_zeilen
        # Die Kursnaehe-Pruefung liest Snapshot-Kurse, die es hier nicht gibt.
        # Ausdruecklich auf None, nicht weggelassen: sonst ginge ein
        # umetikettiertes Kurssignal ungeprueft durch (§2f).
        mit_kursnaehe = False
    else:
        werte, zuordnung = _werte_je_snapshot(db, datenmodus)
        beobachtungen = _beobachtungen(db, horizont, datenmodus, teil)

    raenge = nettoemission_raenge(werte, zuordnung)
    return werte, zuordnung, raenge, beobachtungen, mit_kursnaehe


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

def nettoemission_auswerten(db: Session, horizont: int = 90,
                            datenmodus: str = "HISTORISCH",
                            teil: Optional[str] = TRAIN,
                            minimum: int = MIN_STICHPROBE,
                            mit_kursnaehe: bool = True,
                            panel: Optional[list] = None,
                            z_tests: Optional[int] = None) -> dict:
    """Quintile der Nettoemission gegen den Markt.

    Args:
        panel: Beobachtungen aus `auswertung/kurspanel.py` statt aus den
            Outcomes. Damit laeuft die Messung auf dem erweiterten Universum.
        z_tests: Anzahl Zellen fuer die Sidak-Korrektur. Ueber mehrere
            Horizonte hinweg muss sie ueber ALLE Zellen des Laufs gehen,
            nicht je Horizont — sonst ist sie zu mild.

    Returns:
        {"basis_markt", "basis_ertrag", "n_gesamt", "quintile", "spread_pp",
         "ertrag_spread_pp", "z_korrigiert", "kursnaehe", "zaehlwerk",
         "teil", "horizont_tage"}

    `spread_pp` ist **Q1 minus Q5** — Rueckkaeufer minus Emittenten. Positiv
    heisst: die Hypothese von Pontiff/Woodgate bestaetigt sich.
    """
    werte, zuordnung, raenge, beobachtungen, mit_kursnaehe = _vorbereiten(
        db, horizont, datenmodus, teil, panel, mit_kursnaehe)

    zaehlwerk = {"zeilen": 0, "ohne_kennzahl": 0, "ohne_rang": 0, "verwertet": 0}
    gruppen: dict[int, list[tuple]] = defaultdict(list)
    alle: list[Optional[float]] = []

    for beobachtung_id, ret, benchmark in beobachtungen:
        zaehlwerk["zeilen"] += 1
        if beobachtung_id not in werte:
            zaehlwerk["ohne_kennzahl"] += 1
            continue
        q = quintil(raenge.get(beobachtung_id))
        if q is None:
            zaehlwerk["ohne_rang"] += 1
            continue
        zaehlwerk["verwertet"] += 1
        u = ueberrendite(ret, benchmark)
        alle.append(u)
        gruppen[q].append((ret, u))

    logger.info("Nettoemission: %d Zeilen, %d verwertet, %d ohne Rang.",
                zaehlwerk["zeilen"], zaehlwerk["verwertet"],
                zaehlwerk["ohne_rang"])

    ergebnis: dict = {"basis_markt": None, "basis_ertrag": None,
                      "n_gesamt": 0, "quintile": [], "spread_pp": None,
                      "ertrag_spread_pp": None, "z_korrigiert": None,
                      "kursnaehe": None, "zaehlwerk": zaehlwerk, "teil": teil,
                      "horizont_tage": horizont}
    if not gruppen:
        return ergebnis

    basis_markt = anteil_schlaegt_markt(alle)
    basis_ertrag = mittlere_ueberrendite(alle)
    z = z_korrigiert(z_tests if z_tests else len(gruppen))
    zeilen = [
        {"quintil": q, "horizont_tage": horizont, "teil": teil,
         **zelle_gegen_markt([r for r, _ in gruppen[q]],
                             [u for _, u in gruppen[q]],
                             basis_markt, horizont, minimum=minimum, z=z,
                             basis_ertrag=basis_ertrag)}
        for q in sorted(gruppen)
    ]

    ergebnis.update({
        "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
        "basis_ertrag": round(basis_ertrag, 3) if basis_ertrag is not None else None,
        "n_gesamt": sum(len(v) for v in gruppen.values()),
        "quintile": zeilen,
        "spread_pp": _spread(zeilen, "markt_trefferquote"),
        "ertrag_spread_pp": _spread(zeilen, "ueberrendite_vorsprung_pp", 2),
        "z_korrigiert": round(z, 2),
    })

    if mit_kursnaehe:
        # Auf den Raengen, nicht auf den Rohwerten — gefragt ist die Naehe
        # dessen, was tatsaechlich gemessen wurde (§2f/§2g).
        ergebnis["kursnaehe"] = kursnaehe_pruefen(
            db, raenge, zuordnung, datenmodus=datenmodus)

    return ergebnis


# ---------------------------------------------------------------------------
# Groessentrennung — die erste der beiden Gegenproben aus §2p
# ---------------------------------------------------------------------------

def nettoemission_nach_groesse(db: Session, horizont: int = 90,
                               datenmodus: str = "HISTORISCH",
                               teil: Optional[str] = TRAIN,
                               panel: Optional[list] = None,
                               klassen: int = 5,
                               minimum: int = MIN_STICHPROBE,
                               z_tests: Optional[int] = None,
                               fenster: Optional[int] = None) -> dict:
    """Traegt die Nettoemission noch etwas INNERHALB einer Groessenklasse?

    Die wichtigste offene Gegenprobe zu §2p. Emittenten sind systematisch
    kleinere Titel; solange alles gegen die gepoolte Marktbasis laeuft, kann
    der gesamte Befund ein Groesseneffekt in anderer Verpackung sein. §2d hat
    fuer die Sektoren gezeigt, wie gross dieser Unterschied wird (Spannweite
    6,6 pp bei ±1,4 pp Fehlerspanne), und §2o hat gezeigt, was eine Gegenprobe
    vor dem Holdout-Zugriff wert ist.

    **Die Bauform ist die abhaengige Doppelsortierung.** Zuerst werden die
    Beobachtungen in Groessenklassen geschnitten (`auswertung/groesse.py`,
    Dollar-Umsatz, split-immun). Dann wird die Nettoemission **innerhalb jeder
    Klasse neu gerangt**, und jede Schicht bekommt **ihre eigene Marktbasis**.

    Die Neuberangung ist der Unterschied zu `handbuch.bedingt()`, das die
    globalen Raenge beibehaelt. Hier ist sie noetig: laufen Emission und Groesse
    stark zusammen, besteht die kleinste Klasse fast nur aus Q5 und die
    groesste fast nur aus Q1 — die Schichten waeren entartet und die Frage
    bliebe unbeantwortet. Nach der Neuberangung fragt jede Schicht das, worauf
    es ankommt: **trennt die Emission noch, wenn alle Verglichenen gleich gross
    sind?**

    Die eigene Marktbasis je Schicht folgt derselben Regel wie in
    `jahresstabilitaet` und `handbuch.bedingt`: die Grundgesamtheit kleiner
    Titel schlaegt ihren Index anders oft als die Gesamtheit, und wer gegen
    eine gemeinsame Basis rechnet, misst genau diesen Unterschied.

    Args:
        klassen: Zahl der Groessenschichten (5 = Quintile).
        z_tests: Zellen fuer die Sidak-Korrektur ueber den GANZEN Lauf. Hier
            sind es `klassen * 5` je Horizont — deutlich mehr als bei der
            gepoolten Messung, und wer das nicht mitzaehlt, macht die Korrektur
            zu mild.
        fenster: Rueckblick des Umsatzmittels in Handelstagen.

    Returns:
        {"schichten": [...], "rangkorrelation", "schichten_mit_vorsprung",
         "schichten_gesamt", "basis_je_schicht", "zaehlwerk", "teil",
         "horizont_tage"}

        Jede Schicht traegt `klasse`, `n`, `basis_markt`, `basis_ertrag`,
        `spread_pp`, `ertrag_spread_pp` und die volle `quintile`-Tabelle in
        derselben Form wie `nettoemission_auswerten` — damit die Ausgabe
        dieselbe Tabellenfunktion benutzen kann.

    **Wie das Ergebnis zu lesen ist.** Haelt der Spread in allen Schichten im
    Vorzeichen und in aehnlicher Groesse, ist die Nettoemission etwas Eigenes.
    Verschwindet er in den grossen Klassen und sitzt nur in der kleinsten, war
    §2p ein Groesseneffekt — dann ist der Befund als Handelsaussage tot und
    bestenfalls ein Filter fuer Nebenwerte. Bricht er ueberall zusammen, ist
    §2p falsifiziert wie §2n durch §2o.
    """
    from snapshot_engine.auswertung.groesse import FENSTER_TAGE, groessen_klassen
    from snapshot_engine.auswertung.kursnaehe import rangkorrelation

    werte, zuordnung, _, beobachtungen, _ = _vorbereiten(
        db, horizont, datenmodus, teil, panel, mit_kursnaehe=False)

    klasse_je_id, umsatz = groessen_klassen(
        db, zuordnung, benchmark_fuer, klassen=klassen,
        fenster=fenster if fenster is not None else FENSTER_TAGE)

    # Wie stark laufen die beiden Groessen ueberhaupt zusammen? Dieselbe
    # Pruefung, die §2f zur stehenden Regel gemacht hat, nur gegen die Groesse
    # statt gegen den Kurs. Eine Korrelation nahe null hiesse: der Einwand war
    # gegenstandslos. Nahe −1 hiesse: die Messung misst ueberwiegend Groesse.
    gemeinsam = sorted(set(werte) & set(umsatz))
    korrelation = rangkorrelation([werte[i] for i in gemeinsam],
                                  [umsatz[i] for i in gemeinsam])

    zaehlwerk = {"zeilen": 0, "ohne_kennzahl": 0, "ohne_klasse": 0,
                 "verwertet": 0}
    je_klasse: dict[int, list[tuple]] = defaultdict(list)
    for beobachtung_id, ret, benchmark in beobachtungen:
        zaehlwerk["zeilen"] += 1
        if beobachtung_id not in werte:
            zaehlwerk["ohne_kennzahl"] += 1
            continue
        k = klasse_je_id.get(beobachtung_id)
        if k is None:
            zaehlwerk["ohne_klasse"] += 1
            continue
        je_klasse[k].append((beobachtung_id, ret, benchmark))

    z = z_korrigiert(z_tests if z_tests else klassen * QUANTILE)
    schichten: list[dict] = []

    for k in sorted(je_klasse):
        zeilen_der_schicht = je_klasse[k]
        ids = {b_id for b_id, _, _ in zeilen_der_schicht}

        # Neu rangen — nur gegen die Titel DERSELBEN Groessenklasse.
        raenge_k = nettoemission_raenge(
            {i: werte[i] for i in ids},
            {i: zuordnung[i] for i in ids})

        gruppen: dict[int, list[tuple]] = defaultdict(list)
        alle: list[Optional[float]] = []
        for beobachtung_id, ret, benchmark in zeilen_der_schicht:
            q = quintil(raenge_k.get(beobachtung_id))
            if q is None:
                continue
            zaehlwerk["verwertet"] += 1
            u = ueberrendite(ret, benchmark)
            alle.append(u)
            gruppen[q].append((ret, u))

        if not gruppen:
            continue

        basis_markt = anteil_schlaegt_markt(alle)
        basis_ertrag = mittlere_ueberrendite(alle)
        quintil_zeilen = [
            {"quintil": q, "horizont_tage": horizont, "teil": teil,
             **zelle_gegen_markt([r for r, _ in gruppen[q]],
                                 [u for _, u in gruppen[q]],
                                 basis_markt, horizont, minimum=minimum, z=z,
                                 basis_ertrag=basis_ertrag)}
            for q in sorted(gruppen)
        ]

        schichten.append({
            "klasse": k,
            "n": sum(len(v) for v in gruppen.values()),
            "umsatz_median": _median([umsatz[i] for i in ids if i in umsatz]),
            "basis_markt": round(basis_markt, 1) if basis_markt is not None else None,
            "basis_ertrag": round(basis_ertrag, 3) if basis_ertrag is not None else None,
            "quintile": quintil_zeilen,
            "spread_pp": _spread(quintil_zeilen, "markt_trefferquote"),
            "ertrag_spread_pp": _spread(quintil_zeilen,
                                        "ueberrendite_vorsprung_pp", 2),
        })

    mit_vorsprung = sum(1 for s in schichten
                        if s["spread_pp"] is not None and s["spread_pp"] > 0)

    logger.info("Nettoemission nach Groesse: %d Schichten, %d mit positivem "
                "Spread, Rangkorrelation %s.",
                len(schichten), mit_vorsprung, korrelation)

    return {
        "schichten": schichten,
        "schichten_gesamt": len(schichten),
        "schichten_mit_vorsprung": mit_vorsprung,
        "rangkorrelation": korrelation,
        "basis_je_schicht": {s["klasse"]: s["basis_markt"] for s in schichten},
        "z_korrigiert": round(z, 2),
        "zaehlwerk": zaehlwerk,
        "teil": teil,
        "horizont_tage": horizont,
    }


def _median(werte: list[float]) -> Optional[float]:
    """Median ohne numpy — nur fuer die Ausgabe, nicht fuer eine Aussage."""
    if not werte:
        return None
    sortiert = sorted(werte)
    mitte = len(sortiert) // 2
    if len(sortiert) % 2:
        return sortiert[mitte]
    return (sortiert[mitte - 1] + sortiert[mitte]) / 2


def nettoemission_jahresstabilitaet(db: Session, horizont: int = 90,
                                    datenmodus: str = "HISTORISCH",
                                    teil: Optional[str] = TRAIN,
                                    panel: Optional[list] = None) -> dict:
    """Spread Q1-Q5 je Kalenderjahr — der Filter, an dem neun Familien starben.

    Die Binomialtafel aus §2j gehoert an jede Lesung dieser Zahl:
    6 von 9 -> p = 0,51 · 7 von 9 -> p = 0,18 · 8 von 9 -> p = 0,039 ·
    9 von 9 -> p = 0,004. Ein „7 von 9" ist keine Bestaetigung.
    """
    werte, zuordnung, raenge, beobachtungen, _ = _vorbereiten(
        db, horizont, datenmodus, teil, panel, False)

    je_jahr: dict[int, dict[int, list[tuple]]] = defaultdict(
        lambda: defaultdict(list))
    alle_je_jahr: dict[int, list[Optional[float]]] = defaultdict(list)

    for beobachtung_id, ret, benchmark in beobachtungen:
        if beobachtung_id not in werte or beobachtung_id not in zuordnung:
            continue
        q = quintil(raenge.get(beobachtung_id))
        if q is None:
            continue
        jahr = zuordnung[beobachtung_id][1].year
        u = ueberrendite(ret, benchmark)
        alle_je_jahr[jahr].append(u)
        je_jahr[jahr][q].append((ret, u))

    zeilen = []
    for jahr in sorted(je_jahr):
        gruppen = je_jahr[jahr]
        if 1 not in gruppen or QUANTILE not in gruppen:
            continue
        # Die Basis je Jahr, nicht gepoolt: die Marktquote schwankt zwischen
        # den Jahren um mehr als jeder je gemessene Signalvorsprung (§2i).
        basis = anteil_schlaegt_markt(alle_je_jahr[jahr])
        basis_ertrag = mittlere_ueberrendite(alle_je_jahr[jahr])
        if basis is None:
            continue

        q1 = zelle_gegen_markt([r for r, _ in gruppen[1]],
                               [u for _, u in gruppen[1]], basis, horizont,
                               basis_ertrag=basis_ertrag)
        q5 = zelle_gegen_markt([r for r, _ in gruppen[QUANTILE]],
                               [u for _, u in gruppen[QUANTILE]], basis,
                               horizont, basis_ertrag=basis_ertrag)
        if q1.get("markt_trefferquote") is None or q5.get("markt_trefferquote") is None:
            continue

        zeilen.append({
            "jahr": jahr,
            "n": len(gruppen[1]) + len(gruppen[QUANTILE]),
            "spread_pp": round(q1["markt_trefferquote"] - q5["markt_trefferquote"], 1),
            "ertrag_spread_pp": (
                None if q1.get("ueberrendite_vorsprung_pp") is None
                or q5.get("ueberrendite_vorsprung_pp") is None
                else round(q1["ueberrendite_vorsprung_pp"]
                           - q5["ueberrendite_vorsprung_pp"], 2)),
        })

    def _gleich(schluessel: str) -> tuple[int, int]:
        werte_ = [z[schluessel] for z in zeilen if z.get(schluessel) is not None]
        if not werte_:
            return 0, 0
        positiv = sum(1 for w in werte_ if w > 0)
        return max(positiv, len(werte_) - positiv), len(werte_)

    vorzeichen, gesamt = _gleich("spread_pp")
    ertrag_vorzeichen, ertrag_gesamt = _gleich("ertrag_spread_pp")

    return {"jahre": zeilen, "vorzeichen_gleich": vorzeichen,
            "jahre_gesamt": gesamt,
            "ertrag_vorzeichen_gleich": ertrag_vorzeichen,
            "ertrag_jahre_gesamt": ertrag_gesamt,
            "horizont_tage": horizont, "teil": teil}


def _spread(zeilen: list[dict], schluessel: str,
            stellen: int = 1) -> Optional[float]:
    """Q1 minus Q5 — Rueckkaeufer minus Emittenten.

    **Umgekehrt zu PEAD und den Revisionen**, und zwar absichtlich: so heisst
    ein positiver Wert auch hier „die Hypothese bestaetigt sich". Die
    Alternative waere ein Spread, dessen Vorzeichen je Modul etwas anderes
    bedeutet — genau die Fussangel, die einen Befund spaeter falsch zitiert
    werden laesst.
    """
    je_quintil = {z["quintil"]: z.get(schluessel) for z in zeilen}
    niedrig, hoch = je_quintil.get(1), je_quintil.get(QUANTILE)
    if niedrig is None or hoch is None:
        return None
    return round(niedrig - hoch, stellen)
