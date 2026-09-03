"""
tests/test_journal_auto.py — Das Journal als Ausgabe statt als Eingabe.

Vorher war es eine handgefuehrte Parallelaufzeichnung von etwas, das das System
bereits wusste: die Position stand in `positions`, die Analyse im Snapshot, das
Ergebnis im Kurs. Wer beides pflegen muss, pflegt am Ende keines — im Bestand
standen 25 Testeintraege und kein einziger echter Trade.

Geprueft wird, was diese Automatik still wertlos machen wuerde:

  * eine Einstiegsanalyse, die NACH dem Kauf entstanden ist — dann misst man
    Nachwissen und die ganze Auswertung waere geschoent,
  * ein R-Multiple gegen den nachgezogenen statt den initialen Stop — der
    Nenner schrumpft, und aus gewoehnlichen Trades werden Rekorde,
  * ein Break-Even, das die Gebuehren ignoriert,
  * eine erfundene Zahl, wo gar kein Risiko definiert war.
"""

from datetime import datetime, timedelta

import pytest

from services.watchlist import (
    ANALYSE_ALTER_HINWEIS_TAGE, QUELLE_JOURNAL_AUTO, _journaleintrag_abschliessen,
    _r_multiple,
)


class _Pos:
    """Minimale Position — nur die Felder, die der Abschluss liest."""

    def __init__(self, **kw):
        self.id = kw.get("id", "p1")
        self.ticker = kw.get("ticker", "AAPL")
        self.buy_date = kw.get("buy_date", "2026-01-05")
        self.buy_price = kw.get("buy_price", 100.0)
        self.quantity = kw.get("quantity", 10.0)
        self.stop_loss = kw.get("stop_loss", 90.0)
        self.take_profit = kw.get("take_profit", 130.0)
        self.fees = kw.get("fees", 0.0)
        self.sell_date = kw.get("sell_date", "2026-02-04")
        self.sell_price = kw.get("sell_price", 120.0)
        self.sell_fees = kw.get("sell_fees", 0.0)


class _Eintrag:
    def __init__(self, stop_initial=90.0):
        self.position_id = "p1"
        self.stop_initial = stop_initial
        self.exit_date = self.exit_price = None
        self.pnl_eur = self.pnl_pct = self.status = None
        self.r_multiple = self.haltedauer_tage = None


