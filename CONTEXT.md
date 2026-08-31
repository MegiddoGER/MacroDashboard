# CONTEXT.md — Arbeitsstand Signal-Engine

_Stand: 2026-08-31 · auf `9995db0` folgend · Branch `main`_

Übergabedatei für eine frische Claude-Session. Sie beantwortet drei Fragen:
**Was ist erledigt, was ist offen, und was darf nicht noch einmal neu hergeleitet
werden.** Vollständige Fassung mit Belegen und Zahlen:
<https://claude.ai/code/artifact/0dbcfa21-4049-4568-800b-edfc83b2f3cb>

---

## 0. Zuerst lesen — drei Dinge, die schiefgehen

### a) Arbeitsbaum gegen HEAD prüfen, BEVOR Quellcode gelesen wird

```
git status && git diff HEAD --stat
```

Der Arbeitsbaum lag am 2026-08-30 **454 Zeilen hinter HEAD** — `gate.py` gelöscht,
`SCORE_VERSION` von 2.0.0 auf 1.0.0 zurückgerollt. Wer die Dateien für aktuell
hält, baut bereits committete Arbeit neu. Genau das ist passiert und hat eine
ganze Sitzung gekostet.

Liegt der Baum zurück: **nicht eigenmächtig wiederherstellen.** Erst fragen.
`git stash push -- <pfade>` ist rücknehmbar, `git checkout HEAD -- <pfade>` nicht.
Der damalige Rollback liegt in `stash@{0}`.

### b) `.gitignore` — repariert, Historie noch belastet

Commit `6f2f3db` hatte die Regeln `*.db-wal` und `*.db-shm` aus `.gitignore`
entfernt und im selben Zug eine **37,3 MB große WAL-Datei** eingecheckt.
`1a61cf5` hat beide Regeln wiederhergestellt und die Dateien aus dem Index
genommen — **laufende Commits sind wieder sicher.**

Offen bleibt: die 37,3 MB liegen dauerhaft in der Git-Historie, und
`SIGNAL_ENGINE.md` (220 Zeilen Doku) wurde in `6f2f3db` gelöscht. Ob die
Historie bereinigt wird (`filter-repo`), ist eine Entscheidung des Besitzers —
Historie umschreiben nie ungefragt.

Vor jedem Commit trotzdem prüfen, dass die beiden Regeln noch in `.gitignore`
stehen: sie sind schon einmal unbemerkt verschwunden.

### c) Es wird direkt auf `main` gearbeitet — keinen Zweig anlegen

Stehende Anweisung des Besitzers: Pushes gehen auf `main`. Seit `52f5795` ist
das auch der ausgecheckte Zweig, `git push` genügt.

**Keinen Feature-Branch anlegen.** Eine frühere Session hatte
`signal-engine-overhaul` erzeugt und dafür die Umleitung
`git push origin <branch>:main` gebraucht. Das hat den Besitzer wiederholt in
die Irre geführt: Commits landeten auf dem Zweig statt auf `main`, und Gits
Fehlermeldung schlug jedes Mal `--set-upstream origin signal-engine-overhaul`
vor. Der Zweig existierte nie auf GitHub und ist gelöscht.

Der damalige Grund für die Umleitung — ein Arbeitsbaum voller fremder gestagter
Arbeit, der einen `checkout main` gestört hätte — besteht nicht mehr. Vor einem
Zweigwechsel trotzdem `git status` prüfen und nur die Dateien der jeweiligen
Änderung committen.

---

## 1. Worum es geht

MacroDashboard misst mit der Snapshot-Engine, ob die eigenen Empfehlungen
eintreffen. Ziel des Besitzers: daraus **automatisch** bessere Analysen ableiten.

Datenbestand: **88.033 Snapshots**, **256.705 ausgewertete Outcomes**,
**611 Ticker**, Horizonte 7/30/90 Tage. Davon 86.926 HISTORISCH (Backfill),
1.107 LIVE.

---

## 2. Der zentrale Befund — nicht neu herleiten

**Gewicht ist nicht Einfluss.** Im historischen Modus normalisieren die Gewichte
auf trend 0,277 / volume 0,185 / **oscillator 0,538**. Der Oszillator hat die
Mehrheit des Gewichts, aber nicht der Varianz: RSI und Bollinger feuern nur an
Extremen (**11 %** der Snapshots), Trend und Volumen sind auf **100 %** der
Snapshots mit ±1 gesättigt. Der Composite folgt daher Trend und Volumen,
unabhängig von der Gewichtung.

