# CONTEXT.md — Arbeitsstand Signal-Engine

_Stand: 2026-09-01 · auf `1782d55` folgend · Branch `main`_

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

Datenbestand (nach dem 10-Jahres-Backfill vom 2026-09-01): **274.940
Snapshots**, **810.838 ausgewertete Outcomes**, **611 Ticker**, Horizonte
7/30/90 Tage. Davon 273.831 HISTORISCH über **2017-04 bis 2026-08**, 1.109
LIVE. Datenbank rund 970 MB.

**Versionsmischung im Bestand:** 88.035 Snapshots tragen `score_version` 1.0.0
(Ur-Backfill), 186.905 tragen 2.2.0 (Nachlauf). Dazwischen liegt 1.1.0 mit
echten `cat_score`-Änderungen an VWMA und POC. Für kursbasierte Auswertungen
wie Momentum ohne Belang; Indikator- und Kategorie-Leaderboards mischen ab
jetzt zwei Bewertungssysteme und müssen getrennt werden. Die
Vermischungswarnung in `kennzahlen.py` schlägt darauf an.

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
Indexkurs.

### Der Bezugspunkt ist 48 %, nicht 50 % — daran hängt alles Weitere

Die naheliegende Annahme lautet: der Index sei je Beobachtung bereits
abgezogen, also liege ein Ratender in der Hälfte der Fälle vorn. Sie ist
falsch, und sie stand zwischenzeitlich als `MARKT_NULLHYPOTHESE = 50` im Code.
Gemessen (HISTORISCH, Bewegung ≥ 0,3 pp):

| Horizont | Beobachtungen | schlagen ihren Index | mittlere Überrendite |
|---|---|---|---|
| 7 Tage | 79.944 | **48,1 %** | −0,04 pp |
| 30 Tage | 83.199 | **48,1 %** | +0,05 pp |
| 90 Tage | 81.291 | **46,1 %** | −0,05 pp |

Mittelwert null und Anteil unter 50 zugleich ist kein Widerspruch, sondern die
**Marktbreite**: ein kapitalgewichteter Index wird von wenigen großen Titeln
getragen. Der Median-Titel bleibt zurück, einige wenige ziehen den Mittelwert
auf null. Gegen 50 gerechnet sieht deshalb JEDE Auswahl von Einzeltiteln nach
einem systematischen Rückstand von rund 2 pp aus — auch eine zufällige.

Die Marktquote braucht darum ihre eigene Basis, genau wie die absolute
Trefferquote ihre `basis_trefferquote` hat: `anteil_schlaegt_markt()` misst sie
unbedingt über die gesamte Grundgesamtheit, `markt_basis()` gewichtet sie nach
der Richtungsmischung — für eine Short-Beobachtung ist der Bezugspunkt der
Anteil, der den Index NICHT schlägt.

**Achtung bei älteren Notizen und Commit-Texten:** alle Marktzahlen aus den
Commits `9995db0` und `0e9c516` sind gegen 50 gerechnet und weisen rund 2 pp
Rückstand zu viel aus. Die Tabellen unten sind korrigiert.

### Was nach der Korrektur übrig bleibt: nichts

Je Richtungssignal (30 Tage, HISTORISCH, Gesamtbestand):

| Signal | n | absolut | gegen den Markt | Basis | |
|---|---|---|---|---|---|
| KAUF | 32.001 | 54,3 % | 47,4 % | 48,1 % | −0,7 pp, **Rauschen** |
| VERKAUF | 19.439 | 41,2 % | 50,8 % | 51,9 % | −1,2 pp, **Rauschen** |

Alle Signale zusammen, je Horizont:

| Horizont | absolut (ggü. Basisrate) | gegen den Markt (ggü. Marktbasis) |
|---|---|---|
| 7 Tage | 50,4 % (−0,3 pp, Rauschen) | 50,1 % (+0,6 pp ±0,4, signifikant) |
| 30 Tage | 49,3 % (−2,1 pp, signifikant) | 48,7 % (−0,9 pp ±0,8, signifikant) |
| 90 Tage | 51,0 % (−1,1 pp, signifikant) | 48,2 % (−0,9 pp ±1,3, Rauschen) |

