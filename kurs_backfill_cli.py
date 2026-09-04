"""
kurs_backfill_cli.py — Kursreihen des erweiterten Universums laden (Auftrag C).

**Warum das ein eigener Lauf ist und nicht `backfill_cli.py`.** Der grosse
Backfill zeichnet Snapshots auf: er rechnet je Ticker und Stichtag zehn
Indikatoren, SMC-Strukturen und Scores. Das kostete bei Job #3 rund 35
Sekunden je Ticker, auf 4.164 Titeln also gut zwei Tage. Dieser Lauf holt
nur die Kursreihen — dieselben Rohdaten, die `KursHistorie` seit §2j ohnehin
festhaelt, ohne jede Deutung.

Der Unterschied lohnt, weil die naechste offene Frage keine Indikatoren
braucht. Die Insider-Gegenprobe aus §2n (Lakonishok/Lee verorten den Effekt
in kleineren Firmen) braucht je Beobachtung nur zweierlei: den Kurs am
Stichtag und den Kurs 90 Tage spaeter. Beides steht in der Kursreihe.

Der Lauf ist damit kein Ersatz fuer den grossen Backfill, sondern dessen
erste Haelfte: sind die Reihen einmal da, kostet ein spaeterer
Snapshot-Backfill keinen einzigen zusaetzlichen Abruf mehr fuer diese Titel.

**Fortschritt liegt in der Datenbank.** Abbrechen mit Strg-C und spaeter
erneut starten setzt fort — `services.kurshistorie.fehlende_ticker` fragt ab,
welche Reihen noch fehlen. Ein Ticker gilt als erledigt, sobald er eine
Reihe hat.

WICHTIG: Das Dashboard sollte waehrenddessen NICHT laufen. SQLite erlaubt im
WAL-Modus nur einen Schreiber.

Beispiele:
    py kurs_backfill_cli.py                     # erweitertes Universum, ab 2015
    py kurs_backfill_cli.py --status            # nur Bestand anzeigen
    py kurs_backfill_cli.py --ohne-deutsche     # nur US-Titel
    py kurs_backfill_cli.py --alle-us           # auch ohne SEC-Historie (5.364)
    py kurs_backfill_cli.py --ticker AAPL MSFT  # einzelne Titel (Test)
"""

import argparse
import logging
import sys
import time
from datetime import datetime

# Ticker je Netzabruf. yfinance buendelt sie in einen Request; groessere
# Bloecke sind schneller, laufen aber eher in eine Drosselung. 50 hat sich
# in services/market_data_batch.py als Standard bewaehrt.
CHUNK = 50

# Pause zwischen den Bloecken. Bei 4.164 Tickern sind das rund 83 Abrufe —
# eine Sekunde Abstand kostet anderthalb Minuten und schont das Limit.
PAUSE_SEKUNDEN = 1.0

# Ab wann die Reihen gebraucht werden. Der Insider-Bestand beginnt 2016-01;
# ein halbes Jahr Vorlauf deckt das Sechs-Monats-Fenster der Kennzahl ab,
# ein ganzes Jahr gibt Luft fuer spaetere Indikatoren mit langem Anlauf.
START = datetime(2015, 1, 1)

# Weniger als das ist keine brauchbare Reihe, sondern ein Rest. Ein Titel mit
# drei Handelstagen wuerde sonst als "vorhanden" gelten und beim naechsten
# Lauf nicht mehr nachgeholt.
MIN_BARS = 60


