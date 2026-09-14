"""
services/sec_fundamentals.py — Die SEC-Bestaende je Titel, fuer die Anzeige.

**Wozu.** Das Projekt haelt fuenf SEC-gespeiste Bestaende — Nettoemission,
Accruals, Earnings, Analystenrevisionen, Insidergeschaefte — mit zusammen
mehreren hunderttausend Zeilen. Bis hierher hat sie **kein einziger Router und
kein Template gelesen**: sie existierten ausschliesslich fuer die
Forschungspipeline unter `snapshot_engine/auswertung/`. Dieses Modul macht sie
im Dashboard sichtbar.

**Die Bruecke ueber `services/ticker_zuordnung.py`.** Die Bestaende liegen
unter US-Tickern, das Dashboard fuehrt Frankfurter Notierungen. Ohne die
Zuordnung waere ABEA.DE hier leer, obwohl unter GOOG 11 Nettoemissions-
kennzahlen und 9.276 Insidergeschaefte liegen.

**Was dieses Modul ausdruecklich NICHT tut: bewerten.** Es liefert Zahlen und
ihre Herkunft, keine Empfehlung und keinen Score-Beitrag. Das ist keine
Bequemlichkeit, sondern die Trennlinie aus CONTEXT.md §7: in den Score geht
nur, was belegt ist, und diese Frage ist fuer die Nettoemission zum Zeitpunkt
dieses Moduls **offen** (§2r/§2s: das Vorzeichen haelt in allen zehn Dezilen,
eine Grenze gibt es nicht, der Holdout ist unangetastet). Eine Anzeige darf
den Bestand zeigen, ohne dass daraus eine Handlungsaussage wird — sie darf nur
nicht so tun, als waere die Frage entschieden.

Deshalb traegt jede Kennzahl hier ihre **Einordnung als Text**, nicht als
Ampel: „Rueckkauf" und „Emission" sind Beschreibungen dessen, was die Firma
getan hat. Ob das ein Kaufgrund ist, steht hier nicht.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database import (
    AccrualKennzahl, AnalystenRevision, EarningsEvent, InsiderGeschaeft,
    NettoemissionKennzahl,
)

logger = logging.getLogger(__name__)


# Wie viele Einzelposten je Abschnitt hoechstens angezeigt werden. Die Tabelle
# soll lesbar bleiben; wer mehr will, bekommt es ueber die Auswertungsseiten.
MAX_ZEILEN = 8

# Fenster fuer die Insider-Zusammenfassung. Zwoelf Monate, weil die Literatur
# (Cohen/Malloy/Pomorski) Routinegeschaefte ueber den Jahreszyklus trennt.
INSIDER_FENSTER_TAGE = 365

# Form-4-Transaktionscodes. P = offener Markt Kauf, S = offener Markt Verkauf.
# Alles andere (Zuteilungen, Optionsausuebungen, Schenkungen) ist fuer die
# Frage "hat jemand mit eigenem Geld gekauft" ohne Aussage und wird getrennt
# gezaehlt statt stillschweigend eingemischt.
CODE_KAUF = "P"
CODE_VERKAUF = "S"


def _nettoemission(db: Session, ticker: str) -> Optional[dict]:
    """Die zuletzt oeffentlich gewesene Nettoemission.

    `nettoemission` ist ln(Aktienzahl / Aktienzahl im Vorjahr): negativ heisst
    Rueckkauf, positiv heisst Emission. Angezeigt wird zusaetzlich die
    Veraenderung in Prozent, weil ein Logarithmus sich schlecht liest.
    """
    zeile = (
        db.query(NettoemissionKennzahl)
        .filter(NettoemissionKennzahl.ticker == ticker)
        .filter(NettoemissionKennzahl.nettoemission.isnot(None))
        .order_by(NettoemissionKennzahl.bekannt_ab.desc())
        .first()
    )
    if zeile is None or zeile.nettoemission is None:
        return None

    import math
    wert = float(zeile.nettoemission)
    return {
        "wert": wert,
        "prozent": (math.exp(wert) - 1) * 100,
        "richtung": "Rueckkauf" if wert < 0 else ("Emission" if wert > 0
                                                  else "unveraendert"),
        "aktien": zeile.aktien,
        "aktien_vorjahr": zeile.aktien_vorjahr,
        "periode_ende": zeile.periode_ende,
        "bekannt_ab": zeile.bekannt_ab,
        "accession": zeile.accession,
    }


def _accruals(db: Session, ticker: str) -> Optional[dict]:
    """Periodenabgrenzungen nach Sloan: (Gewinn − operativer Cashflow) / Bilanzsumme.

    Hoch heisst: der ausgewiesene Gewinn ist zu einem grossen Teil Buchhaltung
    und nicht Zahlung. Die Messung des Projekts (§2g) fand darin **keinen**
    Vorsprung — die Zahl steht hier als Bilanzeigenschaft, nicht als Signal.
    """
    zeile = (
        db.query(AccrualKennzahl)
        .filter(AccrualKennzahl.ticker == ticker)
        .filter(AccrualKennzahl.accrual.isnot(None))
        .order_by(AccrualKennzahl.bekannt_ab.desc())
        .first()
    )
    if zeile is None or zeile.accrual is None:
        return None
    return {
        "wert": float(zeile.accrual),
        "netto_gewinn": zeile.netto_gewinn,
        "operativer_cashflow": zeile.operativer_cashflow,
        "bilanzsumme": zeile.bilanzsumme,
        "periode_ende": zeile.periode_ende,
        "bekannt_ab": zeile.bekannt_ab,
    }


def _earnings(db: Session, ticker: str, grenze: int = MAX_ZEILEN) -> list[dict]:
    """Die juengsten Quartalszahlen mit ihrer Ueberraschung."""
    zeilen = (
        db.query(EarningsEvent)
        .filter(EarningsEvent.ticker == ticker)
        .order_by(EarningsEvent.datum.desc())
        .limit(grenze)
        .all()
    )
    return [{
        "datum": z.datum,
        "eps_actual": z.eps_actual,
        "eps_estimate": z.eps_estimate,
        "surprise_pct": z.surprise_pct,
    } for z in zeilen]


def _revisionen(db: Session, ticker: str, grenze: int = MAX_ZEILEN) -> list[dict]:
    """Die juengsten Analystenhandlungen.

    §2f hat gemessen, dass die Zielrevision zu 0,47 mit der Vorrendite
    korreliert — Analysten folgen dem Kurs. Deshalb steht die Kursrendite
    dieser Zahl im Template als Warnung daneben und nicht als Bestaetigung.
    """
    zeilen = (
        db.query(AnalystenRevision)
        .filter(AnalystenRevision.ticker == ticker)
        .order_by(AnalystenRevision.datum.desc())
        .limit(grenze)
        .all()
    )
    return [{
        "datum": z.datum,
        "firma": z.firma,
        "aktion": z.aktion,
        "ziel_aktion": z.ziel_aktion,
        "note_alt": z.note_alt,
        "note_neu": z.note_neu,
        "ziel_alt": z.ziel_alt,
        "ziel_neu": z.ziel_neu,
    } for z in zeilen]


def _insider(db: Session, ticker: str, grenze: int = MAX_ZEILEN,
             fenster_tage: int = INSIDER_FENSTER_TAGE,
             heute: Optional[datetime] = None) -> dict:
    """Insidergeschaefte: Zusammenfassung ueber das Fenster plus die juengsten.

    **Nur die Codes P und S gehen in die Summen.** Eine Aktienzuteilung (A),
    eine Optionsausuebung (M) oder eine Schenkung (G) ist kein Kauf mit
    eigenem Geld, und wer sie mitzaehlt, liest Verguetung als Ueberzeugung.
    Die uebrigen Codes werden gezaehlt, aber getrennt ausgewiesen.
    """
    heute = heute or datetime.now()
    seit = heute - timedelta(days=fenster_tage)

    zeilen = (
        db.query(InsiderGeschaeft)
        .filter(InsiderGeschaeft.ticker == ticker)
        .filter(InsiderGeschaeft.trans_datum >= seit)
        .all()
    )

    kauf_wert = verkauf_wert = 0.0
    kauf_n = verkauf_n = sonstige_n = 0
    for z in zeilen:
        wert = float(z.wert or 0)
        if z.code == CODE_KAUF:
            kauf_n += 1
            kauf_wert += wert
        elif z.code == CODE_VERKAUF:
            verkauf_n += 1
            verkauf_wert += wert
        else:
            sonstige_n += 1

    juengste = (
        db.query(InsiderGeschaeft)
        .filter(InsiderGeschaeft.ticker == ticker)
        .filter(InsiderGeschaeft.code.in_([CODE_KAUF, CODE_VERKAUF]))
        .order_by(InsiderGeschaeft.trans_datum.desc())
        .limit(grenze)
        .all()
    )

    return {
        "fenster_tage": fenster_tage,
        "kauf_n": kauf_n,
        "verkauf_n": verkauf_n,
        "sonstige_n": sonstige_n,
        "kauf_wert": kauf_wert,
        "verkauf_wert": verkauf_wert,
        "netto_wert": kauf_wert - verkauf_wert,
        "zeilen": [{
            "datum": z.trans_datum,
            "bekannt_ab": z.bekannt_ab,
            "name": z.owner_name,
            "beziehung": z.beziehung,
            "code": z.code,
            "stueck": z.stueck,
            "kurs": z.kurs,
            "wert": z.wert,
            "plan_10b5_1": z.plan_10b5_1,
        } for z in juengste],
    }


def sec_fundamentaldaten(db: Session, notierung: str,
                         grenze: int = MAX_ZEILEN) -> dict:
    """Alles, was zu einer Notierung aus SEC-Quellen im Bestand liegt.

    Args:
        notierung: Der Ticker, wie ihn das Dashboard fuehrt — "AMZN" ebenso
            wie "ABEA.DE".

    Returns:
        {"notierung", "us_ticker", "zuordnung", "hat_daten", "nettoemission",
         "accruals", "earnings", "revisionen", "insider"}

        `us_ticker` ist None, wenn keine Zuordnung besteht; dann sind alle
        Abschnitte leer und `zuordnung` traegt die Begruendung. Das ist der
        Normalfall fuer einen deutschen Titel wie ALV.DE und ausdruecklich
        kein Fehler.
    """
    from services.ticker_zuordnung import us_ticker_fuer, zuordnung_lesen

    us_ticker = us_ticker_fuer(db, notierung)
    zeile = zuordnung_lesen(db, notierung)

    ergebnis: dict = {
        "notierung": notierung,
        "us_ticker": us_ticker,
        "zuordnung": zeile.to_dict() if zeile else None,
        "hat_daten": False,
        "nettoemission": None,
        "accruals": None,
        "earnings": [],
        "revisionen": [],
        "insider": None,
    }

    if not us_ticker:
        return ergebnis

    ergebnis.update({
        "nettoemission": _nettoemission(db, us_ticker),
        "accruals": _accruals(db, us_ticker),
        "earnings": _earnings(db, us_ticker, grenze),
        "revisionen": _revisionen(db, us_ticker, grenze),
        "insider": _insider(db, us_ticker, grenze),
    })
    ergebnis["hat_daten"] = any([
        ergebnis["nettoemission"], ergebnis["accruals"],
        ergebnis["earnings"], ergebnis["revisionen"],
        ergebnis["insider"]["zeilen"] if ergebnis["insider"] else None,
    ])

    logger.debug("SEC-Fundamentaldaten %s (%s): Daten vorhanden = %s",
                 notierung, us_ticker, ergebnis["hat_daten"])
    return ergebnis