**Und je Indikator — das ist der eigentliche Befund** (30 Tage, HISTORISCH,
Marktbasis 48,1 % long / 51,9 % short):

| Indikator | bullisch | bearisch |
|---|---|---|
| Trend (SMA 200) | −0,5 pp | −0,6 pp |
| SMA-Cross (20/50) | −0,3 pp | −0,3 pp |
| FVG (Fair Value Gap) | −0,5 pp | −0,7 pp |
| VWMA (20T) | +0,2 pp | +0,3 pp |
| OBV Trend | −0,1 pp | −0,1 pp |
| Volumen-Cluster (POC) | −0,3 pp | −0,5 pp |
| RSI (14) | +0,4 pp | −0,4 pp |
| Bollinger Bänder | +0,1 pp | −0,4 pp |

**Keine einzige dieser 16 Zeilen ist signifikant.** Dasselbe auf
Kategorie-Ebene: trend −0,3 / −0,3, volume −0,1 / −0,0, oscillator +0,3 / −0,4
— nichts davon von Zufall unterscheidbar. Die absoluten Quoten (54,8 % bullisch,
43 % bearisch) waren vollständig Marktrichtung plus Marktbreite.

Das ist ein Null-Befund auf dem **Gesamtbestand**, also in der konservativen
Richtung: eine Train/Holdout-Trennung könnte einen Vorsprung nur weiter
schrumpfen, nicht erzeugen. Der Holdout musste dafür nicht angefasst werden und
steht weiter bei **0 Zugriffen**.

### Die Confidence-Kurve trennt nicht

| Confidence-Band | n | absolut | gegen den Markt | Basis | |
|---|---|---|---|---|---|
| 0–29 VERKAUF | 5.643 | 38,7 % | 49,1 % | 51,9 % | −2,9 pp, **signifikant** |
| 30–44 VERKAUF | 19.344 | 42,3 % | 51,5 % | 51,9 % | −0,5 pp, Rauschen |
| 60–74 KAUF | 30.029 | 54,1 % | 47,3 % | 48,1 % | −0,8 pp, Rauschen |
| 75–100 KAUF | 1.972 | 56,3 % | 48,6 % | 48,1 % | +0,6 pp, Rauschen |

Absolut steigt die Kurve sauber monoton (38,7 → 42,3 → 54,1 → 56,3) und sieht
nach einer gut kalibrierten Engine aus. Marktbereinigt bleibt eine flache
Reihe, in der nur das unterste Band überhaupt aus dem Rauschen ragt — und zwar
mit negativem Vorzeichen. Genau davor warnt der Docstring von
`kalibrierung.py` seit jeher: in einem steigenden Markt erzeugt schon die
Aufwärtsdrift eine steigende Kurve, weil niedrige Confidence Verkaufssignale
sind und hohe Kaufsignale.

### P1-08b: die Beförderung ist entfallen

Auf dem **Trainingsteil** nachgerechnet, gegen die dortige Marktbasis:

| Horizont | n | absolut | gegen den Markt |
|---|---|---|---|
| 7 Tage | 2.033 | +4,9 pp, signifikant | +0,7 pp, Rauschen |
| 30 Tage | 2.107 | +4,2 pp, signifikant | −0,5 pp, Rauschen |
| 90 Tage | 2.147 | +6,5 pp, signifikant | +3,1 pp, Rauschen |

Absolut auf allen drei Horizonten signifikant, marktbereinigt auf keinem.
**Konsequenz: die Beförderung ist in Score 2.2.0 entfallen** (§3); die
Konstellation wird weiter erkannt und als Hinweis geführt.