Belegt durch:

| Confidence-Band | trend+vol | oscillator | gemessener Vorsprung |
|---|---|---|---|
| 0–29 VERKAUF | 84 % | 16 % | −5,8 pp **signifikant** |
| 30–44 VERKAUF | 85 % | 15 % | −2,2 pp **signifikant** |
| 60–74 KAUF | 98 % | 2 % | −1,4 pp **signifikant** |
| 75–100 KAUF | 51 % | 49 % | +0,5 pp nicht signifikant |

Korrelationen der Kategorie-Scores (n = 40.000):
`trend ↔ volume +0,553` · `volume ↔ oscillator −0,599` · `trend ↔ oscillator −0,276`

**Die volume-Kategorie misst kein Volumen.** VWMA = Momentum(20), OBV-Slope =
Momentum(20), POC = Momentum(252). Sechs Momentum-Messungen, drei davon als
Order-Flow etikettiert. Deshalb waren alle Volumen-Indikatoren in *beiden*
Richtungen negativ.

**Isoliert trägt der Oszillator echten Vorsprung** (30 Tage, HISTORISCH,
Basisrate 55,5 / 44,5):

```
osc ≥ +0.50  (long)             n=5154   eff=1683  +3.2 pp ±2.4  SIGNIFIKANT
osc ≥ +0.75  (long)             n=1041   eff= 340  +5.4 pp ±5.2  SIGNIFIKANT
osc ≥ +0.50 UND trend ≤ −0.50   n=2452   eff= 800  +4.8 pp ±3.4  SIGNIFIKANT
osc ≤ −0.50  (short)            n=9134   eff=2983  +0.7 pp ±1.8  Rauschen
Gesamtuniversum (Kontrolle)     n=83606  eff=27311 +0.0 pp ±0.6  Rauschen
```

Der Vorteil ist **long-only**. Die Short-Seite ist auf jeder Schwelle Rauschen.

---

## 2a. Was die Train/Holdout-Trennung davon übrig lässt

Die Zahlen in §2 stammen aus dem **Gesamtbestand**. Auf dem Trainingsteil allein
(30 Tage, HISTORISCH, Basisrate 54,8 gegen 55,5) sieht es anders aus:

| Konstellation | n | eff | Vorsprung | |
|---|---|---|---|---|
| `osz ≥ 0.50` allein (der Befund aus §2) | 3.503 | 1.144 | +2,4 pp ±2,9 | **Rauschen** |
| `osz ≥ 0.75` allein | 725 | 236 | +6,2 pp ±6,2 | hauchdünn signifikant |
| `osz ≥ 0.50` UND `conf ≥ 60` — **das Gate** | 1.396 | 456 | −0,3 pp ±4,6 | **Rauschen** |
| `osz ≥ 0.50` UND `conf < 60` — Beförderung | 2.107 | 688 | +4,2 pp ±3,7 | signifikant |

Drei Schlüsse, die nicht neu hergeleitet werden müssen:

1. **Der Befund `osz ≥ 0.50: +3,2 pp` hält nicht.** Er war nur auf dem
   Gesamtbestand signifikant, wo die größere Stichprobe die Fehlerspanne
   schrumpfen lässt. Auf der Hälfte der Daten ist er Rauschen. Genau dafür
   existiert die Trennung.
2. **Der sperrende Zweig des Gates hat nie funktioniert** — auch in-sample
   nicht (+2,1 pp ±3,7). Die durchgelassene Gruppe schlägt die gesperrte nicht.
3. **Der Effekt sitzt im befördernden Zweig**, also im Mean-Reversion-Setup bei
   NIEDRIGER Confidence — nicht im Sperren hoher Confidence.

Die Schwellensuche über 13 Kandidaten (0,20–0,80) fand **keine** Schwelle, die
sich von Zufall unterscheiden ließe; real sind es nur 3 unterscheidbare Tests,
weil 0,35–0,65 dieselbe Zeilenmenge auswählen. Der Holdout (22.529 Snapshots)
ist deshalb weiterhin **unangetastet**.

---

## 2b. Was die Marktbereinigung davon übrig lässt

