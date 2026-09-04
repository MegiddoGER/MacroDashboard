"""
gegenprobe_cli.py — Der Insider-Clusterkauf auf Small und Mid Cap (Auftrag C).

**Was hier geprueft wird.** §2n hat den ersten Kandidaten dieses Projekts
gefunden, der die Jahresstabilitaet ueberlebt: Titel, bei denen in sechs
Monaten mindestens zwei verschiedene Insider am Markt gekauft haben, liegen
auf 90 Tagen rund 3,1 Prozentpunkte vor der Marktbasis, in acht von neun
Jahren im Vorzeichen stabil. Signifikant ist das nicht — die Stichprobe traegt
es nicht.

Lakonishok/Lee (2001) verorten den Insidereffekt in **kleineren** Firmen. Das
Universum von §2n war der S&P 500 plus DAX/MDAX, also praktisch reines Large
Cap. Daraus folgt eine Vorhersage, die falsifizierbar ist:

    Verstaerkt sich der Vorsprung auf einem Small- und Mid-Cap-Universum,
    ist der Befund belegt. Verschwindet er dort, war er Rauschen.

Das ist die schaerfere Pruefung als ein Holdout-Zugriff, **und sie verbraucht
nichts** — der Holdout bleibt bei null Zugriffen. Deshalb laeuft sie zuerst.

**Sie laeuft auf TRAIN, nicht auf dem Gesamtbestand.** Der Holdout wird auch
hier nicht angefasst; `insider_auswerten(panel=...)` trennt ueber den
Stichtag.

Beispiele:
    py gegenprobe_cli.py                     # volle Gegenprobe, 7/30/90 Tage
    py gegenprobe_cli.py --nur-insider-daten # nur den Insider-Bestand nachladen
    py gegenprobe_cli.py --horizont 90       # nur ein Horizont (schneller)
    py gegenprobe_cli.py --stichprobe 300    # Probelauf auf 300 Tickern
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime

HORIZONTE = (7, 30, 90)

# Der Befund aus §2n, gegen den verglichen wird. Er steht hier als Zahl und
# nicht als Prosa, damit die Gegenueberstellung im Ausgabetext automatisch
# stimmt und nicht von Hand nachgepflegt werden muss.
BEFUND_2N = {7: -0.4, 30: 1.4, 90: 3.7}          # Spread Cluster minus kein Kauf
BEFUND_2N_VORSPRUNG = {7: -0.4, 30: 1.2, 90: 3.1}  # Cluster gegen Marktbasis


def _logging_einrichten(ausfuehrlich: bool):
    logging.basicConfig(
        level=logging.DEBUG if ausfuehrlich else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S", stream=sys.stdout)
    for name in ("yfinance", "urllib3", "peewee"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _dauer(sekunden: float) -> str:
    if sekunden < 60:
        return f"{sekunden:.0f}s"
    if sekunden < 3600:
        return f"{sekunden / 60:.0f}m"
    return f"{sekunden // 3600:.0f}h {(sekunden % 3600) / 60:.0f}m"


def _insider_nachladen(db, tickers: list[str]) -> None:
    """Holt die Form-4-Geschaefte fuer das erweiterte Universum nach.

    Idempotent (Abgleich ueber accession + sec_sk), und die Quartals-ZIPs
    liegen im Zwischenspeicher von Auftrag B — kein Netzabruf.
    """
    from services.insider import insider_backfill

    print(f"Insider-Bestand fuer {len(tickers):,} Ticker nachladen ...")
    begonnen = time.time()
    statistik = insider_backfill(db, tickers, von=date(2016, 1, 1))
    print(f"  {statistik['quartale_geladen']}/{statistik['quartale']} Quartale, "
          f"{statistik['gelesen']:,} gelesen, {statistik['neu']:,} neu "
          f"({_dauer(time.time() - begonnen)}).\n")


def _tabelle(ueberschrift: str, zeilen: list[dict], schluessel: str) -> None:
    print(f"\n  {ueberschrift}")
    print(f"    {'Gruppe':<14} {'n':>8}  {'schlaegt Markt':>14}  "
          f"{'Vorsprung pp':>13}  {'Ertrag pp':>10}")
    for zeile in zeilen:
        n = zeile.get("n") or 0
        quote = zeile.get("markt_trefferquote")
        vorsprung = zeile.get("markt_vorsprung_pp")
        ertrag = zeile.get("ueberrendite_vorsprung_pp")
        print(f"    {str(zeile.get(schluessel)):<14} {n:>8,}  "
              f"{'—' if quote is None else f'{quote:>13.1f}%'}  "
              f"{'—' if vorsprung is None else f'{vorsprung:>+13.1f}'}  "
              f"{'—' if ertrag is None else f'{ertrag:>+10.2f}'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insider-Clusterkauf auf dem erweiterten Universum.")
    parser.add_argument("--horizont", type=int, choices=HORIZONTE, nargs="+",
                        default=list(HORIZONTE))
    parser.add_argument("--stichprobe", type=int,
                        help="Nur die ersten N Ticker (Probelauf).")
    parser.add_argument("--nur-insider-daten", action="store_true",
                        help="Nur den Insider-Bestand nachladen, nicht messen.")
    parser.add_argument("--ohne-nachladen", action="store_true",
                        help="Insider-Bestand als vollstaendig annehmen.")
    parser.add_argument("-v", "--ausfuehrlich", action="store_true")
    args = parser.parse_args()

    _logging_einrichten(args.ausfuehrlich)

    import database
    from services.universum import abdeckung, abdeckung_text, erweitertes_universum
    from snapshot_engine.auswertung.insider import (
        CLUSTER_AB, insider_auswerten, insider_jahresstabilitaet,
    )
    from snapshot_engine.auswertung.kurspanel import (
        abdeckung_je_jahr, panel_bauen,
    )

    database.init_db()
    db = database.get_session()
    try:
        tickers = erweitertes_universum(db, nur_mit_sec_historie=True)
        if args.stichprobe:
            tickers = tickers[:args.stichprobe]
        print(f"\nUniversum: {len(tickers):,} Ticker\n")

        print("Survivorship-Abdeckung (Vergleichszeitraum 2016-2019):")
        print("  " + abdeckung_text(abdeckung(db, tickers, 2016, 2019)))
        print()

        if not args.ohne_nachladen:
            _insider_nachladen(db, tickers)
        if args.nur_insider_daten:
            return 0

        # Die Šidák-Korrektur muss ueber ALLE Zellen dieses Laufs gehen, nicht
        # je Horizont — sonst ist sie zu mild. Drei Gruppen mal zwei
        # Gruppierungen mal fuenf Quintile, je Horizont.
        z_tests = len(args.horizont) * (3 + 3 + 5)

        for horizont in args.horizont:
            print(f"\n{'=' * 72}")
            print(f"HORIZONT {horizont} TAGE")
            print("=" * 72)

            begonnen = time.time()
            panel = panel_bauen(db, tickers, horizont)
            print(f"  Panel: {len(panel):,} Beobachtungen "
                  f"({_dauer(time.time() - begonnen)})")
            print(f"  Je Jahr: {abdeckung_je_jahr(panel)}")

            ergebnis = insider_auswerten(db, horizont=horizont, panel=panel,
                                         z_tests=z_tests)
            print(f"\n  Marktbasis: {ergebnis['basis_markt']}% schlagen den "
                  f"Index, mittlere Ueberrendite {ergebnis['basis_ertrag']} pp")
            print(f"  Verwertet: {ergebnis['n_gesamt']:,} Zeilen, "
                  f"Šidák-Schwelle z = {ergebnis['z_korrigiert']}")

            _tabelle("Ereignisgruppen", ergebnis["gruppen"], "gruppe")
            _tabelle("Nur opportunistische Kaeufer",
                     ergebnis["gruppen_opportunistisch"], "gruppe")
            if ergebnis["quintile"]:
                _tabelle("Quintile des Netto-Insiderhandels",
                         ergebnis["quintile"], "quintil")

            vorsprung = ergebnis["cluster_vorsprung_pp"]
            alt = BEFUND_2N.get(horizont)
            print(f"\n  Cluster gegen kein Kauf: "
                  f"{'—' if vorsprung is None else f'{vorsprung:+.1f} pp'}"
                  f"   (§2n auf Large Cap: {alt:+.1f} pp)")

            # Zweite Gegenueberstellung: die Clustergruppe gegen die
            # Marktbasis des Bestandes — die Zahl, die in §2n als +3,1 pp
            # steht. Sie und der Spread koennen auseinanderlaufen, wenn sich
            # die Gruppe ohne Kauf mitbewegt.
            cluster_zeile = next(
                (z for z in ergebnis["gruppen"]
                 if str(z.get("gruppe")).startswith(str(CLUSTER_AB))), None)
            if cluster_zeile is not None:
                gegen_basis = cluster_zeile.get("markt_vorsprung_pp")
                spanne = cluster_zeile.get("fehlerspanne_korrigiert_pp")
                alt_basis = BEFUND_2N_VORSPRUNG.get(horizont)
                print(f"  Cluster gegen Marktbasis: "
                      f"{'—' if gegen_basis is None else f'{gegen_basis:+.1f} pp'}"
                      f" ± {'—' if spanne is None else f'{spanne:.1f}'}"
                      f"   (§2n: {alt_basis:+.1f} pp ± 4,7)")
                if cluster_zeile.get("signifikant_korrigiert"):
                    print("  ** Signifikant nach Šidák — das war in §2n "
                          "nicht der Fall. **")

            if vorsprung is not None and alt is not None:
                if vorsprung > alt:
                    deutung = ("staerker als auf Large Cap — die Vorhersage "
                               "von Lakonishok/Lee bestaetigt sich")
                elif vorsprung > 0:
                    deutung = ("schwaecher als auf Large Cap, aber im "
                               "erwarteten Vorzeichen")
                else:
                    deutung = ("das Vorzeichen kehrt sich um — der Befund aus "
                               "§2n haelt auf kleineren Titeln NICHT")
                print(f"  Befund: {deutung}.")

            stabil = insider_jahresstabilitaet(db, horizont=horizont,
                                               panel=panel)
            print(f"\n  Jahresstabilitaet: "
                  f"{stabil.get('vorzeichen_gleich')} von "
                  f"{stabil.get('jahre_gesamt')} Jahren im Vorzeichen "
                  f"(Trefferquote), "
                  f"{stabil.get('ertrag_vorzeichen_gleich')} von "
                  f"{stabil.get('ertrag_jahre_gesamt')} (Rendite)")
            for zeile in stabil.get("jahre", []):
                print(f"    {zeile.get('jahr')}: "
                      f"Spread {zeile.get('spread_pp')} pp, "
                      f"Ertrag {zeile.get('ertrag_spread_pp')} pp, "
                      f"n = {zeile.get('n'):,}")

        print(f"\n{'=' * 72}")
        print("Der Holdout wurde NICHT angefasst — die Messung lief auf TRAIN.")
        print("=" * 72)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