Eine Auffälligkeit, bewusst nicht ausgedeutet: `durchgelassen` trägt auf
**7 Tagen** +4,9 pp und ist dort signifikant, auf 30 und 90 Tagen aber −2,7
und −0,6 pp. Ein Fund, der über drei Horizonte nur auf einem hält, ist eher
Mehrfachtest als Signal — und 7 Tage ist der Horizont mit den engsten
Fehlerspannen, weil dort keine Überlappungskorrektur greift.

---

## 2c. P2-02 — der erste Eingang, der etwas trägt

Querschnitts-Momentum rangt Titel gegeneinander statt gegen null: 12-1-Rendite
(zwölf Monate Rückschau, jüngster Monat ausgelassen), wöchentlich gerangt
**je Handelsplatz**. Die Trennung nach Handelsplatz ist dieselbe Entscheidung
wie bei `benchmark.py` — eine gemeinsame Rangliste über Xetra und US wiese eine
Dollarstärke als Momentum aus.

Auf dem **Trainingsteil** (HISTORISCH, jedes Dezil als long bewertet, Frage:
wie oft schlägt ein Titel dieses Rangs seinen Index?):

| Dezil | 7 Tage | 30 Tage | 90 Tage |
|---|---|---|---|
| D1 (schwächstes) | −2,1 pp **sig.** | −3,0 pp **sig.** | −4,4 pp |
| D2 | −1,6 pp **sig.** | −1,2 pp | −4,0 pp |
| D5 | −1,5 pp | −0,6 pp | −2,2 pp |
| D8 | +0,7 pp | +1,0 pp | +1,4 pp |
| D9 | +2,3 pp **sig.** | +1,1 pp | +4,7 pp |
| **D10 (stärkstes)** | **+4,9 pp sig.** | **+4,9 pp sig.** | **+9,3 pp sig.** |
| Spread D10−D1 | 7,1 pp | 7,9 pp | 13,7 pp |

Mittlere Überrendite von D10: +0,3 / **+1,54** / **+5,54** pp. Der Verlauf ist
auf allen drei Horizonten monoton steigend, das oberste Dezil überall
signifikant, und der Effekt wächst mit dem Horizont — die klassische
Momentum-Signatur. Auf dem Gesamtbestand dasselbe Bild (D10: +5,1 / +5,2 /
+9,7 pp).

Das ist nach §2b der **erste und bisher einzige Eingang mit einem
marktrelativen Vorsprung**. Zwei Eigenschaften machen ihn belastbarer als alles
zuvor Gemessene:

- **Kein getunter Parameter.** 12-1 ist die Lehrbuchform, a priori gewählt. Es
  gab keine Schwellensuche, also auch keine Mehrfachtest-Inflation — anders als
  beim Oszillator-Gate, dessen 0,50 aus denselben Daten stammte.
- **Der Verlauf trägt die Aussage, nicht eine Zelle.** Ein einzelnes
  herausragendes Dezil wäre verdächtig; zehn monoton steigende sind es nicht.

### Die Survivorship-Korrektur — ein Drittel des Effekts ist weg

**Gemessen, nicht mehr nur befürchtet.** Die Wikipedia-Komponententabelle trägt
eine Spalte `Date added`; **75 der 503 heutigen S&P-Mitglieder** sind erst nach
dem Backfill-Beginn (2022-03-16) aufgenommen worden. Beschränkt man die
Auswertung auf Beobachtungen, bei denen der Titel zum Snapshot-Zeitpunkt
bereits Mitglied war (Trainingsteil, nur US-Werte, damit die Titelmenge
vergleichbar bleibt):

| | 30 Tage | 90 Tage |
|---|---|---|
| alle Daten (n = 31.957) | D10 **+4,5 pp**, signifikant | D10 **+8,7 pp**, signifikant |
| erst ab Aufnahme (n = 29.607) | D10 **+2,9 pp**, *nicht signifikant* | D10 **+6,6 pp**, signifikant |