class _Session:
    """Session-Ersatz: `query(...).filter(...).first()` liefert den Eintrag."""

    def __init__(self, eintrag):
        self._eintrag = eintrag

    def query(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._eintrag


# ---------------------------------------------------------------------------
# R-Multiple — die Groesse, die Trades vergleichbar macht
# ---------------------------------------------------------------------------

def test_r_multiple_rechnet_gegen_das_geplante_risiko():
    """Einstieg 100, Stop 90, Ausstieg 120 → 20 gewonnen bei 10 riskiert."""
    assert _r_multiple(100.0, 120.0, 90.0) == pytest.approx(2.0)


def test_verlust_ergibt_negatives_r():
    assert _r_multiple(100.0, 92.0, 90.0) == pytest.approx(-0.8)


def test_ohne_stop_gibt_es_kein_r_multiple():
    """Ohne Stop gab es kein definiertes Risiko — eine Zahl waere erfunden.

    Genau dieser Fall liegt heute vor: beide offenen Positionen haben weder
    Stop noch Ziel. Ein stillschweigender Ersatzwert wuerde die spaetere
    Auswertung vergiften.
    """
    assert _r_multiple(100.0, 120.0, None) is None


def test_stop_ueber_dem_einstieg_ist_ein_eingabefehler():
    """Bei einer Long-Position kein Risiko, sondern ein vertauschtes Feld."""
    assert _r_multiple(100.0, 120.0, 110.0) is None
    assert _r_multiple(100.0, 120.0, 100.0) is None


def test_der_initiale_stop_ist_der_bezug_nicht_der_nachgezogene():
    """Der teuerste Fehler dieser Kennzahl.

    Wird der Stop von 90 auf 99 nachgezogen und man rechnet dagegen, ergibt
    derselbe Trade statt +2,0 R ploetzlich +20,0 R — bei einem Risiko, das so
    nie bestand. Deshalb liegt `stop_initial` im Journaleintrag und nicht in
    der Position, die sich mitbewegt.
    """
    initial = _r_multiple(100.0, 120.0, 90.0)
    nachgezogen = _r_multiple(100.0, 120.0, 99.0)
    assert initial == pytest.approx(2.0)
    assert nachgezogen == pytest.approx(20.0)
    assert nachgezogen > initial * 5      # der Unterschied ist keine Nuance


def test_stop_ueber_dem_einstieg_hat_kein_definiertes_risiko():
    """Ein bis ueber den Einstieg nachgezogener Stop macht den Trade risikofrei.

    Dann ist R nicht gross, sondern undefiniert — der Nenner ist null oder
    negativ. None ist hier die richtige Antwort, keine Zahl.
    """
    assert _r_multiple(100.0, 120.0, 105.0) is None


# ---------------------------------------------------------------------------
# Abschluss
# ---------------------------------------------------------------------------

def test_abschluss_fuellt_alles_ohne_eingabe():
    eintrag = _Eintrag()
    assert _journaleintrag_abschliessen(_Session(eintrag), _Pos()) is True

    assert eintrag.status == "Gewonnen"
    assert eintrag.pnl_eur == pytest.approx(200.0)      # (120-100) * 10
    assert eintrag.pnl_pct == pytest.approx(20.0)
    assert eintrag.r_multiple == pytest.approx(2.0)
    assert eintrag.haltedauer_tage == 30
    assert eintrag.exit_price == pytest.approx(120.0)


def test_gebuehren_entscheiden_ueber_break_even():
    """Ein Trade, der die Kosten nicht einspielt, ist kein Nullergebnis.

    Kursgewinn 10 Euro, Gebuehren 10 Euro → nach Kurs ein Gewinn, nach Kasse
    eine Null. Das Journal muss die Kasse abbilden.
    """
    eintrag = _Eintrag()
    pos = _Pos(sell_price=101.0, quantity=10.0, fees=5.0, sell_fees=5.0)
    _journaleintrag_abschliessen(_Session(eintrag), pos)

    assert eintrag.pnl_eur == pytest.approx(0.0)
    assert eintrag.status == "Break-Even"


def test_verlusttrade_wird_als_solcher_gefuehrt():
    eintrag = _Eintrag()
    _journaleintrag_abschliessen(_Session(eintrag), _Pos(sell_price=85.0))
    assert eintrag.status == "Verloren"
    assert eintrag.pnl_eur == pytest.approx(-150.0)
    assert eintrag.r_multiple == pytest.approx(-1.5)


def test_ohne_passenden_eintrag_passiert_nichts():
    """Eine Position aus der Zeit vor der Automatik hat keinen Eintrag.

    Das ist der Normalfall fuer Altbestand und darf nicht scheitern — die
    Entscheidung lautet: erst ab dem naechsten Kauf.
    """
    assert _journaleintrag_abschliessen(_Session(None), _Pos()) is False


def test_unlesbares_datum_kippt_den_abschluss_nicht():
    """P&L und R-Multiple haengen nicht am Datum — nur die Haltedauer."""
    eintrag = _Eintrag()
    _journaleintrag_abschliessen(_Session(eintrag), _Pos(sell_date="unbekannt"))
    assert eintrag.haltedauer_tage is None
    assert eintrag.pnl_eur == pytest.approx(200.0)
    assert eintrag.status == "Gewonnen"


# ---------------------------------------------------------------------------
# Konventionen
# ---------------------------------------------------------------------------

def test_automatische_eintraege_sind_als_solche_erkennbar():
    """Handgeschriebene und automatische Eintraege duerfen sich in einer
    Auswertung ueber realisierte Ergebnisse nicht mischen — nur die
    automatischen sind vollstaendig."""
    assert QUELLE_JOURNAL_AUTO == "auto"


def test_alterhinweis_ist_nur_ein_hinweis():
    """Die Schwelle schliesst nichts aus, sie wird nur ausgewiesen.

    Ein hart gesetzter Schnitt waere eine Annahme, die spaeter niemand mehr
    sieht; die Auswertung soll selbst entscheiden, ab wann eine Analyse zu
    alt ist.
    """
    assert ANALYSE_ALTER_HINWEIS_TAGE > 0


# ---------------------------------------------------------------------------
# Die Insert-Reihenfolge — der Fehler, der die Stop-Historie leer hielt
# ---------------------------------------------------------------------------

@pytest.fixture
def echte_db(monkeypatch):
    """In-Memory-Datenbank mit AKTIVEN Fremdschluesseln.

    Der Pragma-Teil ist der ganze Punkt: ohne `foreign_keys=ON` liefe der
    fehlerhafte Code klaglos durch, und dieser Test waere eine leere Huelle,
    die Sicherheit vortaeuscht. Deshalb wird unten geprueft, dass die Pruefung
    wirklich aktiv ist.
    """
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import sessionmaker

    import services.watchlist as wl
    from database import Base
    # Die Snapshot-Tabellen haengen an derselben Base, werden aber erst durch
    # den Import registriert. Ohne ihn faende `_einstiegsanalyse` keine
    # Tabelle und der Test der Verknuepfung waere nicht moeglich.
    import snapshot_engine.models  # noqa: F401

    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_an(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    fabrik = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1, (
            "Fremdschluesselpruefung inaktiv — der Test koennte den Fehler "
            "nicht mehr sehen.")

    monkeypatch.setattr(wl, "get_session", fabrik)
    yield fabrik
    engine.dispose()


def test_kauf_mit_stop_schreibt_die_historie(echte_db):
    """Der Regressionstest fuer den Fehler, der Abschnitt C blockiert hat.

    `PositionStopHistorie.position_id` traegt einen Fremdschluessel auf
    `positions.id`, aber keine `relationship()`. SQLAlchemy kannte die
    Abhaengigkeit deshalb nicht und schrieb die Historie, BEVOR die Position
    existierte — mit aktiven Fremdschluesseln scheiterte jeder Kauf mit
    Stop-Loss an einem IntegrityError.

    Sichtbar war das nur daran, dass `position_stop_historie` dauerhaft bei
    null Zeilen stand. Die Diagnose lautete jahrelang "der Besitzer traegt
    keine Stops ein"; tatsaechlich konnte das Programm sie nicht speichern.
    """
    import services.watchlist as wl
    from database import JournalEntry, PositionStopHistorie, WatchlistItem

    sitzung = echte_db()
    sitzung.add(WatchlistItem(ticker="AAPL", name="Apple", status="Beobachtet"))
    sitzung.commit()
    sitzung.close()

    pos = wl.add_position("AAPL", buy_price=100.0, quantity=10.0,
                          buy_date="2026-01-05", stop_loss=90.0,
                          take_profit=130.0)
    assert pos is not None, "Der Kauf selbst darf nicht scheitern."

    sitzung = echte_db()
    historie = sitzung.query(PositionStopHistorie).all()
    eintrag = sitzung.query(JournalEntry).first()

    assert len(historie) == 1
    assert historie[0].quelle == wl.QUELLE_EROEFFNUNG
    assert historie[0].stop == pytest.approx(90.0)

    # Und der Journaleintrag entsteht in derselben Transaktion.
    assert eintrag is not None
    assert eintrag.quelle == QUELLE_JOURNAL_AUTO
    assert eintrag.stop_initial == pytest.approx(90.0)
    assert eintrag.position_id == pos["id"]
    sitzung.close()


def test_kauf_ohne_stop_erzeugt_keine_historie_aber_ein_journal(echte_db):
    """Ohne Stop gibt es nichts zu vermerken — der Eintrag entsteht trotzdem."""
    import services.watchlist as wl
    from database import JournalEntry, PositionStopHistorie, WatchlistItem

    sitzung = echte_db()
    sitzung.add(WatchlistItem(ticker="SAP.DE", name="SAP", status="Beobachtet"))
    sitzung.commit()
    sitzung.close()

    pos = wl.add_position("SAP.DE", buy_price=200.0, quantity=5.0,
                          buy_date="2026-01-05")
    assert pos is not None

    sitzung = echte_db()
    assert sitzung.query(PositionStopHistorie).count() == 0
    eintrag = sitzung.query(JournalEntry).first()
    assert eintrag is not None
    assert eintrag.stop_initial is None
    sitzung.close()


def test_verkauf_schliesst_den_eintrag_ueber_den_echten_pfad(echte_db):
    """Kauf und Verkauf durch die oeffentlichen Funktionen, nicht am Modell vorbei."""
    import services.watchlist as wl
    from database import JournalEntry, WatchlistItem

    sitzung = echte_db()
    sitzung.add(WatchlistItem(ticker="MSFT", name="Microsoft", status="Beobachtet"))
    sitzung.commit()
    sitzung.close()

    pos = wl.add_position("MSFT", buy_price=100.0, quantity=10.0,
                          buy_date="2026-01-05", stop_loss=90.0)
    wl.close_position("MSFT", pos["id"], sell_price=120.0,
                      sell_date="2026-02-04", sell_fees=5.0)

    sitzung = echte_db()
    eintrag = sitzung.query(JournalEntry).first()
    assert eintrag.status == "Gewonnen"
    assert eintrag.pnl_eur == pytest.approx(195.0)
    assert eintrag.r_multiple == pytest.approx(2.0)
    assert eintrag.haltedauer_tage == 30
    sitzung.close()


def test_die_einstiegsanalyse_muss_vor_dem_kauf_liegen(echte_db):
    """Der Kern der Verknuepfung — und die Stelle, an der Nachwissen
    einsickern wuerde.

    Verknuepft werden darf nur eine Analyse, die zum Kaufzeitpunkt bereits
    existierte. Eine spaetere zu verlinken hiesse, den Trade gegen Wissen zu
    bewerten, das damals niemand hatte; die Auswertung "wie liefen meine
    Trades bei Signal X" waere dann systematisch geschoent.
    """
    from datetime import datetime as dt

    import services.watchlist as wl
    from database import JournalEntry, WatchlistItem
    from snapshot_engine.models import AnalyseModus, AnalyseSnapshot, Datenmodus

    sitzung = echte_db()
    sitzung.add(WatchlistItem(ticker="AAPL", name="Apple", status="Beobachtet"))
    # Drei Analysen: zwei vor dem Kauf, eine danach.
    for tag, conf, signal in [("2025-12-20", 55.0, "NEUTRAL"),
                              ("2026-01-02", 71.0, "KAUF"),
                              ("2026-01-20", 88.0, "KAUF")]:
        sitzung.add(AnalyseSnapshot(
            ticker="AAPL", snapshot_zeitpunkt=dt.strptime(tag, "%Y-%m-%d"),
            kurs_bei_snapshot=100.0, confidence=conf, richtungssignal=signal,
            analyse_modus=AnalyseModus.NEUE_POSITION,
            datenmodus=Datenmodus.LIVE))
    sitzung.commit()
    sitzung.close()

    wl.add_position("AAPL", buy_price=100.0, quantity=10.0,
                    buy_date="2026-01-05", stop_loss=90.0)

    sitzung = echte_db()
    eintrag = sitzung.query(JournalEntry).first()
    # Die juengste VOR dem Kauf, nicht die beste und nicht die spaetere.
    assert eintrag.einstiegs_confidence == pytest.approx(71.0)
    assert eintrag.einstiegs_signal == "KAUF"
    assert eintrag.einstiegs_analyse_alter_tage == 3
    sitzung.close()


def test_ohne_vorherige_analyse_bleiben_die_felder_leer(echte_db):
    """None heisst "keine Analyse vorhanden" — nicht "neutrale Analyse".

    Wer beides gleich behandelt, zaehlt Trades ohne jede Grundlage als
    Beleg fuer ein Signal.
    """
    import services.watchlist as wl
    from database import JournalEntry, WatchlistItem

    sitzung = echte_db()
    sitzung.add(WatchlistItem(ticker="SAP.DE", name="SAP", status="Beobachtet"))
    sitzung.commit()
    sitzung.close()

    wl.add_position("SAP.DE", buy_price=200.0, quantity=5.0,
                    buy_date="2026-01-05")

    sitzung = echte_db()
    eintrag = sitzung.query(JournalEntry).first()
    assert eintrag.einstiegs_snapshot_id is None
    assert eintrag.einstiegs_confidence is None
    assert eintrag.einstiegs_analyse_alter_tage is None
    sitzung.close()