Seit P1-04 trägt jedes Outcome die Rendite seines Handelsplatz-Index über
DASSELBE Fenster (`snapshot_engine/benchmark.py`). Der Bestand ist
nachgetragen: **256.705 von 256.705 ausgewerteten Outcomes, Abdeckung 100 %**
(S&P 216.138 · DAX 40.114 · CAC 447 · SMI 3 · KOSPI 3), null Zeilen ohne
Indexkurs. Damit lässt sich zum ersten Mal trennen, was Signalqualität war und
was Marktphase — und das Ergebnis kehrt die bisherige Deutung um
(30 Tage, HISTORISCH):

| Signal | n | absolute Quote | gegen den Markt | |
|---|---|---|---|---|
| KAUF | 32.001 | 54,3 % | 47,4 % (−2,6 pp) | **signifikanter Rückstand** |
| VERKAUF | 19.439 | 41,2 % | 50,8 % (+0,8 pp) | **Rauschen** |

Alle Signale zusammen, je Horizont:

| Horizont | absolut (ggü. Basisrate) | gegen den Markt (ggü. 50) | mittlere Überrendite |
|---|---|---|---|
| 7 Tage | 50,4 % (−0,3 pp, Rauschen) | 50,1 % (+0,1 pp, Rauschen) | +0,03 pp |
| 30 Tage | 49,3 % (−2,1 pp, signifikant) | 48,7 % (−1,3 pp, signifikant) | −0,06 pp |
| 90 Tage | 51,0 % (−1,1 pp, signifikant) | 48,2 % (−1,8 pp, signifikant) | +0,02 pp |

Drei Schlüsse, die nicht neu hergeleitet werden müssen:

1. **Die Kaufsignale waren nie gut.** Ihre 54,3 % waren Marktdrift; gegen den
   Index liegen sie signifikant zurück. Wer nur die absolute Quote sah, hielt
   ein unterdurchschnittliches Signal für ein brauchbares.
2. **Die Verkaufssignale waren nie schlecht.** Ihre 41,2 % entstanden gegen
   einen steigenden Markt; bereinigt sind sie ein Münzwurf. Die Short-Seite ist
   damit nicht kaputt, sondern nur ohne Vorsprung — ein anderer Befund als
   bisher angenommen.
3. **Im Aggregat gibt es kein Alpha.** Die mittlere Überrendite liegt auf allen
   drei Horizonten bei rund null.

Zwei Festlegungen dazu, die nicht wieder aufgerollt werden müssen:

- **Die Nullhypothese der Marktquote ist 50**, nicht `anteil_steigend`. Der
  Index hat die Marktbewegung je Beobachtung bereits herausgerechnet; eine über
  den Gesamtbestand gemittelte Basisrate wäre danach doppelt gezählt.
- **Der Index richtet sich nach dem Handelsplatz, nicht nach dem Sitz des
  Unternehmens.** Die Überrendite ist eine Differenz zweier Prozentzahlen und
  nur dann sauber, wenn beide dieselbe Währung messen. Ein unbekanntes Suffix
  bekommt deshalb bewusst KEINEN Index: ein falscher wäre eine als Alpha
  getarnte Wechselkursbewegung, und die fiele später niemandem mehr auf.

---

### Was dieselbe Bereinigung in den übrigen Auswertungen sichtbar macht

Alle Zahlen unten: 30 Tage, HISTORISCH, **Gesamtbestand** — nicht auf dem
Trainingsteil gerechnet. Für eine Entscheidung müssten sie dort wiederholt
werden; als Diagnose reichen sie.

**Die Confidence-Kurve überlebt die Bereinigung nicht:**

| Confidence-Band | n | absolut | gegen den Markt |
|---|---|---|---|
| 0–29 VERKAUF | 5.643 | 38,7 % | 49,1 % (−0,9 pp, Rauschen) |
| 30–44 VERKAUF | 19.344 | 42,3 % | 51,5 % (+1,5 pp, Rauschen) |
| 60–74 KAUF | 30.029 | 54,1 % | 47,3 % (−2,7 pp, **signifikant**) |
| 75–100 KAUF | 1.972 | 56,3 % | 48,6 % (−1,4 pp, Rauschen) |

Absolut steigt die Kurve sauber monoton (38,7 → 42,3 → 54,1 → 56,3) und sieht
nach einer gut kalibrierten Engine aus. Gegen den Markt bleibt davon nichts:
49,1 → 51,5 → 47,3 → 48,6. Genau davor warnt der Docstring von
`kalibrierung.py` seit jeher — in einem steigenden Markt erzeugt schon die
Aufwärtsdrift eine steigende Kurve, weil niedrige Confidence Verkaufssignale
sind und hohe Kaufsignale. Jetzt ist es gemessen statt vermutet.