Es fallen nur **2.350 Beobachtungen weg (7,4 %)** — und sie nehmen rund ein
Drittel des Effekts mit. Genau wie erwartet trifft es ausschließlich das
oberste Dezil; D1 bleibt fast unverändert (−3,6 → −3,4 bzw. −4,9 → −4,3). Das
sind die spät aufgenommenen Gewinner, deren Vorgeschichte im Nachhinein
garantiert gut aussieht.

**Was davon übrig bleibt:** der 90-Tage-Effekt hält, der 30-Tage-Effekt fällt
unter die Signifikanzschwelle.

### Die verbleibende Hälfte: Ausschlüsse

Korrigiert ist nur die **Aufnahmen**-Hälfte. Titel, die nach schlechter
Entwicklung aus dem Index geflogen sind, fehlen weiterhin ganz — Wikipedia
führt die Änderungshistorie seit einem Seitenumbau nicht mehr, und in der
Datenbank sind sie nie gewesen.

Wichtig für die Einordnung: diese Hälfte wirkt **gegen** den Befund. Die
fehlenden Verlierer hätten D1 besetzt; dessen gemessene Quote ist dadurch zu
gut, der Spread also eher zu klein als zu groß. Die korrigierten Zahlen oben
sind damit eine faire bis konservative Schätzung — nicht eine geschönte.

### Auf zehn Jahren: der Effekt war ein einziges Regime

Der ursprüngliche Bestand begann 2022-03; mit zwölf Monaten Rückschau maß die
Momentum-Auswertung faktisch **ab 2023-03** — also fast genau die KI-Hausse.
Der 10-Jahres-Backfill (2017-04 bis 2026-08, 273.831 HISTORISCH-Snapshots)
macht sichtbar, was das wert war. Trainingsteil, 90 Tage, mit
Mitgliedschaftsfilter, je Regime:

| Regime | n | Marktbasis | D10 | D1 |
|---|---|---|---|---|
| 2018-19 normal, Q4-18-Einbruch | 18.950 | 53,4 % | **−7,7 pp signifikant** | +0,2 pp |
| 2020 COVID-Crash + Erholung | 13.376 | 48,9 % | −7,4 pp | **+11,9 pp signifikant** |
| 2021 Melt-up | 13.752 | 49,4 % | −5,9 pp | +2,2 pp |
| 2022 Bärenmarkt | 20.589 | 58,7 % | −3,0 pp | −3,1 pp |
| **2023-25 KI-Hausse** | 73.030 | 44,3 % | **+4,8 pp signifikant** | −1,4 pp |

Momentum trägt in **genau einem** von fünf Regimen. In 2020 kehrt es sich um:
das unterste Dezil liegt +11,9 pp vorn — der klassische Momentum-Crash, bei dem
die abgestraften Titel am stärksten zurückspringen.

Über den gesamten Trainingsteil 2018-2025 gepoolt bleibt nichts:

| Dezil | 30 Tage | 90 Tage |
|---|---|---|
| D1 | −1,1 pp | +1,2 pp |
| D5 | +0,6 pp | −0,2 pp |
| D9 | −0,2 pp | −0,2 pp |
| **D10** | **+0,2 pp** | **−0,8 pp** |

Keine einzige Zelle signifikant, n = 146.931. **P2-02 reiht sich damit in den
Null-Befund aus §2b ein.**

**Und der Holdout war richtig gespart.** Er beginnt am 2025-07-19 und liegt
damit mitten in dem einen Regime, in dem der Effekt existiert. Er hätte
bestätigt — und ein Regime-Artefakt wäre in den Score gewandert. Dass die
Fehlerspanne dort ohnehin größer war als der Effekt (±8,0 gegen +6,6 pp), war
der erste Grund, nicht zu messen; dieser hier ist der bessere.

### Wo der Eingang steht

Gemessen, **nicht** im Score. `services/cross_sectional_momentum.py` rechnet
Ränge, `snapshot_engine/auswertung/momentum.py` wertet sie aus; keine
Aufrufstelle in `scoring.py`. `normiert()` liefert die Skala [−1, +1], mit der
er sich als Kategorie-Score führen ließe — sobald die Entscheidung dafür
gefallen ist.

