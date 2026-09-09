"""
nettoemission_cli.py — Traegt die Nettoemission? (P2-06, elfte Signalfamilie)

**Was hier geprueft wird.** Pontiff/Woodgate (2008): Firmen, die Aktien
ausgeben, liefern schlechtere Folgerenditen als Firmen, die zurueckkaufen.
`LITERATUR.md` §6.3 fuehrt diese Familie als staerksten Einzelkandidaten —
kursunabhaengig, punkt-in-zeit datierbar, und als **einzige** gepruefte
Familie mit ausdruecklich berichteter Robustheit ueber kleine UND grosse
Firmen.

Genau daran ist der Insider-Clusterkauf gestorben (§2o): auf 592 Large Caps
+3,1 pp, auf 4.161 Titeln −0,0 pp. Deshalb laeuft diese Messung von
vornherein ueber das erweiterte Universum, ueber `auswertung/kurspanel.py`
und ohne einen einzigen Snapshot.

**Unten ist gut.** Quintil 1 sind die staerksten Rueckkaeufer, Quintil 5 die
staerksten Emittenten. `spread_pp` ist Q1 minus Q5; positiv heisst
„Hypothese bestaetigt".

**Der Lauf geht auf TRAIN.** Der Holdout bleibt bei null Zugriffen.

Beispiele:
    py nettoemission_cli.py                  # 7/30/90 Tage
    py nettoemission_cli.py --horizont 90    # nur ein Horizont
    py nettoemission_cli.py --stichprobe 300 # Probelauf
"""

import argparse
import logging
import sys
import time

HORIZONTE = (7, 30, 90)

# Die Binomialtafel aus §2j, damit „7 von 9" nicht als Bestaetigung gelesen
# wird. Sie gehoert an jede Ausgabe einer Jahrespruefung.
BINOMIAL = {6: 0.51, 7: 0.18, 8: 0.039, 9: 0.004, 10: 0.001}


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


def _quintiltabelle(zeilen: list[dict]) -> None:
    print(f"\n    {'Quintil':<10} {'n':>9}  {'schlaegt Markt':>14}  "
          f"{'Vorsprung pp':>13}  {'+/-':>6}  {'Ertrag pp':>10}")
    for z in zeilen:
        n = z.get("n") or 0
        quote = z.get("markt_trefferquote")
        vorsprung = z.get("markt_vorsprung_pp")
        spanne = z.get("fehlerspanne_korrigiert_pp")
        ertrag = z.get("ueberrendite_vorsprung_pp")
        stern = " *" if z.get("signifikant_korrigiert") else ""
        etikett = {1: "1 (Rueck)", 5: "5 (Emis)"}.get(z["quintil"], str(z["quintil"]))
        print(f"    {etikett:<10} {n:>9,}  "
              f"{'—' if quote is None else f'{quote:>13.1f}%'}  "
              f"{'—' if vorsprung is None else f'{vorsprung:>+13.1f}'}  "
              f"{'—' if spanne is None else f'{spanne:>6.1f}'}  "
              f"{'—' if ertrag is None else f'{ertrag:>+10.2f}'}{stern}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nettoemission auf dem erweiterten Universum.")
    parser.add_argument("--horizont", type=int, choices=HORIZONTE, nargs="+",
                        default=list(HORIZONTE))
    parser.add_argument("--stichprobe", type=int,
                        help="Nur die ersten N Ticker (Probelauf).")
    parser.add_argument("-v", "--ausfuehrlich", action="store_true")
    args = parser.parse_args()

    _logging_einrichten(args.ausfuehrlich)

    import database
    from services.universum import erweitertes_universum
    from snapshot_engine.auswertung.kurspanel import (
        abdeckung_je_jahr, panel_bauen,
    )
    from snapshot_engine.auswertung.nettoemission import (
        nettoemission_auswerten, nettoemission_jahresstabilitaet,
    )

    database.init_db()
    db = database.get_session()
    try:
        from database import NettoemissionKennzahl
        bestand = db.query(NettoemissionKennzahl).count()
        traeger = db.query(NettoemissionKennzahl.ticker).distinct().count()
        print(f"\nBestand: {bestand:,} Kennzahlen ueber {traeger:,} Ticker")
        if not bestand:
            print("Kein Bestand — zuerst `py -m services.nettoemission` laufen "
                  "lassen.")
            return 1

        tickers = erweitertes_universum(db, nur_mit_sec_historie=True)
        if args.stichprobe:
            tickers = tickers[:args.stichprobe]
        print(f"Universum: {len(tickers):,} Ticker\n")

        # Sidak ueber ALLE Zellen des Laufs, nicht je Horizont — sonst ist die
        # Korrektur zu mild. Fuenf Quintile je Horizont.
        z_tests = len(args.horizont) * 5

        for horizont in args.horizont:
            print(f"\n{'=' * 72}")
            print(f"HORIZONT {horizont} TAGE")
            print("=" * 72)

            begonnen = time.time()
            panel = panel_bauen(db, tickers, horizont)
            print(f"  Panel: {len(panel):,} Beobachtungen "
                  f"({_dauer(time.time() - begonnen)})")
            print(f"  Je Jahr: {abdeckung_je_jahr(panel)}")

            ergebnis = nettoemission_auswerten(db, horizont=horizont,
                                               panel=panel, z_tests=z_tests)
            print(f"\n  Marktbasis: {ergebnis['basis_markt']}% schlagen den "
                  f"Index, mittlere Ueberrendite {ergebnis['basis_ertrag']} pp")
            print(f"  Verwertet: {ergebnis['n_gesamt']:,} Zeilen, "
                  f"Sidak-Schwelle z = {ergebnis['z_korrigiert']}")

            _quintiltabelle(ergebnis["quintile"])

            spread = ergebnis["spread_pp"]
            print(f"\n  Spread Q1 - Q5 (Rueckkaeufer minus Emittenten): "
                  f"{'—' if spread is None else f'{spread:+.1f} pp'}"
                  f"   Ertrag: {ergebnis['ertrag_spread_pp']}")
            if spread is not None:
                if spread > 0:
                    print("  Richtung: wie von Pontiff/Woodgate vorhergesagt.")
                else:
                    print("  Richtung: GEGEN die Vorhersage — Emittenten "
                          "laufen besser als Rueckkaeufer.")

            stabil = nettoemission_jahresstabilitaet(db, horizont=horizont,
                                                     panel=panel)
            gleich = stabil.get("vorzeichen_gleich")
            gesamt = stabil.get("jahre_gesamt")
            p = BINOMIAL.get(gleich)
            print(f"\n  Jahresstabilitaet: {gleich} von {gesamt} Jahren im "
                  f"Vorzeichen (Trefferquote)"
                  f"{'' if p is None else f', p = {p}'}, "
                  f"{stabil.get('ertrag_vorzeichen_gleich')} von "
                  f"{stabil.get('ertrag_jahre_gesamt')} (Rendite)")
            for zeile in stabil.get("jahre", []):
                print(f"    {zeile.get('jahr')}: Spread {zeile.get('spread_pp')} pp, "
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