**Beide Signalrichtungen wählen Titel, die hinter dem Index bleiben:**

| Kategorie | Richtung | n | absolut | gegen den Markt |
|---|---|---|---|---|
| trend | bullisch | 196.888 | 54,7 % | 47,8 % (−2,2 pp, **signifikant**) |
| volume | bullisch | 151.293 | 54,7 % | 48,0 % (−2,0 pp, **signifikant**) |
| oscillator | bullisch | 6.816 | 58,9 % | 48,4 % (−1,6 pp, Rauschen) |
| trend | bearisch | 144.281 | 43,3 % | 51,6 % (+1,6 pp, **signifikant**) |
| volume | bearisch | 107.430 | 43,3 % | 51,9 % (+1,9 pp, **signifikant**) |
| oscillator | bearisch | 12.123 | 45,2 % | 51,5 % (+1,5 pp, Rauschen) |

Was die Indikatoren bullisch nennen, bleibt hinter dem Index zurück — und was
sie bearisch nennen, ebenfalls. Die bearische Seite liegt damit richtig, die
bullische systematisch falsch. Das verschärft §2: dort war die
Volumen-Kategorie „in beiden Richtungen negativ"; marktbereinigt ist sie
bearisch signifikant **positiv** und nur bullisch negativ.

**Der befördernde Zweig des Gates hält der Bereinigung nicht stand:**

| Gate-Gruppe | n | absolut | gegen den Markt |
|---|---|---|---|
| Empfohlen — Confidence + Oszillator | 2.136 | 57,7 % (+2,1 pp, Rauschen) | 48,7 % (−1,3 pp, Rauschen) |
| Empfohlen — Mean-Reversion-Setup | 3.018 | 59,5 % (+3,9 pp, **signifikant**) | 49,4 % (−0,6 pp, Rauschen) |
| Gesperrt — Confidence ohne Oszillator | 28.814 | 54,0 % (−1,5 pp, signifikant) | 47,9 % (−2,1 pp, signifikant) |

§2a hielt fest: „Der Effekt sitzt im befördernden Zweig." Gegen den Markt ist
auch dieser Effekt weg (+3,9 pp → −0,6 pp, nicht mehr signifikant). Die
Mean-Reversion-Beförderung, die in Score 2.1.0 als einziger Gate-Teil erhalten
blieb, steht damit ohne belegten Vorsprung da — siehe P1-08b in §4 A.

---

## 3. Erledigt — nicht noch einmal bauen

| Was | Wo |
|---|---|
| Sektor-Normalisierung (yfinance vs. GICS) | `services/sector_map.py` |
| Score-Versionierung, aktuell **2.1.0** | `services/scoring.py`, Changelog im Kopf |
| Split-sichere Outcome-Basis | `snapshot_engine/snapshot_service.py` |
| Kalibrierungs-Fazit gegen die Basisrate | `snapshot_engine/auswertung/kalibrierung.py` |
| Fehlerspannen + Signifikanz | `snapshot_engine/auswertung/basis.py` |
| Vermischungswarnung LIVE/HISTORISCH | `snapshot_engine/auswertung/kennzahlen.py` |
| Oszillator-Gate (Score 2.0.0) | `snapshot_engine/auswertung/gate.py` |
| Mean-Reversion-Setup (Beförderung) | `services/scoring.py` |
| Stochastic messbar gemacht | `snapshot_engine/snapshot_service.py` |
| MACD auf `Granularitaet.INFO` | `snapshot_engine/models.py` |
| VWMA/POC: kein Bearish ohne Aussage | `services/scoring.py` (Version 1.1.0) |
| PC-01 Trend-Guard bei fehlender SMA 200 | `services/scoring_engine_v2.py` |
| PC-02 `data_quality` als Qualifier | `services/scoring_engine_v2.py` |
| PC-03 RSI-Klippe entfernt | `services/scoring_engine_v2.py` |
| **P3-03 Positionspfad instrumentiert** | `snapshot_engine/position_snapshot.py` |
| **P1-05 Train/Holdout-Trennung** | `snapshot_engine/auswertung/holdout.py` |
| **P1-07 Schwellensuche auf dem Trainingsteil** | `snapshot_engine/auswertung/schwellensuche.py` |
| **P1-04 Marktrendite je Outcome** | `snapshot_engine/benchmark.py` |
| **P1-04 Bestandsnachtrag (256.505 Zeilen)** | `snapshot_engine/benchmark_backfill.py` |
| **P1-04 Überrendite in den Kennzahlen** | `auswertung/basis.py`, `auswertung/kennzahlen.py` |
| **P1-04b Überrendite in Kalibrierung, Indikatoren, Gate** | `auswertung/kalibrierung.py`, `indikator_stats.py`, `gate.py` |
| **P1-04 auf der Oberfläche sichtbar** | `templates/pages/signal_quality.html` (vier Tabellen) |