Die Ränge sind aus den Snapshot-Kursen gerechnet, nicht aus neuen Downloads:
der Backfill hat je Ticker EINE Reihe abgespielt, alle HISTORISCH-Kurse eines
Tickers teilen daher eine Anpassungsbasis. Nachgeprüft — von 86.333 aufeinander
folgenden Kurspaaren liegen 16 außerhalb von [0,6 · 1,6], und die sind sämtlich
echte Ereignisse (CVNA, SMCI, HelloFresh, Fiserv), keine Split-Brüche.

---

## 3. Erledigt — nicht noch einmal bauen

| Was | Wo |
|---|---|
| Sektor-Normalisierung (yfinance vs. GICS) | `services/sector_map.py` |
| Score-Versionierung, aktuell **2.2.0** | `services/scoring.py`, Changelog im Kopf |
| **P1-08b Mean-Reversion-Beförderung entfernt (2.2.0)** | `services/scoring.py`, `tests/test_scoring_gate.py` |
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
| **Marktbasis statt Nullhypothese 50** | `auswertung/basis.py` (`anteil_schlaegt_markt`, `markt_basis`) |
| **P2-02 Querschnitts-Momentum, gemessen** | `services/cross_sectional_momentum.py`, `auswertung/momentum.py` |
| **P3-02 Positionsseite erreichbar** | `services/scoring.py`, `tests/test_position_side.py` |
| **P4-07 Aufnahmedaten als Quelle** | `services/index_membership.py`, `cache_core.cached_sp500_aufnahmedaten` |
| **Analyse-Router protokolliert** | `routers/analysis.py` (drei stille Fehlerpfade) |

**Wichtig:** Alle 88.033 Bestands-Snapshots tragen `score_version` 1.0.0 — es
gibt weder welche mit 2.0.0 noch mit 2.1.0 noch mit 2.2.0. Weder der sperrende
Zweig noch die Beförderung hat je einen gespeicherten Snapshot beeinflusst;
beide wirkten ausschließlich auf die angezeigte Empfehlung. Neue Snapshots ab
dem nächsten Scheduler-Lauf tragen **2.2.0**.

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
- ~~**P1-08b** über die Mean-Reversion-Beförderung entscheiden~~ → entschieden
  und umgesetzt: die **Beförderung ist entfallen** (SCORE_VERSION **2.2.0**).
  Auf dem Trainingsteil trägt sie marktbereinigt auf keinem Horizont etwas
  (§2b). Damit steuert der Oszillator gar keine Empfehlung mehr — beide Zweige
  des Gates sind weg, der sperrende in 2.1.0, der befördernde in 2.2.0. Die
  Konstellation wird weiter erkannt (`mean_reversion_setup` bleibt gesetzt) und
  erscheint als Hinweis in der Checkliste. Wirkung: keine Kaufempfehlungen mehr
  aus dem unteren Confidence-Bereich. `tests/test_scoring_gate.py` hält beide
  Entscheidungen fest — es war bis dahin kein einziger Test auf `scoring.py`.
- **P1-06** ein 30-Tage-Takt für alle Kategorien, unabhängig von der Signal-Halbwertszeit
- **P1-03** Backfill kennt kein Sentiment, misst also ein anderes System als das laufende (Designentscheidung offen)

### B. Die strukturelle Ursache — Prämisse widerlegt, Umbau ausgesetzt
- **BC-01** (die volume-Kategorie misst kein Volumen: VWMA = Momentum(20),
  OBV-Slope = Momentum(20), POC = Momentum(252)) und **BC-03** (fünf von sechs
  Preis-Positions-Messungen feuern auf 100 % der Snapshots, RSI und Bollinger
  auf 11 %) sind **weiterhin wahr**. Es sind Aussagen über den Code, nicht über
  Vorsprünge, und die Sättigungszahlen stehen im Artifact.
