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

**Die Groessentrennung (`--groessentrennung`)** ist die erste der beiden
Gegenproben, die §2p sich selbst auferlegt hat. Emittenten sind systematisch
kleinere Titel; solange alles gegen die gepoolte Marktbasis laeuft, kann der
ganze Befund ein Groesseneffekt in anderer Verpackung sein. Der Lauf schneidet
die Beobachtungen nach Dollar-Umsatz in Klassen, rangt die Nettoemission
**innerhalb jeder Klasse neu** und misst jede Schicht gegen **ihre eigene**
Marktbasis. Er kostet keinen Holdout-Zugriff.

Warum Dollar-Umsatz und nicht Marktkapitalisierung: `auswertung/groesse.py`
begruendet es an NVDA — eine Kapitalisierung aus roher SEC-Aktienzahl mal
bereinigtem Kurs waere um den kumulierten Splitfaktor falsch, 2021 rund
Faktor 40, und zwar bevorzugt bei den starken Kurssteigern.

Beispiele:
    py nettoemission_cli.py                       # 7/30/90 Tage
    py nettoemission_cli.py --horizont 90         # nur ein Horizont
    py nettoemission_cli.py --stichprobe 300      # Probelauf
    py nettoemission_cli.py --groessentrennung    # die Gegenprobe
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


def _mrd(wert) -> str:
    """Dollar-Umsatz lesbar — Mio oder Mrd statt fuenfzehn Stellen."""
    if wert is None:
        return "—"
    if wert >= 1e9:
        return f"{wert / 1e9:,.1f} Mrd"
    return f"{wert / 1e6:,.1f} Mio"


def _kursnaehe_zeile(kursnaehe, praefix: str) -> None:
    """Die §2f-Pruefung in einer Zeile — Korrelation, Urteil, Stichprobe."""
    if not kursnaehe:
        print(f"{praefix}— (nicht gemessen)")
        return
    r = kursnaehe.get("rangkorrelation")
    urteil = kursnaehe.get("kursnah")
    etikett = {True: "KURSNAH", False: "eigenstaendig",
               None: "kein Urteil"}[urteil]
    print(f"{praefix}{'—' if r is None else f'{r:+.3f}'} "
          f"({etikett}, n = {kursnaehe.get('n', 0):,}, "
          f"Fenster {kursnaehe.get('fenster_tage')} T)")


def _jahresschichttabelle(ergebnis: dict) -> None:
    """Jahresstabilitaet je Groessenklasse — die schaerfste der drei Pruefungen."""
    schichten = ergebnis.get("schichten") or []
    if not schichten:
        print("\n  Keine auswertbare Schicht.")
        return

    print(f"\n  {'Klasse':<14} {'Vorzeichen':>12} {'p':>8}  "
          f"{'Rendite':>10} {'n':>12}")
    for s in schichten:
        etikett = {1: "1 (kleinste)", 5: "5 (groesste)"}.get(
            s["klasse"], str(s["klasse"]))
        gleich, gesamt = s["vorzeichen_gleich"], s["jahre_gesamt"]
        p = BINOMIAL.get(gleich) if gesamt else None
        treffer = f"{gleich} von {gesamt}"
        ertrag = f"{s['ertrag_vorzeichen_gleich']} von {s['ertrag_jahre_gesamt']}"
        p_text = "—" if p is None else f"{p:.3f}"
        print(f"  {etikett:<14} {treffer:>12} {p_text:>8}  "
              f"{ertrag:>10} {s['n']:>12,}")

    for s in schichten:
        etikett = {1: "1 (kleinste)", 5: "5 (groesste)"}.get(
            s["klasse"], str(s["klasse"]))
        jahre = ", ".join(f"{z['jahr']}: {z['spread_pp']:+.1f}"
                          for z in s.get("jahre", []))
        print(f"\n    Klasse {etikett} je Jahr: {jahre}")

    voll = ergebnis.get("schichten_voll_stabil")
    gesamt = ergebnis.get("schichten_gesamt")
    schwach = ergebnis.get("schwaechste_schicht")
    print(f"\n  {'=' * 68}")
    print(f"  BILANZ: {voll} von {gesamt} Klassen mit voller Vorzeichentreue.")
    if schwach:
        p = BINOMIAL.get(schwach["vorzeichen_gleich"])
        print(f"  Schwaechste Klasse: {schwach['klasse']} mit "
              f"{schwach['vorzeichen_gleich']} von {schwach['jahre_gesamt']}"
              f"{'' if p is None else f' (p = {p})'}")
        print("  Sie entscheidet, nicht der Durchschnitt: eine Schicht, die "
              "ihre\n  Jahre nicht traegt, ist in dieser Klasse Rauschen.")