**Wichtig:** Alle 88.033 Bestands-Snapshots tragen `score_version` 1.0.0 — es
gibt weder welche mit 2.0.0 noch mit 2.1.0. Der sperrende Zweig hat also nie
einen einzigen gespeicherten Snapshot beeinflusst; er wirkte ausschließlich auf
die angezeigte Empfehlung. Neue Snapshots ab dem nächsten Scheduler-Lauf tragen
2.1.0.

---

## 4. Offen — nach Wirkung geordnet

### A. Blockiert das eigentliche Ziel (automatische Verbesserung)
- ~~**P1-05** kein Train/Holdout-Split~~ → erledigt, siehe §3. Grenze steht fest
  auf **2025-04-20**, Sperrzone 90 Tage, Holdout ab **2025-07-19**. Belegung
  (HISTORISCH): Training 59.065 · Sperrzone 5.332 · Holdout 22.529. Die Grenze
  liegt in der `Setting`-Tabelle und wandert nicht mit dem Bestand mit.
- ~~**P1-07** Schwelle auf dem Trainingsteil neu bestimmen~~ → durchgeführt,
  Ergebnis **negativ** (siehe §2a). Es gibt keine belegbare Gate-Schwelle;
  `gate.SCHWELLE_BESTIMMT_AM` bleibt daher `None`. Der Holdout wurde **nicht**
  angefasst — es gab nichts zu bestätigen.
- ~~**P1-08** über das Gate entscheiden~~ → entschieden und umgesetzt: der
  **sperrende Zweig ist entfallen** (SCORE_VERSION **2.1.0**), die
  Mean-Reversion-Beförderung bleibt. Eine hohe Confidence ohne
  Oszillator-Deckung wird nicht mehr zu „Kein Einstieg" herabgestuft; der
  Oszillator erscheint dort nur noch als Hinweis in der Checkliste. Wirkung:
  spürbar mehr Kaufempfehlungen als unter 2.0.0.
- ~~**P1-04** keine Benchmark-Rendite je Outcome~~ → erledigt, siehe §2b
  und §3. Jedes ausgewertete Outcome trägt `benchmark_ticker` und
  `benchmark_return`; die Kennzahlen weisen Marktquote, mittlere
  Überrendite, Fehlerspanne und Abdeckung neben der absoluten Quote aus.
  Die absolute Quote bleibt bewusst stehen — sonst verlören alle in §2
  und §2a belegten Zahlen ihren Bezug, und gerade die Differenz zwischen
  beiden ist die Aussage.
- ~~**P1-04b** die Überrendite steht nur in `basis.py` und `kennzahlen.py`~~
  → erledigt. `kalibrierung.py`, `indikator_stats.py` (beide Leaderboards) und
  `gate.py` rechnen jetzt marktbereinigt; die Befunde stehen in §2b. Zwei
  Korrekturen an der damaligen Aufzählung:
  - `holdout.py` rechnet **gar keine** Trefferquoten — es liefert nur Grenze,
    Filter und Zugriffszähler. Dort war nichts zu verdrahten.
  - `risk_adjusted.py` bleibt **absichtlich** absolut. Es speist
    Kelly-Positionsgrößen und Journal-Statistik, also tatsächlich realisierte
    Gewinne und Verluste. Eine Überrendite lässt sich nicht ausgeben, solange
    nicht zugleich der Index geshortet wird. Die Begründung steht im
    Modul-Docstring, damit sie nicht als vergessene Lücke wiederkehrt.