- **BC-02 ist widerlegt.** Sie lautete: „die einzige Kategorie mit Vorsprung
  wird von der ohne gekippt" — Grundlage war der Oszillator-Vorsprung. Gegen
  den Markt hat der Oszillator keinen: +0,3 pp bullisch, −0,4 pp bearisch,
  beides Rauschen (§2b). Es gibt kein gutes Signal, das gerettet werden müsste.
- **P2-04** (die additive Form kann keine Interaktionen ausdrücken) stand auf
  demselben Beleg: „überverkauft gegen den Trend +4,8 pp". Diese Interaktion
  ist exakt die Mean-Reversion-Beförderung, die in 2.2.0 entfallen ist, weil
  marktbereinigt nichts von ihr bleibt.
- **Konsequenz: den Composite jetzt NICHT umbauen.** Eine andere Arithmetik
  über Eingänge, von denen keiner einen marktrelativen Vorsprung trägt, ordnet
  Nullen um. Der Umbau wird sinnvoll, sobald es einen Eingang gibt, der einen
  hat — siehe §5.

### C. Positionspfad — Messung läuft, Auswertung fehlt
- ~~**P3-03** erzeugt keine Snapshots~~ → erledigt UND **nachgeprüft**. Der
  Bestand stand tagelang auf null, was zwei völlig verschiedene Ursachen haben
  konnte: nie aufgerufen, oder still gescheitert. Ein echter Aufruf von
  `POST /analysis/position/load` hat genau eine Zeile erzeugt — der Pfad
  funktioniert, er war nur nie benutzt worden. Der Bestand beginnt jetzt;
  die ersten Outcomes werden 7 Tage nach dem ersten Aufruf fällig.
  Dass die Frage überhaupt offen war, lag am fehlenden Protokoll (siehe
  P4-11).
- **P3-05 (neu)** keine Auswertungsfläche für `BESTEHENDE_POSITION`. Die Daten
  laufen auf, gelesen werden sie noch nirgends — `/signals` und alle Abfragen in
  `auswertung/` filtern bewusst auf `NEUE_POSITION`. Nächster Schritt, sobald
  genug Zeilen fällig geworden sind.
- **P3-01** keine Stop-Historie → Ratchet wirkungslos, R-Multiple/MAE/MFE unberechenbar
- ~~**P3-02** SHORT-Pfad unerreichbar~~ → **halb erledigt.** Die Seite kommt
  jetzt aus `position_data["side"]` statt fest verdrahtet
  (`services/scoring.py`); `tests/test_position_side.py` belegt die
  Durchleitung und dass dieselbe Lage je Seite umgekehrt bewertet wird. Die
  Engines konnten SHORT ohnehin immer — es war getesteter toter Code.
  **Offen bleibt die Oberfläche:** das Positionsformular bietet kein
  Seiten-Feld an, liefert also weiter keine Seite und bekommt LONG. Bewusst so:
  der SHORT-Pfad ist durch Tests gedeckt, nicht durch Benutzung, und eine
  Positionsempfehlung ist eine Aussage über echtes Geld.
- **PC-04** ADX wird hier gerichtet gewertet — genau umgekehrt zur Entry-Engine, die ihn als Info führt
- ~~**PC-06** drei Metriken werden berechnet und nie gelesen~~ → erledigt, und
  es waren **acht**, nicht drei: `distance_to_stop_pct`,
  `distance_to_target_pct`, `invested_capital`, `open_risk`,
  `position_cagr`, `secured_profit_at_stop`, `secured_profit_pct_at_stop`,
  `target_exceeded_by_pct` — null Verwendungen außerhalb der Engine. Die
  Ursache war größer als der Posten: `position_recommendation.html` liest
  `pa.recommendation`, `pa.scores`, `pa.validation` und `pa.stop_proposals`,
  aber **`pa.metrics` kein einziges Mal**. Jetzt zeigt das Partial Risiko und
  Abstände (offenes Risiko, Stop-Abstand in ATR, gesicherter Gewinn,
  Zielabstand, verbleibendes CRV, R-Multiple). `position_cagr` bleibt bewusst
  draußen — eine auf ein Jahr hochgerechnete Rendite aus drei Haltetagen ist
  eine Zahl, die in die Irre führt.
  **Einheitenfalle dabei festgehalten:** die `_pct`-Felder von
  `PositionMetrics` enthalten BRÜCHE, keine Prozente (`_safe_div` teilt nur).
  Die Engines rechnen korrekt um (`recommendation_engine.py:59`), die Anzeige
  jetzt auch.