def _logging_einrichten(ausfuehrlich: bool):
    logging.basicConfig(
        level=logging.DEBUG if ausfuehrlich else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    for name in ("yfinance", "urllib3", "peewee"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _dauer(sekunden: float) -> str:
    if sekunden < 60:
        return f"{sekunden:.0f}s"
    if sekunden < 3600:
        return f"{sekunden / 60:.0f}m"
    return f"{sekunden // 3600:.0f}h {(sekunden % 3600) / 60:.0f}m"


def _universum(db, args) -> list[str]:
    from services.universum import erweitertes_universum

    if args.ticker:
        return [t.strip().upper() for t in args.ticker if t.strip()]
    return erweitertes_universum(
        db,
        nur_mit_sec_historie=not args.alle_us,
        mit_deutschen=not args.ohne_deutsche,
    )


def _status(db, tickers: list[str]) -> None:
    from services.kurshistorie import bestand, fehlende_ticker

    gesamt = bestand(db)
    offen = fehlende_ticker(db, tickers)
    print(f"  Universum:        {len(tickers):,} Ticker")
    print(f"  Reihen im Bestand: {gesamt.get('ticker', 0):,} Ticker, "
          f"{gesamt.get('zeilen', 0):,} Handelstage")
    print(f"  Davon offen:      {len(offen):,} Ticker")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Kursreihen des erweiterten Universums laden (Auftrag C).")
    parser.add_argument("--status", action="store_true",
                        help="Nur den Bestand anzeigen, nichts laden.")
    parser.add_argument("--ticker", nargs="+",
                        help="Nur diese Ticker laden (Test).")
    parser.add_argument("--alle-us", action="store_true",
                        help="Auch US-Titel ohne SEC-Historie (5.364 statt 4.035).")
    parser.add_argument("--ohne-deutsche", action="store_true",
                        help="DAX/MDAX/SDAX weglassen.")
    parser.add_argument("--neu-laden", action="store_true",
                        help="Vorhandene Reihen ueberschreiben statt ueberspringen.")
    parser.add_argument("-v", "--ausfuehrlich", action="store_true")
    args = parser.parse_args()

    _logging_einrichten(args.ausfuehrlich)
    logger = logging.getLogger("kurs_backfill")

    import database
    from services.kurshistorie import fehlende_ticker, reihe_speichern
    from services.market_data_batch import batch_download_ohlcv

    database.init_db()
    db = database.get_session()
    try:
        tickers = _universum(db, args)
        if not tickers:
            print("Universum ist leer — nichts zu tun.")
            return 1

        if args.status:
            _status(db, tickers)
            return 0

        offen = tickers if args.neu_laden else fehlende_ticker(db, tickers)
        if not offen:
            print("Alle Reihen liegen bereits vor.")
            _status(db, tickers)
            return 0

        print(f"Kurs-Backfill: {len(offen):,} von {len(tickers):,} Tickern offen, "
              f"ab {START.date()}.")
        print(f"Bloecke zu {CHUNK} Tickern, {PAUSE_SEKUNDEN}s Pause.\n")

        begonnen = time.time()
        geladen = fehlgeschlagen = zeilen_gesamt = 0
        bloecke = [offen[i:i + CHUNK] for i in range(0, len(offen), CHUNK)]

        for nummer, block in enumerate(bloecke, 1):
            try:
                daten = batch_download_ohlcv(
                    block, start=START, chunk_size=CHUNK,
                    min_bars=MIN_BARS, pause_sekunden=0.0)
            except Exception as e:
                # Ein Block darf den Lauf nicht beenden — beim naechsten
                # Start sind seine Ticker wieder offen.
                logger.error("Block %d/%d fehlgeschlagen: %s",
                             nummer, len(bloecke), e, exc_info=True)
                fehlgeschlagen += len(block)
                continue

            for ticker in block:
                hist = daten.get(ticker)
                if hist is None or hist.empty:
                    fehlgeschlagen += 1
                    continue
                try:
                    zeilen_gesamt += reihe_speichern(db, ticker, hist)
                    geladen += 1
                except Exception as e:
                    logger.error("Kursreihe %s nicht speicherbar: %s",
                                 ticker, e, exc_info=True)
                    fehlgeschlagen += 1
            db.commit()

            fertig = nummer / len(bloecke)
            verbraucht = time.time() - begonnen
            rest = verbraucht / fertig - verbraucht if fertig > 0 else 0
            print(f"  Block {nummer:3d}/{len(bloecke)}  {100 * fertig:5.1f}%  |  "
                  f"{geladen:,} Reihen  |  {zeilen_gesamt:,} Tage  |  "
                  f"{fehlgeschlagen} ohne Daten  |  Rest {_dauer(rest)}",
                  flush=True)

            if PAUSE_SEKUNDEN and nummer < len(bloecke):
                time.sleep(PAUSE_SEKUNDEN)

        print(f"\nFertig in {_dauer(time.time() - begonnen)}: "
              f"{geladen:,} Reihen, {zeilen_gesamt:,} Handelstage, "
              f"{fehlgeschlagen} ohne Daten.")
        print("\nDie Ticker ohne Daten sind der Survivorship-Rand: yfinance "
              "liefert delistete Titel nicht mehr. services.universum.abdeckung() "
              "beziffert, was dadurch fehlt.")
        _status(db, tickers)
        return 0
    except KeyboardInterrupt:
        print("\nAbgebrochen. Erneutes Starten setzt fort.")
        return 130
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