- ~~**P1-04c** die Überrendite ist nirgends sichtbar~~ → erledigt.
  `/signals` zeigt sie in allen vier Tabellen (Horizonte, Richtungssignal,
  Gate-Gruppen, Confidence-Kalibrierung) als Spaltenpaar „Quote vs. Markt" und
  „Vorsprung vs. Markt", mit Fehlerspanne und Abdeckung im Tooltip. Wie beim
  absoluten Vorsprung wird innerhalb der Fehlerspanne **nicht** eingefärbt.
- **P1-08b (neu)** über die Mean-Reversion-Beförderung entscheiden. Sie blieb
  in Score 2.1.0 als einziger Teil des Gates erhalten, weil sie absolut +3,9 pp
  brachte; marktbereinigt sind es −0,6 pp und nicht signifikant (§2b). Vor
  einer Entscheidung auf dem **Trainingsteil** nachrechnen — die Zahlen in §2b
  stammen aus dem Gesamtbestand.
- **P1-06** ein 30-Tage-Takt für alle Kategorien, unabhängig von der Signal-Halbwertszeit
- **P1-03** Backfill kennt kein Sentiment, misst also ein anderes System als das laufende (Designentscheidung offen)

### B. Die strukturelle Ursache (Gate umgeht sie, löst sie nicht)
- **BC-01/02/03 + P2-04** sechs korrelierte Momentum-Messungen dominieren drei meist stille Oszillator-Slots. Das Gate filtert obenauf; der Composite darunter bleibt fehlkomponiert. **Größter offener Posten, architektonisch.**

### C. Positionspfad — Messung läuft, Auswertung fehlt
- ~~**P3-03** erzeugt keine Snapshots~~ → erledigt, siehe §3. Ab jetzt schreibt
  jede Positionsanalyse einen Snapshot mit `analyse_modus = BESTEHENDE_POSITION`.
  **Der Bestand ist aber leer:** die ersten Outcomes werden erst 7 Tage nach dem
  ersten erfassten Aufruf fällig, belastbare Zahlen dauern entsprechend länger.
- **P3-05 (neu)** keine Auswertungsfläche für `BESTEHENDE_POSITION`. Die Daten
  laufen auf, gelesen werden sie noch nirgends — `/signals` und alle Abfragen in
  `auswertung/` filtern bewusst auf `NEUE_POSITION`. Nächster Schritt, sobald
  genug Zeilen fällig geworden sind.
- **P3-01** keine Stop-Historie → Ratchet wirkungslos, R-Multiple/MAE/MFE unberechenbar
- **P3-02** SHORT-Pfad unerreichbar (`side = PositionSide.LONG` fest verdrahtet)
- **PC-04** ADX wird hier gerichtet gewertet — genau umgekehrt zur Entry-Engine, die ihn als Info führt
- **PC-06** drei Metriken werden berechnet und nie gelesen
- **P3-04** Entry- und Positionsscore sind keine vergleichbaren Größen

### D. Analyse-Substanz
- **P2-01** Sektor-Bewertungsmodelle erreichen den Score nicht — generischer DCF läuft auf Banken, REITs, Biotech
- **P2-02** Cross-sectional Momentum fehlt ganz (robusteste Anomalie überhaupt)
- **P2-03** ADX wird berechnet und verworfen; gehört als Regime-Gate verwendet
- **P2-05** Fundamentalblock (0,30) wird auf 7–90 Tagen gemessen, passt nicht zur Halbwertszeit
- **P2-06** fehlende Signale: PEAD (Ansatz existiert, <1 % Abdeckung), Analysten-Revisionen, relative Stärke je Sektor, Short Interest, Insider-Cluster, Accruals

### E. Präzision (2 von 9 erledigt)
- **P4-04** absolute statt volatilitätsrelative Schwellen — RSI 30 bedeutet bei Versorger und Biotech Verschiedenes
- **P4-03** Währungen (Xetra/US) werden nie verrechnet
- **P4-05** Nenner nahe null über die gesamte Kennzahlenfläche
- **P4-06/07/08/09** illiquide Reihen, still ausscheidende Delistings (Survivorship), Kursgrößenordnungen, ADR-Doppelzählung

### F. Werkzeuge — keines gebaut
`signal-researcher`, `market-data-integrity`, `sector-models`, `snapshot-schema`
(Spezifikation im Artifact). B, D und E stützen sich darauf; bisher wurde diese
Arbeit inline erledigt, was sie langsam und einmalig statt wiederholbar macht.

---

## 5. Empfohlener nächster Schritt

