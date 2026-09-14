"""
tests/test_sec_fundamentals.py — Die SEC-Bestaende fuer die Anzeige.

Diese Flaeche zeigt Zahlen, auf die eine Kaufentscheidung folgen kann. Drei
Sorten Fehler waeren teuer und alle drei still:

  * **Daten des falschen Unternehmens** — faengt `test_ticker_zuordnung.py`
    auf der Zuordnungsebene ab, hier wird geprueft, dass dieses Modul keine
    eigene Abkuerzung nimmt;
  * **Verguetung als Ueberzeugung gelesen** — eine Aktienzuteilung (Code A)
    oder Optionsausuebung (M) ist kein Insiderkauf. Wer sie mitzaehlt, dreht
    das Vorzeichen einer Zusammenfassung;
  * **eine veraltete Kennzahl als aktuelle ausgegeben** — es gilt die zuletzt
    oeffentlich gewesene, nicht die mit dem juengsten Geschaeftsjahr.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import (
    AccrualKennzahl, AnalystenRevision, Base, EarningsEvent, InsiderGeschaeft,
    NettoemissionKennzahl,
)
from services.sec_fundamentals import sec_fundamentaldaten
from services.ticker_zuordnung import manuell_setzen, zuordnung_speichern


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False,
                           expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


_laufnummer = iter(range(1, 10_000))


def _insider(db, ticker, code, wert, tage_her=10, stueck=100.0):
    """Ein Form-4-Geschaeft. `accession`/`sec_sk` sind NOT NULL und eindeutig."""
    n = next(_laufnummer)
    db.add(InsiderGeschaeft(
        ticker=ticker, code=code, wert=wert, stueck=stueck, kurs=10.0,
        accession=f"0000000000-00-{n:06d}", sec_sk=str(n),
        trans_datum=datetime.now() - timedelta(days=tage_her),
        bekannt_ab=datetime.now() - timedelta(days=tage_her - 1),
        owner_name="Muster", beziehung="CEO", quelle="test"))


# ---------------------------------------------------------------------------
# Die Bruecke wird benutzt, nicht umgangen
# ---------------------------------------------------------------------------

def test_ohne_zuordnung_bleibt_alles_leer(db):
    """Ein deutscher Titel ohne SEC-Emittent liefert ein Ergebnis, keinen Fehler."""
    db.add(NettoemissionKennzahl(
        ticker="ALV", periode_ende=datetime(2024, 12, 31),
        bekannt_ab=datetime(2025, 3, 1), nettoemission=-0.02, quelle="test"))
    db.commit()

    e = sec_fundamentaldaten(db, "ALV.DE")

    assert e["us_ticker"] is None
    assert e["hat_daten"] is False
    assert e["nettoemission"] is None
    # Die Daten von Autoliv (Ticker ALV) duerfen NICHT durchschlagen.
    assert e["earnings"] == []


def test_zuordnung_holt_die_daten_des_richtigen_emittenten(db):
    db.add(NettoemissionKennzahl(
        ticker="GOOG", periode_ende=datetime(2024, 12, 31),
        bekannt_ab=datetime(2025, 2, 1), nettoemission=-0.01,
        aktien=12_000_000_000, aktien_vorjahr=12_120_000_000, quelle="test"))
    db.commit()
    manuell_setzen(db, "ABEA.DE", "GOOG", cik="0001652044")

    e = sec_fundamentaldaten(db, "ABEA.DE")

    assert e["us_ticker"] == "GOOG"
    assert e["hat_daten"] is True
    assert e["nettoemission"]["richtung"] == "Rueckkauf"


def test_us_ticker_braucht_keine_zuordnung(db):
    db.add(NettoemissionKennzahl(
        ticker="AMZN", periode_ende=datetime(2024, 12, 31),
        bekannt_ab=datetime(2025, 2, 1), nettoemission=0.005,
        aktien=10_600_000_000, aktien_vorjahr=10_547_000_000, quelle="test"))
    db.commit()

    e = sec_fundamentaldaten(db, "AMZN")
    assert e["us_ticker"] == "AMZN"
    assert e["nettoemission"]["richtung"] == "Emission"


# ---------------------------------------------------------------------------
# Nettoemission
# ---------------------------------------------------------------------------

def test_die_zuletzt_oeffentliche_kennzahl_gewinnt(db):
    """Nicht die mit dem juengsten Geschaeftsjahr, sondern die zuletzt bekannte.

    Eine spaeter eingereichte Korrektur eines aelteren Jahres ist der aktuelle
    Wissensstand; ein frueher eingereichtes juengeres Jahr gibt es nicht.
    """
    db.add(NettoemissionKennzahl(
        ticker="AMZN", periode_ende=datetime(2023, 12, 31),
        bekannt_ab=datetime(2025, 6, 1), nettoemission=-0.09,
        aktien=1.0, aktien_vorjahr=1.0, quelle="test"))
    db.add(NettoemissionKennzahl(
        ticker="AMZN", periode_ende=datetime(2024, 12, 31),
        bekannt_ab=datetime(2025, 2, 1), nettoemission=0.01,
        aktien=1.0, aktien_vorjahr=1.0, quelle="test"))
    db.commit()

    e = sec_fundamentaldaten(db, "AMZN")
    assert e["nettoemission"]["wert"] == pytest.approx(-0.09)


def test_logarithmus_wird_in_prozent_uebersetzt(db):
    """ln(1,05) muss als +5 % ankommen, nicht als +0,0488."""
    import math
    db.add(NettoemissionKennzahl(
        ticker="AMZN", periode_ende=datetime(2024, 12, 31),
        bekannt_ab=datetime(2025, 2, 1), nettoemission=math.log(1.05),
        aktien=105.0, aktien_vorjahr=100.0, quelle="test"))
    db.commit()

    e = sec_fundamentaldaten(db, "AMZN")
    assert e["nettoemission"]["prozent"] == pytest.approx(5.0)
    assert e["nettoemission"]["richtung"] == "Emission"


def test_kennzahl_ohne_wert_zaehlt_nicht(db):
    db.add(NettoemissionKennzahl(
        ticker="AMZN", periode_ende=datetime(2024, 12, 31),
        bekannt_ab=datetime(2025, 2, 1), nettoemission=None, quelle="test"))
    db.commit()
    assert sec_fundamentaldaten(db, "AMZN")["nettoemission"] is None


# ---------------------------------------------------------------------------
# Insider — der gefaehrlichste Abschnitt
# ---------------------------------------------------------------------------

def test_nur_offener_markt_zaehlt_in_die_summen(db):
    """Zuteilungen und Optionsausuebungen sind kein Kauf mit eigenem Geld."""
    _insider(db, "AMZN", "P", 100_000)       # echter Kauf
    _insider(db, "AMZN", "S", 40_000)        # echter Verkauf
    _insider(db, "AMZN", "A", 5_000_000)     # Zuteilung
    _insider(db, "AMZN", "M", 3_000_000)     # Optionsausuebung
    _insider(db, "AMZN", "G", 1_000_000)     # Schenkung
    db.commit()

    ins = sec_fundamentaldaten(db, "AMZN")["insider"]

    assert ins["kauf_n"] == 1
    assert ins["verkauf_n"] == 1
    assert ins["sonstige_n"] == 3
    assert ins["kauf_wert"] == pytest.approx(100_000)
    assert ins["verkauf_wert"] == pytest.approx(40_000)
    # Ohne die Trennung waere das Netto hier +9,06 Mio statt +60.000.
    assert ins["netto_wert"] == pytest.approx(60_000)


def test_die_tabelle_zeigt_nur_kauf_und_verkauf(db):
    _insider(db, "AMZN", "A", 5_000_000)
    _insider(db, "AMZN", "P", 100_000)
    db.commit()

    ins = sec_fundamentaldaten(db, "AMZN")["insider"]
    assert len(ins["zeilen"]) == 1
    assert ins["zeilen"][0]["code"] == "P"


def test_geschaefte_ausserhalb_des_fensters_zaehlen_nicht(db):
    _insider(db, "AMZN", "P", 100_000, tage_her=400)
    db.commit()

    ins = sec_fundamentaldaten(db, "AMZN")["insider"]
    assert ins["kauf_n"] == 0
    # In der Liste der juengsten steht es trotzdem — sie ist nicht
    # fensterbegrenzt, sondern zeigt die letzten bekannten Geschaefte.
    assert len(ins["zeilen"]) == 1


def test_fehlender_wert_kippt_die_summe_nicht(db):
    db.add(InsiderGeschaeft(
        ticker="AMZN", code="P", wert=None, stueck=100.0,
        accession="0000000000-00-999999", sec_sk="999999",
        trans_datum=datetime.now() - timedelta(days=5),
        bekannt_ab=datetime.now(), quelle="test"))
    db.commit()

    ins = sec_fundamentaldaten(db, "AMZN")["insider"]
    assert ins["kauf_n"] == 1
    assert ins["kauf_wert"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Reihenfolge und Begrenzung
# ---------------------------------------------------------------------------

def test_juengste_zuerst_und_begrenzt(db):
    for i in range(20):
        db.add(EarningsEvent(ticker="AMZN",
                             datum=datetime(2020, 1, 1) + timedelta(days=90 * i),
                             eps_actual=1.0, eps_estimate=0.9,
                             surprise_pct=11.1, quelle="test"))
    db.commit()

    e = sec_fundamentaldaten(db, "AMZN", grenze=5)
    assert len(e["earnings"]) == 5
    daten = [x["datum"] for x in e["earnings"]]
    assert daten == sorted(daten, reverse=True)


def test_revisionen_juengste_zuerst(db):
    for i in range(5):
        db.add(AnalystenRevision(
            ticker="AMZN", datum=datetime(2025, 1, 1) + timedelta(days=30 * i),
            firma=f"Haus {i}", aktion="Kursziel", ziel_neu=100.0 + i,
            quelle="test"))
    db.commit()

    rev = sec_fundamentaldaten(db, "AMZN")["revisionen"]
    assert rev[0]["firma"] == "Haus 4"


# ---------------------------------------------------------------------------
# Leerer Bestand
# ---------------------------------------------------------------------------

def test_zuordnung_ohne_bestand_meldet_keine_daten(db):
    """ADR-Notierungen sind zugeordnet, aber nie geladen worden."""
    manuell_setzen(db, "DTE.DE", "DTEGF", cik="0000946770")

    e = sec_fundamentaldaten(db, "DTE.DE")
    assert e["us_ticker"] == "DTEGF"
    assert e["hat_daten"] is False


def test_negative_zuordnung_traegt_ihre_begruendung(db):
    """Die Anzeige soll sagen koennen, WARUM nichts da ist."""
    zuordnung_speichern(db, {
        "notierung": "ALV.DE", "cik": None, "us_ticker": None,
        "firmenname": "Allianz SE", "land": "Germany", "gefunden": False,
        "begruendung": "kein SEC-Emittent mit dem Namen 'ALLIANZ'"})

    e = sec_fundamentaldaten(db, "ALV.DE")
    assert e["zuordnung"]["begruendung"].startswith("kein SEC-Emittent")


def test_accruals_werden_gelesen(db):
    db.add(AccrualKennzahl(
        ticker="AMZN", periode_ende=datetime(2024, 12, 31),
        bekannt_ab=datetime(2025, 2, 1), accrual=-0.035,
        netto_gewinn=1.0, operativer_cashflow=2.0, bilanzsumme=30.0,
        quelle="test"))
    db.commit()

    e = sec_fundamentaldaten(db, "AMZN")
    assert e["accruals"]["wert"] == pytest.approx(-0.035)