def _schichttabelle(ergebnis: dict) -> None:
    """Die Groessentrennung: eine Quintiltabelle je Schicht, dann die Bilanz."""
    schichten = ergebnis.get("schichten") or []
    if not schichten:
        print("\n  Keine auswertbare Schicht — Groessentrennung ohne Ergebnis.")
        return

    korrelation = ergebnis.get("rangkorrelation")
    print(f"\n  Rangkorrelation Nettoemission x Dollar-Umsatz: "
          f"{'—' if korrelation is None else f'{korrelation:+.3f}'}")
    _kursnaehe_zeile(ergebnis.get("kursnaehe"),
                     "  Kursnaehe (global, §2p Einwand 2): ")
    print(f"  Sidak-Schwelle ueber alle Schichten: "
          f"z = {ergebnis.get('z_korrigiert')}")
    z = ergebnis.get("zaehlwerk") or {}
    print(f"  Zeilen: {z.get('zeilen', 0):,} · ohne Kennzahl "
          f"{z.get('ohne_kennzahl', 0):,} · ohne Groessenklasse "
          f"{z.get('ohne_klasse', 0):,} · verwertet {z.get('verwertet', 0):,}")

    for s in schichten:
        etikett = {1: "1 (kleinste)", 5: "5 (groesste)"}.get(
            s["klasse"], str(s["klasse"]))
        print(f"\n  {'-' * 68}")
        print(f"  GROESSENKLASSE {etikett} — n = {s['n']:,}, "
              f"Median-Umsatz {_mrd(s.get('umsatz_median'))}/Tag")
        print(f"  Eigene Marktbasis: {s.get('basis_markt')}% schlagen den "
              f"Index, mittlere Ueberrendite {s.get('basis_ertrag')} pp")
        _quintiltabelle(s["quintile"])
        sp = s.get("spread_pp")
        print(f"    Spread Q1 - Q5: "
              f"{'—' if sp is None else f'{sp:+.1f} pp'}"
              f"   Ertrag: {s.get('ertrag_spread_pp')}")
        _kursnaehe_zeile(s.get("kursnaehe"), "    Kursnaehe: ")

    mit = ergebnis.get("schichten_mit_vorsprung")
    gesamt = ergebnis.get("schichten_gesamt")
    print(f"\n  {'=' * 68}")
    print(f"  BILANZ: {mit} von {gesamt} Groessenklassen mit positivem Spread.")
    spreads = [s.get("spread_pp") for s in schichten
               if s.get("spread_pp") is not None]
    if spreads:
        print(f"  Spannweite der Spreads: {min(spreads):+.1f} bis "
              f"{max(spreads):+.1f} pp")
    if mit == gesamt and gesamt:
        print("  Lesart: der Befund haelt in JEDER Groessenklasse — er ist "
              "nicht die Groesse.")
    elif mit == 0:
        print("  Lesart: der Befund haelt in KEINER Klasse — §2p ist "
              "falsifiziert wie §2n durch §2o.")
    else:
        print("  Lesart: der Befund haelt nur in einem Teil der Klassen. "
              "Welche das sind, entscheidet, ob etwas uebrig bleibt.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nettoemission auf dem erweiterten Universum.")
    parser.add_argument("--horizont", type=int, choices=HORIZONTE, nargs="+",
                        default=list(HORIZONTE))
    parser.add_argument("--stichprobe", type=int,
                        help="Nur die ersten N Ticker (Probelauf).")
    parser.add_argument("--groessentrennung", action="store_true",
                        help="Gegenprobe: Quintile INNERHALB jeder "
                             "Groessenklasse, jede Schicht gegen ihre eigene "
                             "Marktbasis (§2p, offener Einwand 1).")
    parser.add_argument("--klassen", type=int, default=5,
                        help="Zahl der Groessenschichten (Vorgabe 5).")
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
        nettoemission_jahresstabilitaet_nach_groesse, nettoemission_nach_groesse,
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
        # Korrektur zu mild. Fuenf Quintile je Horizont; bei der
        # Groessentrennung fuenf Quintile je Klasse, also ein Vielfaches. Wer
        # das nicht mitzaehlt, prueft dieselbe Hypothese fuenfmal zum alten
        # Preis und findet mit Sicherheit irgendeine Schicht, die haelt.
        if args.groessentrennung:
            z_tests = len(args.horizont) * args.klassen * 5
        else:
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

            if args.groessentrennung:
                begonnen = time.time()
                geschichtet = nettoemission_nach_groesse(
                    db, horizont=horizont, panel=panel,
                    klassen=args.klassen, z_tests=z_tests)
                _schichttabelle(geschichtet)
                print(f"\n  (Groessentrennung in "
                      f"{_dauer(time.time() - begonnen)})")

                # Die Jahrespruefung JE SCHICHT — die Kombination der beiden
                # Filter, an denen bisher alles gestorben ist. Der Querschnitt
                # allein schliesst nicht aus, dass eine einzelne Klasse das
                # Jahresergebnis traegt.
                begonnen = time.time()
                print(f"\n  {'#' * 68}")
                print("  JAHRESSTABILITAET JE GROESSENKLASSE")
                print(f"  {'#' * 68}")
                stabil = nettoemission_jahresstabilitaet_nach_groesse(
                    db, horizont=horizont, panel=panel, klassen=args.klassen)
                _jahresschichttabelle(stabil)
                print(f"\n  (Jahrespruefung je Schicht in "
                      f"{_dauer(time.time() - begonnen)})")
                continue

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