- **P3-04** Entry- und Positionsscore sind keine vergleichbaren Größen

### D. Analyse-Substanz
- **P2-01** Sektor-Bewertungsmodelle erreichen den Score nicht — generischer DCF läuft auf Banken, REITs, Biotech
- ~~**P2-02** Cross-sectional Momentum fehlt ganz~~ → gebaut, gemessen,
  survivorship-korrigiert und auf zehn Jahren **widerlegt** (§2c). Über
  2018-2025 gepoolt: D10 +0,2 pp (30 Tage) und −0,8 pp (90 Tage), nichts
  signifikant. Der ursprüngliche Befund war zu einem Drittel Survivorship und
  im Rest ein einziges Regime (2023-25). **Kommt nicht in den Score.** Die
  Module bleiben — sie messen weiter, und ein Regime-Filter wäre die einzige
  Konstruktion, unter der Momentum hier je etwas beitrüge.
- **P2-03** ADX wird berechnet und verworfen; gehört als Regime-Gate verwendet
- **P2-05** Fundamentalblock (0,30) wird auf 7–90 Tagen gemessen, passt nicht zur Halbwertszeit
- **P2-06** fehlende Signale: PEAD (Ansatz existiert, <1 % Abdeckung), Analysten-Revisionen, relative Stärke je Sektor, Short Interest, Insider-Cluster, Accruals

### E. Präzision (2 von 9 erledigt)
- **P4-04** absolute statt volatilitätsrelative Schwellen — RSI 30 bedeutet bei Versorger und Biotech Verschiedenes
- **P4-03** Währungen (Xetra/US) werden nie verrechnet
- **P4-05** Nenner nahe null über die gesamte Kennzahlenfläche
- **P4-06/08/09** illiquide Reihen, Kursgrößenordnungen, ADR-Doppelzählung
- ~~**P4-07** Survivorship~~ → **halb geschlossen.** Die Aufnahmen-Hälfte ist
  gemessen und korrigierbar: `services/index_membership.py` liefert die
  Aufnahmedaten, `momentum_auswerten(nur_mitglieder=True)` filtert danach,
  und der Effekt ist beziffert (§2c: ein Drittel des Momentum-Vorsprungs).
  **Offen bleibt die Ausschluss-Hälfte** — die entfernten Titel fehlen im
  Bestand vollständig und Wikipedia führt die Änderungshistorie nicht mehr.
  Sie wirkt allerdings gegen gefundene Effekte, ist also die ungefährlichere
  der beiden. Zum Schließen bräuchte es eine Quelle historischer
  Index-Zusammensetzungen und einen Backfill der entfernten Ticker.
- **P4-10 (neu)** `basis_kurs` ist auf **allen 264.102** Outcomes NULL. Das Feld
  existiert, `models.py` führt es als split-sichere Outcome-Basis, und
  `snapshot_service` füllt es für neue Zeilen — nur hat keine einzige
  Bestandszeile es je bekommen. Alle gespeicherten `outcome_return` sind damit
  gegen `kurs_bei_snapshot` gerechnet, mit einem Outcome-Kurs aus einem anderen
  Download: genau die Konstellation, gegen die das Feld eingeführt wurde. Der
  sichtbare Schaden ist klein — 26 von 87.523 Sieben-Tage-Zeilen über ±40 %,
  und die tragen bekannte Namen (CVNA, SMCI, ECHO, ACX.DE), sind also echte
  Ereignisse. Der Schutz war trotzdem nie in Kraft. Eine echte Reparatur hieße,
  die Outcomes aus einer frisch geladenen, einheitlich angepassten Reihe neu zu
  rechnen (593 Ticker).