**BC-01/02/03 — die Komposition des Composites** (§4 B). Die Messfläche steht
jetzt: alles, was eine Trefferquote ausweist, weist sie auch gegen den Markt
aus. Was sie zeigt, ist eindeutig und trifft die Architektur, nicht die
Kalibrierung — die bullische Seite aller drei Kategorien liegt gegen den Index
signifikant zurück, die bearische leicht vorn (§2b). Sechs korrelierte
Momentum-Messungen dominieren drei meist stille Oszillator-Slots; die
volume-Kategorie misst kein Volumen (§2). Keine Gewichtung repariert das, und
DX-01 zeigt, dass Gewichtstuning an dieser Architektur ohnehin eine Decke hat.

**Vorher billig mitzunehmen: P1-08b.** Die Mean-Reversion-Beförderung ist der
einzige noch aktive Gate-Teil und hat marktbereinigt keinen Vorsprung mehr. Das
auf dem Trainingsteil nachzurechnen kostet wenig und entscheidet, ob Score
2.1.0 einen Zweig trägt, der nichts beiträgt.

**Nicht** mit dem Vorschlagspanel für Gewichte anfangen: DX-01 zeigt, dass
Gewichtstuning an dieser Architektur eine Decke hat.

**Den Holdout nicht anfassen**, solange keine auf dem Training bestimmte
Aussage vorliegt, die er bestätigen soll. Er steht bei **0 Zugriffen**; der
Zähler ist auf `/signals` sichtbar. Wer nach jeder Änderung erneut misst und
die beste Variante behält, hat ihn zum Trainingsset gemacht — nur langsamer.

---

## 6. Verifikation (es gibt keine CI)

```
py -m pytest -q                                   # 130 Tests
py -m mypy <geänderte Dateien>                    # ad hoc, keine Konfiguration im Repo
py -c "import warnings; warnings.filterwarnings('ignore'); from fastapi.testclient import TestClient; import main; c=TestClient(main.app); c.__enter__(); [print(c.get(u).status_code, u) for u in ['/','/signals','/signals/indikatoren','/signals/backfill','/analysis','/screener','/watchlist','/journal','/backtesting','/sectors','/economy','/settings','/lexicon','/sources','/directory']]"
```

Alle Routen müssen 200 liefern. Skills unter `.claude/skills/`: `ship-check`,
`quant-testing`, `observability`, `new-data-source`, `new-surface`,
`design-brief`. Agenten unter `.claude/agents/`: `quant-reviewer`, `test-author`,
`data-source-scout`, `ui-designer`. Übersicht in `.claude/README.md`.

---

## 7. Zwei Konventionen

- **Score-Version erhöhen**, wenn aus denselben Kursdaten ein anderer `cat_score`
  entstünde. **Nicht** bei reinen Gewichtsänderungen — `neugewichtung.py` kann
  die Confidence aus gespeicherten `cat_scores` exakt neu rechnen. Es gibt zwei
  davon: `scoring.SCORE_VERSION` (Einstieg) und
  `scoring_engine_v2.POSITION_SCORE_VERSION` (Position). Beide landen im Feld
  `score_version`; unterschieden werden sie über `analyse_modus`.
- **Zahlen, die eine Änderung rechtfertigen sollen, gehören auf den Holdout**
  (`teil=HOLDOUT`). Und: rückwirkend gilt nicht — ein Parameter, der älter ist
  als die Grenze, hat die Holdout-Zeilen gesehen. `holdout_rueckwirkend()`
  benennt diesen Fall; er darf nie als Out-of-Sample-Beleg auftreten.
- **Nach `analyse_modus` filtern**, sobald eine Abfrage Trefferquoten,
  Kalibrierung oder Indikator-Statistik berechnet. `NEUE_POSITION` und
  `BESTEHENDE_POSITION` sind zwei Bewertungssysteme in einer Tabelle: andere
  Confidence-Bedeutung, andere Herkunft des Richtungssignals, andere Einheit in
  `beitrag_numeric`. Ungefiltert mitteln sie beides zusammen. Einzige gewollte
  Ausnahme ist `outcomes_nachtragen` — der Nachtrag ist reine Kursarbeit und
  gilt für jede fällige Zeile.
- **Kommentare und Commits auf Deutsch.** Diese Datei und `CLAUDE.md` sind die
  Ausnahme (Meta-Dokumentation, wie `REVIEW.md`).