- **P4-11 (neu)** Stille Fehlerpfade außerhalb von `snapshot_engine/`.
  `routers/analysis.py` ist umgestellt (drei Stellen: `warnings.warn` und
  `traceback.print_exc` → `logger`), weil dort die Unsicherheit über P3-03
  entstand. Der Rest steht noch: ~190 breite `except Exception` und
  `print()`-Fehlerbehandlung in den übrigen Routern und Services (siehe
  CLAUDE.md). Dazu 23 mypy-Meldungen ohne committete Konfiguration — fehlende
  Stubs sowie `Row`-vs-`tuple` in `kennzahlen.py` und `risk_adjusted.py`.

### F. Werkzeuge — keines gebaut
`signal-researcher`, `market-data-integrity`, `sector-models`, `snapshot-schema`
(Spezifikation im Artifact). B, D und E stützen sich darauf; bisher wurde diese
Arbeit inline erledigt, was sie langsam und einmalig statt wiederholbar macht.

---

## 5. Empfohlener nächster Schritt

**Der Befund nach zehn Jahren Daten: kein Eingang der Engine trägt gegen den
Markt.** Weder die sechzehn Indikator-Richtungen noch die fünf Kategorien
(§2b), noch das Oszillator-Gate in beiden Zweigen (§2a, 2.1.0/2.2.0), noch
Querschnitts-Momentum (§2c). Alles Getestete ist **kursbasiert** — und genau
das ist inzwischen die auffälligste Gemeinsamkeit der Null-Befunde.

Zwei Wege, in dieser Reihenfolge:

1. **Eine andere Signalklasse probieren, nicht noch eine Kursformel.** P2-06
   listet die einzigen bisher ungetesteten Familien: PEAD (Ansatz existiert,
   <1 % Abdeckung), Analysten-Revisionen, Short Interest, Insider-Cluster,
   Accruals. Keine davon ist aus Kursen ableitbar — das ist ihr Wert hier.
   Nüchtern dazu: die Trefferquote dieser Sitzung bei „plausibles Signal trägt
   auch" liegt bei null von vier. Die Erwartung sollte entsprechend sein.

2. **Parallel das ernten, was keinen Prognosevorteil braucht.** Section C:
   Stop-Historie (P3-01) schaltet R-Multiple, MAE und MFE frei; die
   Positionsmetriken sind seit PC-06 sichtbar; P3-05 wertet den Positionspfad
   aus, sobald Zeilen fällig sind. Realisierte Ergebnisse hängen an Ausstieg
   und Positionsgröße, und die sind steuerbar, ohne vorher zu wissen, welcher
   Titel den Index schlägt. Für das Ziel „so viel Geld wie möglich" ist das
   der Teil mit dem sicheren Beitrag.

**Der Holdout bleibt unberührt** (0 Zugriffe) — es gibt weiterhin nichts zu
bestätigen.

Danach P2-06 in der dortigen Reihenfolge (PEAD, Analysten-Revisionen, relative
Stärke je Sektor, Short Interest, Insider-Cluster, Accruals) und P2-01
(Sektormodelle). Der Umbau des Composites bleibt bis Schritt 3 liegen.

**Nicht** mit dem Vorschlagspanel für Gewichte anfangen: DX-01 zeigt, dass
Gewichtstuning an dieser Architektur eine Decke hat.

**Den Holdout nicht anfassen**, solange keine auf dem Training bestimmte
Aussage vorliegt, die er bestätigen soll. Er steht bei **0 Zugriffen**; der
Zähler ist auf `/signals` sichtbar. Wer nach jeder Änderung erneut misst und
die beste Variante behält, hat ihn zum Trainingsset gemacht — nur langsamer.

---

## 6. Verifikation (es gibt keine CI)

```
py -m pytest -q                                   # 191 Tests
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
