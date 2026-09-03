# CONTEXT.md — Arbeitsstand Signal-Engine

_Stand: 2026-09-04 · auf `01646e9` folgend · Branch `main`_

Übergabedatei für eine frische Claude-Session. Sie beantwortet drei Fragen:
**Was ist erledigt, was ist offen, und was darf nicht noch einmal neu hergeleitet
werden.** Vollständige Fassung mit Belegen und Zahlen:
<https://claude.ai/code/artifact/0dbcfa21-4049-4568-800b-edfc83b2f3cb>

---

## 0. Zuerst lesen — vier Dinge, die schiefgehen

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

### c) Die alte Snapshot-Generation ist gelöscht — es gibt eine Sicherung

Am 2026-09-03 wurden die **273.831 HISTORISCH-Snapshots** der Jobs #1 und #2
gelöscht und durch Job #3 ersetzt (§2j). Die 1.109 LIVE-Snapshots blieben
unberührt — sie sind der einzige Bestand im Projekt, der sich nicht
nachproduzieren lässt.

**Die Sicherung liegt unter `data/macrodashboard.sicherung-2026-09-03.db`**
(1,03 GB, von `.gitignore` erfasst, Integrität geprüft). Sie enthält den
vollständigen Vorzustand. Nicht löschen, solange die neuen Auswertungen nicht
über Wochen plausibel sind.

Warum ersetzt und nicht danebengelegt, obwohl zunächst anders entschieden: der
neue Lauf trägt dieselbe `score_version` 2.2.0 wie der alte, und **keine
einzige Auswertung filtert auf `backfill_job_id`** (geprüft). Zwei Generationen
nebeneinander hätten einen Generationsfilter durch acht Auswertungsmodule
verlangt, und ein übersehenes Modul hätte still doppelt gezählt.

Zweiter Grund, der vorher nicht auf dem Tisch lag: `_ticker_replayen`
überspringt jeden Stichtag, für den bereits ein HISTORISCH-Snapshot dieses
Tickers existiert — **unabhängig vom Job**. Ohne Löschen hätte der neue Lauf
Kurszeilen erzeugt und null neue Indikatorzeilen. Wer das nächste Mal neu
aufzeichnen will, muss diese Stelle kennen.

Fünf Ticker liessen sich nicht mehr laden (`FDXF`, `HONA`, `Q`, `KCO.DE`,
`XONA.DE`) — delistet oder umbenannt. Genau dafür existiert die Sicherung.

### d) Es wird direkt auf `main` gearbeitet — keinen Zweig anlegen

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

Datenbestand (nach der **Neuaufzeichnung vom 2026-09-03**, Backfill-Job #3):

| | |
|---|---|
| Snapshots HISTORISCH | **188.347** · 2017-04-13 bis 2026-09-03 · 592 Ticker |
| Snapshots LIVE | **1.109** · unverändert erhalten |
| Indikatorzeilen | **1.896.557** · davon 1.883.467 mit Rohwert (99,3 %) |
| Outcomes ausgewertet | **558.683** · zu 100 % marktbereinigt |
| Kurszeilen (`kurs_historie`) | **1.465.410** · 592 Ticker · 2016-08 bis 2026-09 |

**Es gibt nur noch EINE Generation.** Die 273.831 alten HISTORISCH-Snapshots
aus den Jobs #1 und #2 sind am 2026-09-03 gelöscht worden, nachdem die
Neuaufzeichnung sie ersetzt hatte — siehe §0c. Damit entfällt die frühere
Versionsmischung; jede Auswertung rechnet wieder über einen einheitlichen
Bestand, ohne Filter auf `backfill_job_id`.

Weniger Snapshots als vorher ist kein Verlust: der alte Bestand war die Summe
zweier übereinandergelegter Läufe (#1 über 5 Jahre, #2 über 10), #3 ist ein
einziger sauberer Durchlauf mit einer Kadenz über denselben Zeitraum.

---

## 2. Der zentrale Befund — nicht neu herleiten

> ### ⚠ Die Zahlen in §2 bis §2i stammen aus dem STILLGELEGTEN Bestand
>
> Sie sind auf den 273.831 Snapshots der Jobs #1 und #2 gerechnet, und diese
> Zeilen existieren seit dem 2026-09-03 nicht mehr (§0c). **Sie lassen sich
> gegen die heutige Datenbank nicht reproduzieren.** Als Befunde bleiben sie
> gültig und sind nicht neu herzuleiten — als Zahlen sind sie historisch.
>
> Vor allem: alle Indikatoraussagen dieser Abschnitte beruhen auf der
> **binären Kodierung** (±1), die inzwischen als Messfehler erwiesen und
> behoben ist. Der aktuelle Stand steht in **§2j**, und wo beide sich
> widersprechen, gilt §2j.

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

## 2d. Sektortrennung: die Nullbefunde sind keine Mischungsartefakte

Die naheliegende Erklärung für §2b war: eine RSI-Schwelle von 30 bedeutet bei
einem Versorger etwas anderes als bei einem Biotech, und eine Auswertung über
alle Titel mittelt genau den Vorsprung weg, den es je Sektor gäbe. Der Nutzer
hat diese Eigenschaft am 2026-08-30 ausdrücklich verlangt („specific on the
stock that the user inputted"). Sie ist geprüft — **die Erklärung trägt nicht.**

### Erst die Prämisse, und die hält

Die unbedingte Marktquote unterscheidet sich je Sektor deutlich
(Trainingsteil, 30 Tage, HISTORISCH, 182.692 Beobachtungen, gepoolt 50,4 %):

| Sektor | n | schlägt Index | Abstand zum Pool |
|---|---|---|---|
| Information Technology | 26.403 | 53,0 % | +2,6 pp |
| Industrials | 29.141 | 52,1 % | +1,7 pp |
| Financials | 28.205 | 51,4 % | +1,0 pp |
| Consumer Discretionary | 17.381 | 51,0 % | +0,6 pp |
| Communication Services | 8.316 | 49,5 % | −0,9 pp |
| Utilities | 11.285 | 49,5 % | −0,9 pp |
| Materials | 9.131 | 49,3 % | −1,1 pp |
| Energy | 7.755 | 48,9 % | −1,5 pp |
| Health Care | 21.456 | 48,7 % | −1,7 pp |
| Real Estate | 11.143 | 47,5 % | −2,8 pp |
| Consumer Staples | 12.476 | 46,4 % | −4,0 pp |

**Spannweite 6,6 pp bei ±1,4 pp Fehlerspanne** — weit außerhalb des Rauschens.
Konsequenz für jede künftige Auswertung: **nach Sektor aufteilen heißt auch,
gegen die Basis DES SEKTORS zu rechnen.** Gegen die gepoolte Basis bekäme jeder
Tech-Titel +2,6 pp geschenkt und jeder Basiskonsumtitel −4,0 pp aufgebürdet,
ohne dass ein Indikator daran beteiligt wäre.

### Dann die Messung, und die ist negativ

Je Sektor, Indikator und Richtung, jede Zelle gegen die Marktquote ihres
Sektors: **198 auswertbare Zellen.** Bei so vielen Tests wären unkorrigiert
rund zehn Zufallstreffer zu erwarten, deshalb Šidák-Korrektur wie in
`schwellensuche.py` — kritischer z-Wert **3,65** statt 1,96.

**Zwei Zellen überleben, beide negativ:**

| Sektor | Indikator | Richtung | n | Vorsprung |
|---|---|---|---|---|
| Industrials | Trend (SMA 200) | bearisch | 9.305 | −4,0 pp ±3,4 |
| Utilities | SMA-Cross (20/50) | bearisch | 4.608 | −5,1 pp ±4,8 |

Keine einzige Zelle mit positivem Vorsprung übersteht die Korrektur; der größte
positive Wert (Bollinger bearisch in IT, +5,4 pp) fällt durch. **Die
Sektortrennung macht nichts sichtbar, was das Pooling verdeckt hätte.**

**Nicht weiterverfolgen:** unter den acht besten Zellen steht viermal der RSI
(Utilities +4,9, Materials beidseitig +4,7, Energy +4,2). Das ist das einzige
kohärent wirkende Muster — und genau die Beobachtung, aus der ein Fehlbefund
entsteht, wenn man sie herausgreift und separat nachrechnet. Die Zellen sind
klein (n = 270–644), keine ist signifikant, und die vier vielversprechendsten
von 198 zusammenzufassen ist Cherry-Picking mit Zwischenschritt.

---

## 2e. PEAD: der erste Eingang, dessen Vorzeichen über die Jahre hält

Der erste geprüfte Kandidat, der **nicht aus Kursen stammt** (P2-06). Genau
darum ging es: die Gemeinsamkeit aller bisherigen Nullbefunde war nicht die
Hypothese, sondern die Herkunft der Größe.

### Der Bestand, und warum es ihn vorher nicht gab

`services/earnings.py` liest `tk.earnings_dates` **ohne `limit`** — Yahoos
Vorgabe sind rund zwölf Quartale. Das ist die ganze Erklärung für die
„<1 % Abdeckung", die hier lange als Sackgasse notiert war: es fehlte nicht
die Quelle, es fehlte ein Parameter. Mit `limit=100` reicht die Reihe bei
US-Titeln bis 2002 (AAPL 87 Quartale, MSFT 99), bei SAP.DE bis 2010.

Geladen: **47.176 Ereignisse über 592 der 611 Ticker.** Die 19 Ausfälle sind
fast alle Xetra-Listings von US-Konzernen (`MSF.DE`, `ABEA.DE`, `NVD.DE`,
`ORC.DE`, `CHV.DE`, `BAC.DE` …) — deren Zahlen liegen unter dem US-Kürzel;
eine Zuordnungstabelle wäre die Nachbesserung, ist aber ungeprüft und daher
nicht gebaut. `BTC-USD` hat berechtigterweise keine Quartalszahlen.

Damit tragen **204.652 von 217.590 auswertbaren Snapshot-Zeilen (94 %)** ein
Ereignis im Fenster — gegenüber 981 Zeilen vorher.

### Die Messung: Quintile gegen den Markt (TRAIN, HISTORISCH, Šidák z = 2,57)

| Horizont | Basis | Q1 (schlechteste) | Q5 (beste) | Spread |
|---|---|---|---|---|
| 7 Tage | 49,7 % | 48,7 % · **−1,1 pp ±0,6 SIGNIFIKANT** | 50,2 % · +0,5 ±0,6 | 1,5 pp |
| 30 Tage | 50,0 % | 49,4 % · −0,6 ±1,1 | 50,7 % · +0,7 ±1,1 | 1,3 pp |
| 90 Tage | 49,6 % | 49,6 % · −0,0 ±1,9 | 50,3 % · +0,6 ±1,9 | 0,7 pp |

Die Reihenfolge zeigt auf allen drei Horizonten in die vorhergesagte Richtung,
und der Spread schrumpft mit wachsendem Horizont — beides passt zu PEAD.
**Signifikant ist aber nur das untere Ende.** Q5, die Seite, die man kaufen
würde, bleibt überall Rauschen.

### Der Verlauf über den Abstand zur Veröffentlichung (30 Tage, 20 Zellen, z = 3,02)

Zwei Zellen überstehen die Korrektur: `Q1 · 6–20 Tage` mit −3,2 pp ±3,1 und
`Q4 · 61–120 Tage` mit +2,6 pp ±2,2. Bei zwanzig Tests ist etwa ein
Zufallstreffer zu erwarten, zwei sind kaum mehr. Und die zweite liegt an der
**für PEAD falschen Stelle**: ein verzögertes Einpreisen klingt ab, es setzt
nicht nach vier Monaten im vierten Quintil ein. Als Beleg zählt sie nicht.

Nebenbefund, der beim Lesen der Tabelle sonst irreführt: das Band 21–60 Tage
liegt in **allen** Quintilen bei −1,7 bis −1,8 pp, das Band 61–120 Tage in
allen bei +1,0 bis +2,6. Das ist eine gemeinsame Zeitstruktur, keine
Eigenschaft der Überraschung — im Quintilvergleich hebt sie sich auf.

### Die Regime-Prüfung, an der Momentum gescheitert ist (7 Tage, je Kalenderjahr)

| Jahr | n | Basis | Q1 Vorsprung | Q5 Vorsprung |
|---|---|---|---|---|
| 2017 | 7.935 | 50,9 % | −1,5 | +1,1 |
| 2018 | 18.942 | 52,5 % | −1,6 | −0,1 |
| 2019 | 19.079 | 51,6 % | −1,4 | −0,7 |
| 2020 | 19.411 | 48,6 % | −1,9 | +2,7 |
| 2021 | 19.473 | 49,3 % | −0,5 | −0,8 |
| 2022 | 29.693 | 54,2 % | −1,6 | +0,7 |
| 2023 | 39.436 | 46,8 % | −0,5 | −0,2 |
| 2024 | 39.610 | 46,1 % | −1,7 | +2,0 |
| 2025 (Teiljahr bis zur Grenze) | 11.073 | 55,2 % | **+2,9** | −1,9 |

**Das ist der Unterschied zu §2c.** Querschnitts-Momentum trug in einem
einzigen Regime (2023–25) und sonst nichts. Q1 trägt hier in **acht von neun
Jahren** dasselbe Vorzeichen — als Vorzeichentest p ≈ 0,04, und zwar
unabhängig davon, wie gepoolt wird. Q5 dagegen hat kein stabiles Vorzeichen
(fünfmal positiv, viermal negativ) und ist damit auch jahresweise Rauschen.

Das letzte, unvollständige Jahr kehrt Q1 um (+2,9). Es ist das jüngste
Fenster vor der Trennungsgrenze und wiegt entsprechend — es widerlegt den
Befund nicht, aber es ist die eine Beobachtung, die gegen ihn steht.

### Was daraus folgt

1. **PEAD als Kaufsignal trägt nicht.** Q5 ist gepoolt Rauschen und jahresweise
   ohne stabiles Vorzeichen. Die Trefferquote „plausibles Signal trägt auch"
   bleibt damit bei null von fünf.
2. **Die Miss-Seite trägt schwach, aber stabil.** Rund −1,1 bis −1,3 pp über
   sieben Tage, Vorzeichen in acht von neun Jahren gleich. Das ist der erste
   Eingang der Engine mit einem über Regime hinweg stabilen Vorzeichen.
3. **Verwendbar wäre er nur als Meidungsfilter**, nicht als Signal: eine
   Short-Seite lässt sich hier nicht ausspielen (dieselbe Begründung, aus der
   `risk_adjusted.py` absolut rechnet). „Nach einem schweren Miss in den
   nächsten Tagen nicht kaufen" ist dagegen ohne Leerverkauf umsetzbar.
4. **Nichts davon geht in den Score**, bevor der Holdout dazu gehört wurde —
   und ob er dafür ausgegeben wird, ist eine Entscheidung des Besitzers
   (siehe §5).

---

## 2f. Analystenrevisionen: die Kaufseite leuchtet — und ist zur Hälfte der Kurs

Zweite Signalfamilie aus §5 (P2-06). Der Befund ist der bisher lehrreichste,
weil er zum ersten Mal auf der **Kaufseite** signifikant wird und trotzdem
nicht trägt.

### Was es historisch gar nicht gibt — geprüft, nicht vermutet

Der klassische Revisionsindikator wäre die Änderung der
Konsens-Gewinnschätzung. Bei dieser Quelle ist sie **historisch nicht zu
haben**: `eps_trend`, `eps_revisions`, `earnings_estimate` und
`recommendations` liefern sämtlich nur ein rollierendes Fenster (aktuell, vor
7/30/60/90 Tagen bzw. 0m/−1m/−2m/−3m) **ohne Datumsachse**. Sie sind live
lesbar und rückwirkend wertlos. Wer das nicht prüft, baut eine Messung, die
auf dem Bestand nie laufen kann.

Verwertbar ist genau eine Quelle: `upgrades_downgrades` — ein Ereignisprotokoll
mit Datum, Haus, Rating vorher/nachher und Kursziel vorher/nachher, bei
US-Titeln zurück bis 2012.

### Bestand und seine Schlagseite

**175.197 Handlungen über 523 der 611 Ticker.** Die 88 Ausfälle sind **fast
ausschließlich nicht-US-Titel**: 85 Xetra-Werte (SAP, Siemens, BMW, Allianz …),
dazu Paris, Zürich, Seoul. Umgekehrt zu PEAD haben die Xetra-**Listings von
US-Konzernen** (`MSF.DE`, `ABEA.DE`, `NVD.DE`) sehr wohl Daten.

Die Folge steht in der Messung: von **203.204 gerangten Snapshots stammt kein
einziger von Xetra** — der deutsche Querschnitt fällt je Woche unter
`MIN_QUERSCHNITT` und damit ganz heraus. **Diese Auswertung ist US-only.** Ein
Signal daraus gälte für rund fünf Sechstel des Universums, nicht für alle.

Zwei Fallen der Quelle, beide im Code festgehalten:
`priorPriceTarget` ist **`0.0`, nicht `NaN`**, wenn kein Vorziel existiert
(rund ein Fünftel der Zeilen) — auf `notna()` geprüft rechnet man danach gegen
einen Nenner von null. Und der Median der Zielrevisionen liegt bei **+2,1 %**:
Analysten heben häufiger an als sie senken, eine absolute Schwelle misst
deshalb überwiegend diesen Drift. Nur ein Querschnittsrang taugt.

### Die Messung (TRAIN, HISTORISCH, Šidák z = 2,57)

**Netto-Rating** (Heraufstufungen minus Herabstufungen im 90-Tage-Fenster,
gruppiert nach Wert statt nach Rang, weil die Mehrheit exakt null ist):
**nichts, auf keinem Horizont.** Spread 0,7 / 0,4 / −0,1 pp, keine einzige
Zelle signifikant. Erledigt.

**Zielrevision** (mittlere prozentuale Kurszieländerung im Fenster, Quintile):

| Horizont | Q1 | Q5 | Spread | Form |
|---|---|---|---|---|
| 7 Tage | 48,8 % · **−1,0 pp ±0,7 SIG** | 50,9 % · **+1,2 pp ±0,7 SIG** | **2,1 pp** | monoton über alle fünf |
| 30 Tage | 50,9 % · +0,7 ±1,3 | 51,0 % · +0,8 ±1,3 | 0,1 pp | U-Form, beide Enden oben |
| 90 Tage | 50,4 % · +0,6 ±2,2 | 51,3 % · +1,5 ±2,2 | 0,9 pp | Rauschen |

Auf sieben Tagen ist das der **erste Befund dieses Projekts, bei dem auch die
Kaufseite signifikant ist**, und der Verlauf ist über alle fünf Quintile
monoton. Genau deshalb lohnen die zwei Gegenproben.

### Gegenprobe 1: die Regime-Prüfung

Spread je Kalenderjahr (7 Tage): +4,4 · +1,3 · +1,4 · +5,3 · **−3,3** · +3,2 ·
+1,4 · +5,4 · **−5,0**.

**Positiv in sieben von neun Jahren — als Vorzeichentest p ≈ 0,18, also
Rauschen.** Zum Vergleich: PEADs Miss-Seite stand bei acht von neun und
p ≈ 0,04. Die beiden Gegenjahre sind zudem keine Nullen, sondern die
zweit- und drittgrößten Beträge der Reihe, und die drei stärksten positiven
Jahre (2020, 2022, 2024) sind Hochvolatilitätsjahre. Das sieht nach einer
Regime-Abhängigkeit aus, nicht nach einer Eigenschaft.

Wie schon bei PEAD widerspricht das jüngste, unvollständige Jahr am
deutlichsten (−5,0).

### Gegenprobe 2: was misst die Zielrevision eigentlich?

**Rangkorrelation zwischen dem Zielrevisions-Rang und der Kursrendite der
vorangegangenen 90 Tage: 0,473** (Pearson 0,455, n = 200.620).

Analysten folgen dem Kurs zu rund der Hälfte. Der Eingang ist damit **kein
unabhängiger fundamentaler Eingang**, sondern zu großen Teilen recyceltes
Kursmomentum — gemessen auf sieben Tagen, wo kurzfristige Fortsetzung ohnehin
am ehesten auftritt. Damit erklärt sich auch, warum der Effekt auf 30 Tagen
verschwindet statt abzuklingen: eine Informationsverarbeitung klänge ab, ein
kurzfristiger Kurseffekt kippt.

### Was daraus folgt

1. **Kommt nicht in den Score.** Weder Netto-Rating noch Zielrevision.
2. **Der Anspruch „nicht aus Kursen ableitbar" muss gemessen werden, nicht
   angenommen.** Die Quelle ist fundamental, die Größe ist es nicht. Für jede
   künftige Signalfamilie gehört diese Korrelation zur Prüfung dazu — sie
   kostet eine Abfrage und hätte hier eine Fehlinterpretation verhindert.
3. **Die Regime-Prüfung bleibt der schärfste Filter.** Sie hat jetzt
   Querschnitts-Momentum (§2c) und die Zielrevision aussortiert und PEADs
   Miss-Seite als einziges durchgelassen.
4. Trefferquote bei „plausibles Signal trägt auch": **null von sechs.**

---

## 2g. Accruals: der erste wirklich unabhängige Eingang — und er trägt nichts

Dritte Signalfamilie (P2-06), und die einzige, die den Kurs von ihrer
Konstruktion her nicht berühren kann:

    accrual = (Jahresüberschuss − operativer Cashflow) / Bilanzsumme

**Achtung beim Vorzeichen:** anders als bei §2e und §2f ist hier unten gut.
Sloan (1996) erwartet, dass **hohe** Abgrenzungen schlechtere Folgerenditen
haben. `spread_pp` ist deshalb als Q1 minus Q5 gerechnet, damit „positiv"
auch in diesem Modul „Hypothese bestätigt" heißt.

### Zwei Datenquellen, die nicht gehen — beide gemessen, nicht vermutet

**Insider-Cluster ist auf diesem Bestand nicht messbar** und deshalb gar nicht
erst gebaut worden. `insider_transactions` reicht bei allen fünf geprüften
Tickern einheitlich nur bis September/Oktober 2024 zurück. Der Trainingsteil
endet am 2025-04-20 — es blieben gut sechs Monate Überlappung, und der
**Holdout hätte mehr Abdeckung als das Training**. Ein Quiver-Token ist nicht
gesetzt. Die Familie bleibt offen, aber nicht als Versäumnis: sie braucht eine
andere Quelle.

**Die billige SEC-Schnittstelle ist eine Falle.** `frames` liefert eine
Kennzahl für rund 5.700 Unternehmen in einem einzigen Abruf — aber die zuletzt
berichtete Fassung. Gemessen an `CY2020Q1`:

| Einreichungsjahr der gelieferten Zahl | Anteil |
|---|---|
| 2020 (das Periodenjahr) | **7,1 %** |
| 2021 | 84,0 % |
| 2022 und später | 8,9 % |

Vier Fünftel der Werte stammen also aus der Vergleichsspalte des Folgejahres.
Ein pauschaler Aufschlag von drei Monaten hätte damit mit Wissen gerechnet,
das seinerzeit ein Jahr in der Zukunft lag. Verwendet wird deshalb
`companyconcept` — ein Abruf je Unternehmen und Auszeichnung, dafür mit
`filed` an jeder einzelnen Zahl. `bekannt_ab` ist das **späteste** der drei
Einreichungsdaten; ein pauschaler Sicherheitsabstand entfällt dadurch ganz.

Ebenfalls gemessen: **Quartals-Accruals gehen nicht.** Der operative Cashflow
wird überwiegend kumuliert übers Geschäftsjahr berichtet, weshalb nur das
erste Quartal eine Dreimonatsdauer trägt — je Ticker blieben rund acht statt
achtunddreißig verwertbare Quartale. Die Jahresform braucht keine
Differenzbildung und ist ohnehin die der Literatur.

### Bestand

**6.556 Jahres-Accruals über 459 Ticker.** Ausfälle: 109 ohne CIK (jede
Auslandsnotierung — die Messung ist wie §2f US-only) und 41 US-Titel, deren
Filer die drei Bestandteile anders auszeichnen (Banken und Versicherer, dazu
KO, XOM, V, PYPL). 141.891 von 217.590 Zeilen tragen eine gültige Kennzahl.

### Die Messung (TRAIN, HISTORISCH, Šidák z = 2,57)

| Horizont | Q1 (niedrig) | Q3 | Q5 (hoch) | Spread Q1−Q5 |
|---|---|---|---|---|
| 7 Tage | 50,4 % · +0,5 ±0,8 | 49,5 % · −0,4 | 49,4 % · −0,5 | 1,0 pp |
| 30 Tage | 51,6 % · +1,3 ±1,3 | 49,6 % · −0,7 | 50,5 % · +0,2 | 1,1 pp |
| 90 Tage | 52,3 % · +2,1 ±2,3 | 48,3 % · −1,9 | 51,4 % · +1,2 | 0,9 pp |

**Keine einzige Zelle übersteht die Korrektur, und die Form ist überall
falsch.** Sloan sagt einen monotonen Abfall von Q1 nach Q5 voraus; gemessen
ist ein U — Q1 oben, die Mitte unten, Q5 wieder oben. Q1 liegt auf 30 und 90
Tagen zwar in der vorhergesagten Richtung, aber ohne Gefälle dahinter ist das
eine Zelle von fünfzehn.

### Der eigentliche Ertrag: die Kursnähe-Prüfung ist geeicht

**Rangkorrelation zur Kursrendite der vorangegangenen 90 Tage: −0,001**
(n = 179.648). Zum Vergleich die Zielrevision der Analysten aus §2f: **0,473**.

Damit ist zweierlei belegt:

1. **Die Prüfung aus §2f unterscheidet tatsächlich**, statt nur plausibel zu
   klingen. Sie liegt bei einem umetikettierten Kurssignal bei 0,47 und bei
   einer echten Bilanzgröße bei null. Sie steht jetzt als
   `auswertung/kursnaehe.py` und wird von den Revisions- und
   Accrual-Auswertungen mitgerechnet.
2. **Die Erklärung „alle Nullbefunde kommen von der kursbasierten Herkunft"
   ist erledigt.** Hier ist ein Eingang, der nachweislich nichts vom Kurs
   abbildet, sauber punkt-in-zeit datiert ist, aus 6.556 geprüften
   Jahresabschlüssen stammt — und er trägt genauso wenig wie die sechzehn
   Kursindikatoren. Die Gemeinsamkeit der Nullbefunde liegt nicht in der
   Herkunft der Eingänge.

Trefferquote bei „plausibles Signal trägt auch": **null von sieben.**

---

## 2h. Die Kodierung war das Problem — und das Regime ist die offene Frage

Der erste Befund dieser Reihe, bei dem die Engine selbst der Fehler ist und
nicht die Datenlage. Ausgelöst durch einen Einwand des Besitzers: die
bisherigen Nullbefunde seien Aussagen über **eine Implementierung**, nicht
über die Kennzahlen — und Profis arbeiteten sehr wohl mit Flags, Kaufsignalen
und Chartverhalten. Beides trifft zu.

### Was im Bestand tatsächlich steht

| Indikator | Zeilen | **verschiedene Werte** | Verteilung |
|---|---|---|---|
| Trend (SMA 200) | 274.839 | **2** | +1: 62 % · −1: 38 % |
| SMA-Cross (20/50) | 274.839 | **2** | +1: 57 % · −1: 43 % |
| VWMA (20T) | 274.840 | **2** | +1: 56 % · −1: 44 % |
| Volumen-Cluster (POC) | 274.840 | **2** | +1: 66 % · −1: 34 % |
| FVG (Fair Value Gap) | 263.630 | **2** | +1: 69 % · −1: 31 % |

Ein Kurs ein halbes Prozent über der SMA 200 und einer fünfundvierzig Prozent
darüber sind **derselbe Eingang**. Keine Stärke, kein Neutralbereich. Und im
Feld `wert` steht bei den Trendindikatoren nicht der Abstand, sondern der Kurs
(409,39 / 90,37) — die Größe selbst wurde nie gespeichert. Ein Flag, das bei
62 Prozent aller Beobachtungen gesetzt ist, ist kein Flag, sondern eine
Zustandsbeschreibung.

### Der Kontrollversuch (7 Tage, TRAIN, identische Zeilen, Šidák z = 2,68)

Gemessen wurden beide Fassungen derselben Zahl auf **exakt denselben
205.159 Zeilen**, mit derselben Marktbasis und derselben Korrektur. Einziger
Unterschied: die weggeworfene Stärke.

| | Q1 | Q2 | Q3 | Q4 | Q5 | Spread |
|---|---|---|---|---|---|---|
| **Trend stetig** | −0,8 **SIG** | −1,0 **SIG** | −0,3 | +1,0 **SIG** | +1,2 **SIG** | **2,0 pp** |
| Trend binär | −1: −0,5 Rauschen | | | | +1: +0,3 Rauschen | 0,8 pp |
| **SMA-Cross stetig** | −1,2 **SIG** | −1,3 **SIG** | +0,1 | +0,7 | +1,7 **SIG** | **2,9 pp** |
| SMA-Cross binär | −1: −0,2 Rauschen | | | | +1: +0,1 Rauschen | 0,3 pp |

**Monotoner Verlauf über alle fünf Quintile, mehrere Zellen korrigiert
signifikant — und die binäre Fassung derselben Zahl zeigt nichts.** Die
Rundung auf ±1 vernichtet das Signal.

Auf 30 und 90 Tagen verschwindet der Effekt in beiden Fassungen und kehrt sich
teilweise um. Es ist ein Kurzfristeffekt, was zur Kursnähe passt: 0,696 beim
Trend, 0,513 beim Cross. Das ist hier kein Einwand wie in §2f — die Größe
**ist** eine Kursgröße, sie gibt nicht vor, etwas anderes zu sein. Es heißt
aber: kein neuer Eingang, sondern ein besser kodierter alter.

### Die Regime-Prüfung besteht es nicht — und zeigt dabei auf die Lösung

Spread je Kalenderjahr: **Trend 5 von 8 Jahren positiv** (p ≈ 0,73),
**SMA-Cross 6 von 8** (p ≈ 0,29). Beides fällt durch denselben Test, an dem
Querschnitts-Momentum (§2c) und die Zielrevision (§2f) gescheitert sind.

Entscheidend ist aber, **wie** es durchfällt:

| Jahr | Trend stetig | SMA-Cross stetig | Zielrevision (§2f) |
|---|---|---|---|
| 2018 | +1,5 | +2,5 | +1,3 |
| 2019 | −0,1 | +1,9 | +1,4 |
| **2020** | **+6,0** | **+4,3** | **+5,3** |
| **2021** | **−2,1** | **−1,5** | **−3,3** |
| **2022** | **+2,4** | **+6,4** | **+3,2** |
| 2023 | −0,6 | +1,6 | +1,4 |
| **2024** | **+4,2** | **+4,7** | **+5,4** |
| 2025 (Teiljahr) | +6,2 | −0,1 | −5,0 |

**Drei unabhängig konstruierte Signale, dasselbe Jahresmuster.** Stark in
2020, 2022 und 2024, negativ in 2021. Dass drei verschiedene Bauweisen
dieselben Jahre gut und dieselben Jahre schlecht finden, ist kein Zufall —
es sagt, dass die fehlende Größe **nicht ein weiteres Signal ist, sondern die
Bedingung, unter der ein Signal gilt.**

Damit hat P2-03 („der ADX wird berechnet und verworfen; gehört als Regime-Gate
verwendet") zum ersten Mal einen empirischen Beleg statt einer Vermutung.

### Was daraus folgt

1. **Die Kodierung ist ein echter Defekt der Engine**, unabhängig davon, ob
   das Signal am Ende trägt. Sie vernichtet nachweislich eine messbare Größe.
   Das gilt für alle sechzehn Indikatorrichtungen, nicht nur die zwei
   geprüften.
2. **Die Nullbefunde aus §2b sind entsprechend abzuschwächen.** Sie belegen,
   dass diese Kodierung nichts trägt — nicht, dass Trend, Mean-Reversion oder
   Chartlage nichts tragen. Wer sie weiter als Zweites zitiert, zitiert falsch.
3. **Kommt trotzdem nicht in den Score.** Ein Eingang, der in fünf von acht
   Jahren funktioniert, ist ohne Bedingung nicht handelbar; die Turnover-Frage
   bei einem Sieben-Tage-Horizont kommt hinzu.
4. **Der nächste Schritt ist das Regime-Gate**, nicht die achte Signalfamilie.

**Grenze der Messung:** die gleitenden Mittel stammen aus Snapshot-Kursen mit
acht Tagen Kadenz — das lange Fenster hat rund 35 statt 200 Stützstellen. Für
den Kontrollversuch (stetig gegen binär auf identischen Zeilen) reicht das;
ein exakter Nachbau auf echten Tagesreihen wäre der nächste Schärfungsschritt,
falls das Regime-Gate trägt.

---

## 2i. Das Regime-Gate: die Zahl wird besser, die Eigenschaft nicht

P2-03 stand seit jeher als Vermutung im Plan („der ADX wird berechnet und
verworfen; gehört als Regime-Gate verwendet"). §2h hat ihr einen Beleg
gegeben — drei unabhängige Signale mit demselben Jahresmuster. Jetzt ist sie
geprüft.

### Was gemessen wurde, und warum nicht der ADX

Der ADX braucht Tageshochs und -tiefs; der Bestand führt Schlusskurse im
Achttagetakt. Er ist zudem eine Eigenschaft des **einzelnen Titels**, während
das Muster aus §2h über alle Titel gleichzeitig auftritt und damit marktweit
ist. Gemessen wurde deshalb das Regime des **Index**, aus Tagesreihen
(`services/marktregime.py`):

- `vola_regime` — annualisierte realisierte Volatilität über 63 Handelstage,
  HOCH wenn über dem **nachlaufenden** Median der letzten zwei Jahre.
- `richtungs_regime` — Index über oder unter seinem eigenen 200-Tage-Mittel.

**Keine gesuchte Schwelle.** Die Grenze ist der nachlaufende Median der Größe
selbst; es gibt keinen Kandidatensatz wie in `schwellensuche.py` und damit
nichts zu korrigieren. Eine Grenze über den Gesamtzeitraum (etwa ein Terzil)
hätte die Zukunft mitbenutzt.

### Ein Nebenbefund, der wichtiger ist als das Gate

**Die Marktquote unterscheidet sich zwischen den Regimen um 4,2 pp:**

| Regime | n | Anteil, der den Index schlägt |
|---|---|---|
| Volatilität HOCH | 108.239 | **51,6 %** |
| Volatilität NIEDRIG | 96.920 | **47,4 %** |

Das ist **größer als jeder Signalvorsprung, der in diesem Projekt je gemessen
wurde.** In unruhigen Phasen schlagen mehr Titel ihren Index, in ruhigen
weniger — dieselbe Marktbreite, die schon §2b erklärt hat, nur regimeabhängig.

**Konsequenz für jede künftige Auswertung, die nach Regime trennt: gegen die
Basis DES REGIMES rechnen.** Gegen eine gemeinsame Basis bekäme jede
Hochvolatilitätsbeobachtung +2,1 pp geschenkt, ohne dass ein Signal beteiligt
wäre. Gleiche Falle wie bei den Sektor-Basisquoten (§2d), nur größer.

### Das Gate selbst (SMA-Cross stetig, 7 Tage, TRAIN, Šidák z = 2,80)

| Regime | Q1 | Q2 | Q3 | Q4 | Q5 | Spread |
|---|---|---|---|---|---|---|
| **HOCH** | −2,2 **SIG** | −1,8 **SIG** | +0,4 | +1,4 **SIG** | +2,1 **SIG** | **4,3 pp** |
| NIEDRIG | −0,2 | −0,8 | −0,2 | −0,1 | +1,3 **SIG** | 1,5 pp |

Gepoolt sieht das aus wie ein Fund: der Spread verdreifacht sich, der Verlauf
ist monoton, vier von fünf Zellen überstehen die Korrektur. Für „Trend
(SMA 200)" dasselbe schwächer (2,8 gegen 1,1), für das Richtungsregime
schwächer und weniger trennscharf (3,9 gegen 2,6).

### Und dann die Jahre

| Jahr | HOCH n | Spread | NIEDRIG n | Spread |
|---|---|---|---|---|
| 2018 | 16.311 | +4,4 | 1.497 | −18,7 |
| 2019 | 16.012 | +1,2 | 4.016 | +4,3 |
| 2020 | 16.879 | +5,4 | 3.259 | −1,6 |
| 2021 | 988 | −1,8 | 19.396 | −1,4 |
| 2022 | 29.099 | **+8,1** | 2.053 | −18,4 |
| 2023 | 4.665 | **−15,9** | 37.288 | +3,9 |
| 2024 | 13.262 | **+9,8** | 28.613 | +2,4 |
| 2025 | 11.023 | −0,9 | 798 | +11,5 |

**Im Hochvolatilitätsregime: fünf von acht Jahren positiv** — genau so
instabil wie ungegatet (sechs von acht). Die gepoolten 4,3 pp stammen aus
2018, 2020, 2022 und 2024 und werden von einem einzigen Jahr (2023, −15,9 pp)
weitgehend aufgezehrt.

**Das Gate verbessert die Zahl, aber nicht die Eigenschaft, auf die es
ankommt.** Genau das ist der Unterschied zwischen einem gepoolten Vorsprung
und einem verwendbaren Signal, und genau daran ist in diesem Projekt jetzt
alles gescheitert.

### Was daraus folgt

1. **P2-03 ist in der marktweiten Fassung geprüft und negativ.** Weder
   Volatilitäts- noch Richtungsregime machen ein Signal jahresstabil. Die
   titelbezogene Fassung (ADX je Aktie) bleibt ungeprüft — sie bräuchte einen
   Nachtrag von Tages-OHLC und ist damit eine andere Größenordnung.
2. **Die Regime-Basisquoten gehören ab jetzt in jede Auswertung**, die nach
   Regime trennt (siehe oben, 4,2 pp).
3. **Nichts davon geht in den Score.**
4. Trefferquote bei „plausibles Signal trägt auch": **null von acht.**

---

## 2j. Die Neuaufzeichnung — das Messgerät ist repariert, das Ergebnis bleibt negativ

Der Tag, an dem BC-04 behoben und der Bestand neu vermessen wurde. **Dies ist
der aktuelle Stand; bei Widerspruch zu §2–§2i gilt dieser Abschnitt.**

### Warum überhaupt neu aufgezeichnet wurde

Von zehn Instrumenten der Einstiegsanalyse liessen sich nur **zwei**
nachträglich stetig auswerten — und zwar nur deshalb, weil bei ihnen zufällig
ein Rohwert im Feld `wert` mitgeschrieben wurde. Nachgesehen in
`snapshot_service.py`:

| Instrument | im Bestand | nachträglich lesbar |
|---|---|---|
| Trend (SMA 200), SMA-Cross | ±1 + `sma200_val` / `sma50_val` | ja |
| RSI, Stochastic, Bollinger | Zeile nur an den Extremen | nein — 89 % fehlten |
| OBV, VWMA, POC | nur ±1, Rohwert `None` | nein |

Zwei Codezeilen erklären das: `if richtung is None: continue` warf jede
neutrale Beobachtung weg, und für die drei Volumen-Instrumente war gar kein
Wert-Schlüssel eingetragen. Eine Reparatur der Kodierung allein hätte daran
nichts geändert — sie wirkt auf künftige Snapshots, nicht auf das Archiv.

### Was gebaut wurde

- **`database.KursHistorie`** + `services/kurshistorie.py` — die tägliche
  OHLCV-Reihe als eigener Bestand. Der Backfill hatte sie bisher abgerufen,
  durch den Score geschickt und verworfen. **Eine Reihe wird immer als GANZES
  geschrieben**, nie zeilenweise ergänzt: yfinance bereinigt zum
  Abrufzeitpunkt, und ein Mischbestand aus zwei Abrufen trüge zwei
  Anpassungsbasen. Ein leerer Abruf löscht nicht.
- **`wert_numeric`** auf `analyse_snapshot_indikatoren` — die gemessene Größe
  in ihrer eigenen Einheit. Bewusst der Rohwert und keine Normierung: eine
  Deutung beim Schreiben einzubacken ist der Fehler, um den es geht.
- **Neutrale Zeilen** werden geschrieben (Beitrag 0). Die Rohgröße
  entscheidet, OB eine Beobachtung existiert; die Richtung nur, was sie
  beiträgt. Die Leaderboards filtern bereits `beitrag_numeric != 0` und
  schliessen sie von selbst aus.
- **`auswertung/handbuch.py`** — Quintile der Rohgröße gegen den Markt, plus
  `jahresstabilitaet()` und `bedingt()`.
- **`services/volumen.py`** + `auswertung/volumen.py` — echter Umsatz.

**Nebenbefund, mit korrigiert:** `_score_volume` initialisiert
`obv_bullish`/`vwap_bullish`/`poc_bullish` mit False und lässt sie dort
stehen, wenn der Indikator gar nicht berechenbar ist. `_aus_bool` las das als
**bearisch** — der Snapshot trug ein Verkaufssignal, wo das Scoring weder
`cat_scores` noch `cat_max` erhöht hatte. Die Richtung kommt für diese drei
jetzt aus dem Vorzeichen der Rohgröße (`_aus_rohwert`).

### Das Handbuch: 10 Instrumente × 3 Horizonte, Šidák über alle 210 Zellen (z = 3,67)

Trainingsteil, HISTORISCH, n = 157.187 je Instrument. **Vier signifikante
Zellen von 150, alle auf sieben Tagen.** Auf 30 und 90 Tagen trägt nichts.

| | Q1 | Q2 | Q3 | Q4 | Q5 | Spread |
|---|---|---|---|---|---|---|
| **FVG** | 48,7 | 49,0 | 49,2 | 50,2 | **51,1** SIG | +2,4 pp, monoton |
| **MACD** | **50,9** SIG | 50,0 | 49,3 | 49,4 | **48,6** SIG | −2,3 pp |
| **Trend (SMA 200)** | 49,1 | 48,7 | 49,2 | 50,3 | **50,8** SIG | +1,7 pp |
| RSI, Stochastic, Bollinger, OBV, VWMA, POC, SMA-Cross | | | | | | nichts |

**Der RSI ist jetzt zum ersten Mal vollständig gemessen**: 21.407 Zeilen unter
der alten Kodierung gegen 188.347 heute — also 11,4 %, exakt die 89 %, die
gefehlt haben. Über den ganzen Bereich trägt er **nichts**.

### Die Gegenprobe zu §2h fällt gemischt aus

Das war der eigentliche Grund für den Aufwand: §2h hatte genähert gerechnet
(acht Tage Kadenz, ~35 Stützstellen statt 200) und die exakte Nachrechnung im
eigenen Docstring eingefordert.

| | §2h genähert | jetzt exakt |
|---|---|---|
| Trend (SMA 200) | 2,0 pp, monoton | 1,7 pp, Q5 signifikant, **nicht monoton** |
| SMA-Cross (20/50) | **2,9 pp, monoton** | **+0,2 pp — flach, nichts** |

**Der stärkste Befund aus §2h überlebt die exakte Nachrechnung nicht.** Er war
ein Artefakt der genäherten Reihen. Nicht neu zitieren.

### Jahresstabilität — und was 7 von 9 wert ist

| | | Ausreisser |
|---|---|---|
| Trend (SMA 200) | 7 von 9 | 2019 (−1,5), 2022 (−1,1) |
| FVG | 7 von 9 | 2019 (−0,7), 2022 (−2,8) |
| MACD | 6 von 9 | Vorzeichen kippt +2,4 bis −6,1 → **erledigt** |

Binomial gegen reinen Zufall — **diese Tabelle gehört ab jetzt an jede
Jahresprüfung**, sonst liest man 7 von 9 als Bestätigung:

```
6 von 9 → p = 0,51      7 von 9 → p = 0,18
8 von 9 → p = 0,039     9 von 9 → p = 0,004
```

PEADs Miss-Seite (§2e) steht bei 8 von 9 und bleibt damit der einzige Eingang,
dessen Jahresstabilität sich von Zufall unterscheiden lässt.

### FVG und Trend sind EIN Kandidat, nicht zwei

Rangkorrelation der Rohgrößen **0,729** (Schwelle aus §2f: 0,30). Das erklärt
die identischen Fehljahre. Die Verbundtabelle zeigt die Konzentration:

```
           FVG Q1      Q2      Q3      Q4      Q5
  Trend Q1 24.073   8.535   3.089   1.229     442
  Trend Q5    459   1.467   4.205   9.861  21.496
```

Bedingt sieht es asymmetrisch aus (FVG hält in 4 von 5 Trendschichten, Trend
nur in 2 von 5 FVG-Schichten). **Das ist kein Befund**: die Eckzellen tragen
442 bis 1.500 Zeilen statt 31.000, und keine Zelle übersteht die Korrektur.

### Echtes Volumen: null von 75 Zellen (BC-01 beantwortet)

Fünf Kennzahlen aus `kurs_historie`, ohne einen neuen Abruf. Šidák über alle
105 Zellen (z = 3,49):

| Kennzahl | 7 T | 30 T | 90 T |
|---|---|---|---|
| Relatives Volumen | +0,6 | +0,0 | −0,4 |
| Volumen-Trend (20/60) | +0,5 | +0,7 | −0,4 |
| Ausbruchs-Bestätigung | +0,3 | −0,3 | −1,2 |
| Tagesspanne | −0,9 | +0,6 | +3,7 |
| Eröffnungslücke | −1,2 | +1,9 | +3,7 |

**Keine einzige Zelle signifikant.** Die beiden Auffälligkeiten auf 90 Tagen
sind auf **ihrem** Horizont nachgeprüft (nicht auf sieben): je 5 von 9 Jahren,
Ausschläge von −12,3 bis +25,4, Gipfel 2020. Das ist der Volatilitätsausbruch,
nicht die Kennzahl.

### Was daraus folgt

1. **Das Messgerät ist repariert**, der Bestand vollständig neu vermessen.
   Zehn Instrumente in voller Auflösung statt zwei.
2. **Es gibt EINEN Kandidaten**: Chartlage, nur 7 Tage, 7 von 9 Jahren
   (p = 0,18). Nicht belegt, geht nicht in den Score.
3. **Die Leitidee „weg vom Kurs" ist zweimal widerlegt.** Nach den Accruals
   (§2g) trägt mit Volumen ein zweiter kursunabhängiger Eingang nichts. Die
   Gemeinsamkeit der Nullbefunde liegt **nicht** in der Herkunft der Größe.
4. Trefferquote bei „plausibles Signal trägt auch": **null von neun.**

---

## 2k. Die Renditespanne — der letzte blinde Fleck, und er war leer (S6)

Bis hierher hing **jedes** Urteil dieses Projekts an der **Trefferquote**. Die
mittlere Überrendite wurde berechnet, aber nie auf Signifikanz geprüft, also
nie zu einem Urteil. Beide Größen können auseinanderlaufen: ein Eingang, der
selten recht hat und dabei viel gewinnt, ist nach der Quote Rauschen und nach
der Rendite ein Faktor. Die Literatur misst durchgehend das Zweite.

`basis.fehlerspanne_mittelwert_pp()` schließt das — über die **effektive**
Stichprobe, wie bei der Quote.

### Ein Fehler, der hier stehen bleibt, weil er lehrreich ist

Der erste Durchlauf meldete **47 signifikante Zellen von 150** statt vier. Das
Muster hat ihn verraten: **Q1 UND Q5 desselben Instruments positiv**, bei allen
zehn Instrumenten, mit Werten proportional zum Horizont. Ein Signal kann nicht
an beiden Enden gleichzeitig gut sein.

```
Grundgesamtheit TRAIN, mittlere Überrendite:
   7 Tage  +0,040 pp     30 Tage  +0,304 pp     90 Tage  +0,832 pp
```

Die vermeintlichen Funde lagen genau darauf. Geprüft wurde gegen **null** statt
gegen die Grundgesamtheit — dieselbe Falle wie 50 % statt 48,1 % bei der Quote
(§2b), nur gespiegelt: **gegen null sieht jede Auswahl nach einem Vorsprung
aus.** `mittlere_ueberrendite()` liefert den Bezugspunkt jetzt, je Jahr und je
Schicht getrennt; ein Regressionstest hält den Fehler fest.

Korrigiert: **47 → 8** Zellen im Handbuch, **18 → 13** beim Volumen.

### Was übrig blieb — und woran es starb

Die Rendite sah tatsächlich etwas, das die Quote nicht sah: Mean Reversion bei
**allen drei** Oszillatoren, beide Enden, entgegengesetztes Vorzeichen.

```
RSI 7T    Q1 +0,13 ±0,10    Q5 −0,08 ±0,08
Stoch     Q1 +0,13 ±0,10    Q5 −0,11 ±0,08
Bollinger                   Q5 −0,12 ±0,08
```

Die Jahresprüfung, jetzt auch auf der Rendite (`ertrag_vorzeichen_gleich`),
erledigt es: RSI **5 von 9**, Stochastic und Bollinger je **7 von 9**
(p = 0,18). Der Verlauf zeigt, woher es kommt — **2020 trägt −1,20 / −1,29 /
−1,18**, das Vier- bis Sechsfache jedes anderen Jahres. Ohne 2020 bleibt
Streuung um null.

Ebenso beim Volumen: Tagesspanne und Eröffnungslücke tragen auf der Rendite
monoton über alle fünf Quintile (90 Tage: −1,00 / −0,81 / −0,07 / … / +2,24),
sind aber **Volatilitätsmaße**. Ein volatiler Titel hat allein wegen der
Rechtsschiefe seiner Verteilung einen höheren arithmetischen Mittelwert, ohne
häufiger vorn zu liegen — Konvexität, keine Prognose. Jahresweise 5 von 9,
Gipfel 2020.

**S6 ist geschlossen: der blinde Fleck war echt, und er war leer.** Beide
Metriken stehen ab jetzt nebeneinander in jeder Zelle.

---

## 2l. Das Journal wird automatisch geführt — und ein Fehler wird korrigiert

### Der Fehler zuerst, weil er eine Diagnose in §5 widerlegt

`PositionStopHistorie.position_id` trägt einen Fremdschlüssel auf
`positions.id`, aber **keine `relationship()`**. SQLAlchemy kannte die
Abhängigkeit deshalb nicht und ordnete die Inserts frei an; mit
`PRAGMA foreign_keys=ON` scheiterte die Historie an einem `IntegrityError`,
bevor die Position geschrieben war.

**Jeder Kauf mit Stop-Loss ist daran gescheitert.** Genau deshalb stand
`position_stop_historie` bei null Zeilen. Die frühere Diagnose — Abschnitt C
sei an Daten des Besitzers blockiert — **war falsch.** Ein `session.flush()`
vor dem Vermerken behebt es; fünf Tests gegen eine In-Memory-Datenbank mit
aktivem Pragma halten es fest (die Fixture prüft, dass der Pragma wirklich
greift — sonst wäre der Test eine leere Hülle).

### Die Automatik

Der Nutzer trägt die Position ein, das Programm schreibt den Rest.

```
add_position()    legt den Journaleintrag an — in DERSELBEN Transaktion
close_position()  schließt ihn ab: P&L, Status, R-Multiple, Haltedauer
```

Kein zweiter Session-Aufruf: SQLite lässt im WAL-Modus nur einen Schreiber zu,
und beides soll gemeinsam entstehen oder gar nicht.

**Der eigentliche Zweck ist `einstiegs_snapshot_id`.** Sie zeigt auf die
`NEUE_POSITION`-Analyse, die die Entscheidung getragen hat — die letzte **vor**
dem Kauf, nicht die aktuelle. Damit wird zum ersten Mal die Frage beantwortbar,
für die die Snapshot-Engine gebaut wurde: nicht „wie oft trifft die Engine
gegen den Markt", sondern **„wie sind MEINE Trades gelaufen, wenn die Engine
dieses Signal gab"**. `einstiegs_analyse_alter_tage` hält fest, wie alt sie beim
Kauf war — ohne die Angabe sähe eine drei Monate alte aus wie eine vom Kauftag.

Das R-Multiple rechnet gegen den **initialen** Stop, nicht gegen den
nachgezogenen: derselbe Trade ergibt gegen einen auf 99 nachgezogenen Stop
+20 R statt +2 R. Deshalb liegt `stop_initial` im Journaleintrag und nicht in
der Position, die sich mitbewegt.

**Entscheidungen des Besitzers (2026-09-04):** die 25 Testeinträge sind
gelöscht; Altbestand wird **nicht** nachgetragen, die Automatik läuft ab dem
nächsten Kauf. Der Freitext bleibt optional — er ist das einzige Feld, das
sich nicht rekonstruieren lässt.

---

## 2m. Die Oberfläche erfand eine zweite Empfehlung

`templates/partials/analysis_content.html` leitete aus der Confidence **eigene**
Schwellen ab:

```
Template   KAUFEN 70 | HALTEN 55 | NEUTRAL 40 | NICHT KAUFEN darunter
Engine     75 Starkes Kaufsignal | 60 Kauftendenz | 45 Neutral | 30 Kein
           Einstieg | darunter Meiden
```

Bei Confidence 72 stand im Kasten „KAUFEN" und direkt darüber „Kauftendenz" —
zwei Wahrheiten für dieselbe Zahl, und die lautere stand kleiner. **2.1.0 und
2.2.0 haben die Empfehlungslogik zweimal geändert, ohne dass dieses Duplikat
mitgezogen hätte.** Das Template zeigt jetzt `score_label` der Engine und
leitet nichts mehr ab.

Zugleich heißt die Zahl nicht mehr „/ 100", sondern **„Einigkeit"**, mit einem
Satz darunter: sie misst, wie einig sich die Indikatoren sind, nicht wie
wahrscheinlich der Kurs steigt. Marktbereinigt trennt die Kurve nicht (§2b).
Die Zahl bleibt als Sortier- und Filtergröße stehen; nur die Deutung als
Wahrscheinlichkeit ist weg.

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
| **P3-01 Stop-Historie** | `database.PositionStopHistorie`, `services/watchlist.py` |
| **P3-01 MAE/MFE + Fenster seit Einstieg** | `services/scoring.py`, `position_metrics_engine.py` |
| **P3-05 Auswertungsfläche Positionspfad** | `auswertung/position.py`, `/signals/positionen` |
| **PC-04 ADX-Vorzeichenfehler behoben (1.2.0)** | `services/scoring_engine_v2.py` |
| **Analyse-Router protokolliert** | `routers/analysis.py` (drei stille Fehlerpfade) |
| **P2-06 PEAD: Earnings-Bestand (47.176 Ereignisse)** | `database.EarningsEvent`, `services/pead.py` |
| **P2-06 PEAD gemessen, Kaufseite negativ** | `snapshot_engine/auswertung/pead.py`, `tests/test_pead.py` |
| **Šidák-Korrektur zentral** | `auswertung/basis.py` (`z_korrigiert`, `fehlerspanne_korrigiert`) |
| **P2-06 Analystenrevisionen: Bestand (175.197 Handlungen)** | `database.AnalystenRevision`, `services/analyst_revisions.py` |
| **P2-06 Revisionen gemessen, beide Bauweisen negativ** | `auswertung/analyst_revisions.py`, `tests/test_analyst_revisions.py` |
| **Gemeinsame Zellenrechnung der Kandidatenmessungen** | `auswertung/basis.py` (`zelle_gegen_markt`) |
| **P2-06 Accruals: SEC-Bestand (6.556 Jahresabschlüsse)** | `database.AccrualKennzahl`, `services/accruals.py` |
| **P2-06 Accruals gemessen, negativ** | `auswertung/accruals.py`, `tests/test_accruals.py` |
| **Kursnähe-Prüfung als stehende Regel** | `auswertung/kursnaehe.py` (geeicht: 0,47 vs. −0,001) |
| **§2h Stetige Kodierung gegen binäre, Kontrollversuch** | `services/stetige_indikatoren.py`, `auswertung/kodierung.py` |
| **§2i Regime-Gate geprüft (marktweit), negativ** | `services/marktregime.py`, `auswertung/regime.py`, `tests/test_marktregime.py` |
| **§2j Kursreihe als eigener Bestand (1,47 Mio Tage)** | `database.KursHistorie`, `services/kurshistorie.py`, `tests/test_kurshistorie.py` |
| **§2j BC-04 behoben: `wert_numeric` + neutrale Zeilen** | `snapshot_engine/models.py`, `snapshot_service.py`, `services/scoring.py`, `tests/test_indikator_rohwerte.py` |
| **§2j Backfill hält die Rohreihe fest** | `snapshot_engine/backfill_service.py`, `backfill_cli.py` |
| **§2j OBV/VWMA/POC: „nicht berechenbar" war bearisch** | `snapshot_service._aus_rohwert`, `services/technical.py` (`obv_slope`) |
| **§2j Neuaufzeichnung durchgeführt (Job #3)** | 188.347 Snapshots, 5h 55m, 5 Ticker ohne Kursdaten |
| **§2j Handbuch: Quintile je Instrument** | `auswertung/handbuch.py`, `tests/test_handbuch.py` |
| **§2j Jahresstabilität als stehendes Kriterium** | `handbuch.jahresstabilitaet()` |
| **§2j Redundanzprüfung zweier Instrumente** | `handbuch.bedingt()` |
| **§2j BC-01 beantwortet: echtes Volumen, negativ** | `services/volumen.py`, `auswertung/volumen.py`, `tests/test_volumen.py` |
| **§2k Fehlerspanne auf der Rendite (S6)** | `auswertung/basis.py` (`fehlerspanne_mittelwert_pp`, `mittlere_ueberrendite`), `tests/test_renditespanne.py` |
| **§2k Jahresprüfung auch auf der Rendite** | `handbuch.jahresstabilitaet` (`ertrag_vorzeichen_gleich`) |
| **§2l Journal automatisch geführt** | `services/watchlist.py`, `database.JournalEntry`, `tests/test_journal_auto.py` |
| **§2l Fremdschlüssel-Fehler in der Stop-Historie behoben** | `services/watchlist.py` (`session.flush()`) |
| **§2l Additive Spaltenmigration für Kerntabellen** | `database._spalten_ergaenzen()` |
| **§2m Confidence = Einigkeit, Template ohne eigene Schwellen** | `templates/partials/analysis_content.html` |

**Wichtig (überholt seit der Neuaufzeichnung):** Der Satz „alle
Bestands-Snapshots tragen `score_version` 1.0.0" galt für die stillgelegte
Generation. Seit Job #3 trägt der gesamte HISTORISCH-Bestand **2.2.0**, und
die Aussage dahinter bleibt richtig: weder der sperrende Zweig noch die
Beförderung hat je einen gespeicherten Snapshot beeinflusst, beide wirkten nur
auf die angezeigte Empfehlung.

**Die Score-Version ist bei 2.2.0 geblieben, obwohl heute erheblich geändert
wurde.** Das ist Absicht und folgt der Regel aus §7: erhöht wird, wenn aus
denselben Eingaben ein anderer Teilscore entstünde. BC-04 ändert, was ein
Snapshot *festhält*, nicht wie *bewertet* wird — keine Zeile in `_finalize_score`
ist angefasst.

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
- **BC-01 ist weiterhin wahr, aber nicht mehr offen.** Die volume-Kategorie
  misst nach wie vor kein Volumen (VWMA = Momentum(20), OBV-Slope =
  Momentum(20), POC = Momentum(252)) — echtes Volumen ist inzwischen jedoch
  **gemessen** und trägt nichts (§2j, null von 75 Zellen). Die Lücke, die
  BC-01 benannte, ist damit geschlossen: nicht durch einen Umbau, sondern
  durch das Ergebnis.
- **BC-03 ist behoben.** Fünf von sechs Preis-Positions-Messungen feuerten auf
  100 % der Snapshots, RSI und Bollinger nur auf 11 %. Seit der
  Neuaufzeichnung tragen **alle zehn Instrumente 100 % Abdeckung** mit
  Rohwert; die 11 % waren eine Eigenschaft des Schreibpfads, nicht der
  Indikatoren.
- **BC-02 ist widerlegt.** Sie lautete: „die einzige Kategorie mit Vorsprung
  wird von der ohne gekippt" — Grundlage war der Oszillator-Vorsprung. Gegen
  den Markt hat der Oszillator keinen: +0,3 pp bullisch, −0,4 pp bearisch,
  beides Rauschen (§2b). Es gibt kein gutes Signal, das gerettet werden müsste.
- **P2-04** (die additive Form kann keine Interaktionen ausdrücken) stand auf
  demselben Beleg: „überverkauft gegen den Trend +4,8 pp". Diese Interaktion
  ist exakt die Mean-Reversion-Beförderung, die in 2.2.0 entfallen ist, weil
  marktbereinigt nichts von ihr bleibt.
- ~~**BC-04: die Kodierung vernichtet die Eingänge**~~ → **behoben und
  nachgemessen (§2j).** Jede Indikatorzeile trägt seit dem 2026-09-03 ihre
  Rohgröße in `wert_numeric`, neutrale Beobachtungen werden aufgezeichnet, und
  der Bestand ist damit neu vermessen. Die Diagnose war richtig — die
  Aufzeichnung hat Information vernichtet.
  **Der erhoffte Ertrag ist trotzdem ausgeblieben.** In voller Auflösung
  bleiben vier signifikante Zellen von 150, alle auf sieben Tagen, und der
  stärkste Beleg aus §2h (SMA-Cross, 2,9 pp monoton) erweist sich als Artefakt
  der genäherten Reihen: exakt gerechnet sind es +0,2 pp.
- **Konsequenz, erneut revidiert:** die frühere Begründung („nichts umbauen,
  solange kein Eingang einen Vorsprung trägt") war zirkulär, weil sie in einer
  Kodierung prüfte, die einen Vorsprung nicht sichtbar werden lassen konnte.
  Dieser Einwand ist erledigt — jetzt ist in der richtigen Kodierung geprüft,
  und es trägt weiterhin nichts. **Der Umbau des Composites bleibt
  zurückgestellt, und zum ersten Mal ohne Zirkelschluss:** es gibt keinen
  Eingang, dessen Vorsprung eine andere Arithmetik retten müsste.

### C. Positionspfad — Messung läuft, Auswertung fehlt
- ~~**P3-03** erzeugt keine Snapshots~~ → erledigt UND **nachgeprüft**. Der
  Bestand stand tagelang auf null, was zwei völlig verschiedene Ursachen haben
  konnte: nie aufgerufen, oder still gescheitert. Ein echter Aufruf von
  `POST /analysis/position/load` hat genau eine Zeile erzeugt — der Pfad
  funktioniert, er war nur nie benutzt worden. Der Bestand beginnt jetzt;
  die ersten Outcomes werden 7 Tage nach dem ersten Aufruf fällig.
  Dass die Frage überhaupt offen war, lag am fehlenden Protokoll (siehe
  P4-11).
- ~~**P3-05** keine Auswertungsfläche für `BESTEHENDE_POSITION`~~ → **gebaut,
  wartet auf Daten.** `snapshot_engine/auswertung/position.py` mit eigener
  Abfrage und eigener Grundgesamtheit; Seite unter `/signals/positionen`, von
  `/signals` aus verlinkt. Die Trennung zum Einstiegspfad bleibt bestehen und
  ist der Grund für ein eigenes Modul statt eines Parameters:
  `confidence` trägt hier den Positions-Score, `richtungssignal` entsteht aus
  der Empfehlung statt aus einer Confidence-Schwelle, und `beitrag_numeric`
  läuft von 0 bis 100 mit **neutraler Mitte 50** statt um 0.
  **Die Fragestellung ist eine andere, und das steht jetzt in der Fläche:**
  beim Einstieg lautet sie „wäre der Kauf gut gewesen", bei einer laufenden
  Position „war Halten besser als Verkaufen" — und der Bezugspunkt hängt
  davon ab, was mit dem Erlös geschehen wäre. Absolut beantwortet „besser als
  Kasse", marktbereinigt „besser als Umschichten in den Index". Beide stehen
  nebeneinander; welche zählt, entscheidet die Anlagepraxis.
  **Noch keine Zahlen:** 1 Snapshot, 3 Outcomes, 0 davon fällig. Die Seite
  zeigt das ausdrücklich an, statt wie ein Fehler auszusehen.
- ~~**P3-01** keine Stop-Historie~~ → erledigt. Neue Tabelle
  `position_stop_historie` (via `create_all`, keine Migration nötig);
  `add_position` und `update_position` schreiben fort, `initialer_stop()` und
  `vorheriger_stop()` lesen. Der Einstiegs-Stop erreicht jetzt sowohl
  `validate_target_stop` (Ratchet) als auch `calc_position_metrics`
  (R-Multiple) — beide bekamen vorher fest `None`.
  **Die Herkunftsregel ist der Kern:** ein Eintrag zählt nur dann als
  Einstiegsrisiko, wenn er als `EROEFFNUNG` vermerkt ist. Positionen, die
  schon vor der Historie bestanden, bekommen beim ersten Stop-Wechsel einen
  `ALTBESTAND`-Eintrag — der ist der zuletzt bekannte Stop, nicht der
  ursprüngliche, und taugt deshalb NICHT als Bezugsgröße. Ein bereits
  nachgezogener Stop als Einstiegsrisiko gelesen ließe jede Position besser
  aussehen, als sie war. Für die Ratchet-Prüfung genügt er dagegen.
  **Folge:** ein R-Multiple erscheint erst für Positionen, die ab jetzt mit
  Stop eröffnet werden. Die beiden Bestandspositionen haben ohnehin keinen.
  **MAE/MFE ebenfalls erledigt.** `high_since_entry` lief auf den letzten 22
  Bars, kommentiert als „Best approximation with available data";
  `low_since_entry` wurde nie übergeben. Jetzt bestimmt
  `_fenster_seit_einstieg()` beide über die echte Haltedauer und liefert
  `(None, None)`, wenn die Historie den Einstieg nicht abdeckt — eine
  Näherung wäre dort eine falsche Zahl, und die Engines behandeln None
  sauber (Abzug in `data_quality`).
  **Das war kein kosmetischer Fehler.** An der echten ABEA.DE-Position: Hoch
  seit Einstieg 350,56 statt 332,55 aus der Näherung, Profit-Giveback damit
  **0,776 statt 0,705** — also über der 0,75-Schwelle statt darunter, und
  −20 statt −10 Punkte im Risiko-Teilscore. Deshalb ist
  `POSITION_SCORE_VERSION` auf **1.1.0** erhöht.
  Getrennt davon bleibt der Chandelier-Stop bei 22 Bars: das ist die
  Definition des Verfahrens, keine Näherung. Beide Fenster stehen jetzt
  nebeneinander im Code, mit Begründung.
  MAE und MFE sind neue Metriken (`mae`, `mfe`, als Bruch wie die
  Nachbarfelder, bewusst ohne irreführendes `_pct`-Suffix) und in der
  Positionsanzeige sichtbar. Sie fließen in keinen Teilscore ein — sie
  beantworten die Frage, die eine Trefferquote nicht beantwortet: war der
  Stop zu eng oder das Ziel zu weit?
- ~~**P3-02** SHORT-Pfad unerreichbar~~ → **halb erledigt.** Die Seite kommt
  jetzt aus `position_data["side"]` statt fest verdrahtet
  (`services/scoring.py`); `tests/test_position_side.py` belegt die
  Durchleitung und dass dieselbe Lage je Seite umgekehrt bewertet wird. Die
  Engines konnten SHORT ohnehin immer — es war getesteter toter Code.
  **Offen bleibt die Oberfläche:** das Positionsformular bietet kein
  Seiten-Feld an, liefert also weiter keine Seite und bekommt LONG. Bewusst so:
  der SHORT-Pfad ist durch Tests gedeckt, nicht durch Benutzung, und eine
  Positionsempfehlung ist eine Aussage über echtes Geld.
- ~~**PC-04** ADX wird hier gerichtet gewertet~~ → erledigt, und es war kein
  Konventionsstreit, sondern ein **Vorzeichenfehler**. Der ADX misst
  Trendstärke, nicht Trendrichtung; `adx > 25` brachte trotzdem +10 auf den
  TrendHealthScore — auch mitten im Absturz. Bei `trend_macro_bearish` (−20)
  und `cross_bearish` (−15) hob dieser Bonus zwei Drittel der Cross-Strafe
  auf. Gemessen:

  | Lage | vorher | jetzt |
  |---|---|---|
  | **starker** Abwärtstrend (ADX 40) | 25 | **15** |
  | **schwacher** Abwärtstrend (ADX 15) | 10 | **15** |
  | Aufwärtstrend (ADX 40) | 95 | 85 |

  Ein heftiger Absturz galt also als gesünder als ein milder. Der zweite
  Zweig war derselbe Fehler leiser: `adx < 20` heißt „Trendsignale sind hier
  weniger verlässlich", also Unsicherheit — die gehört in `data_quality`,
  aus genau dem Grund, der zehn Zeilen darüber für die fehlende SMA 200
  steht (PC-01). Beide Zweige sind ersatzlos entfallen, **nicht** durch eine
  richtungsabhängige Fassung ersetzt: das wäre ein neues Gewicht ohne Beleg,
  und ein eigener ADX-Beitrag doppelt zählt ohnehin, was SMA-Cross misst —
  der Grund, aus dem die Einstiegs-Engine ihn seit jeher als Info führt.
  `POSITION_SCORE_VERSION` auf **1.2.0**. P2-03 bleibt offen: den ADX als
  Regime-Gate zu verwenden, ist eine andere Frage als ihn zu addieren.
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
- ~~**P2-03** ADX als Regime-Gate~~ → **in der marktweiten Fassung geprüft
  und negativ (§2i).** Weder Volatilitäts- noch Richtungsregime des Index
  machen ein Signal jahresstabil: im Hochvolatilitätsregime trägt der stetige
  SMA-Cross gepoolt 4,3 statt 1,5 pp, aber weiterhin nur in fünf von acht
  Jahren. Ein Jahr (2023, −15,9 pp) zehrt vier gute weitgehend auf.
  **Offen bleibt die titelbezogene Fassung** — der ADX je Aktie braucht
  Tages-OHLC, die der Bestand nicht führt.
  **Mitgenommen:** die Marktquote unterscheidet sich zwischen den Regimen um
  4,2 pp (51,6 % gegen 47,4 %) — mehr als jeder je gemessene Signalvorsprung.
  Jede Auswertung, die nach Regime trennt, muss gegen die Basis DES REGIMES
  rechnen.
- **P2-05** Fundamentalblock (0,30) wird auf 7–90 Tagen gemessen, passt nicht zur Halbwertszeit
- **P2-06** fehlende Signale. **PEAD ist erledigt und gemessen** (§2e): die
  Abdeckung lag nicht an der Quelle, sondern an einem fehlenden `limit` —
  jetzt 47.176 Ereignisse über 592 Ticker und 94 % der auswertbaren Zeilen.
  Ergebnis: Kaufseite (Q5) Rauschen, Miss-Seite (Q1) −1,1 pp über 7 Tage mit
  in acht von neun Jahren gleichem Vorzeichen. **Kommt nicht in den Score**,
  solange der Holdout nicht gehört wurde.
  **Analysten-Revisionen sind ebenfalls erledigt** (§2f): Konsens-Schätzungen
  gibt es historisch nicht, das Handlungsprotokoll schon (175.197 Zeilen, 523
  Ticker). Netto-Rating null auf allen Horizonten; die Zielrevision ist auf
  7 Tagen beidseitig signifikant, aber nur in sieben von neun Jahren positiv
  (p ≈ 0,18) und zu 0,47 mit der vorangegangenen Kursrendite rangkorreliert —
  also überwiegend recyceltes Momentum. Kommt nicht in den Score.
  **Accruals sind ebenfalls erledigt** (§2g): 6.556 Jahresabschlüsse über 459
  Ticker, punkt-in-zeit aus der SEC. Keine Zelle übersteht die Korrektur, und
  die Form ist ein U statt des vorhergesagten Gefälles. Wichtiger als der
  Nullbefund ist die Kursnähe von **−0,001** — der erste nachweislich
  kursunabhängige Eingang, und er trägt nichts. Damit ist die
  Herkunfts-Erklärung für die Nullbefunde widerlegt.
  **Insider-Cluster ist auf diesem Bestand nicht messbar** (§2g):
  `insider_transactions` reicht nur bis September 2024, der Holdout hätte mehr
  Abdeckung als das Training; ein Quiver-Token ist nicht gesetzt.
  Offen bleiben damit: Short Interest und relative Stärke je Sektor (Letztere
  ist per Konstruktion kursbasiert und liefe in die Falle von §2f).
  Dazu drei Abdeckungslücken: für PEAD fehlen 19 Xetra-Listings von
  US-Konzernen (deren Zahlen liegen unter dem US-Kürzel), für die Revisionen
  85 echte Xetra-Titel (die hat Yahoo gar nicht), für Accruals 109
  Auslandsnotierungen plus 41 US-Filer mit abweichender Auszeichnung. Eine
  Zuordnung Xetra→US schlösse die erste; die anderen bräuchten eine andere
  Quelle.

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

> **Für eine frische Sitzung:** Lies §0, §1, §2j–§2m und diesen Abschnitt.
> Der Rest ist Beleg. §2–§2i beschreibt einen Bestand, den es nicht mehr gibt.

**Der historische Bestand ist ausgemessen — auf BEIDEN Metriken.** Seit der
Neuaufzeichnung (§2j) tragen alle zehn Instrumente ihre Rohgröße, echtes
Volumen ist gemessen, die Kodierung als Erklärung ist erledigt, und seit §2k
wird neben der Trefferquote auch die Renditespanne auf Signifikanz geprüft.
Damit ist zum ersten Mal eine belastbare Antwort möglich — und sie lautet:

> **In den historischen Daten gibt es kein Signal, das die Schwelle nimmt.**
> Ein Kandidat (Chartlage, nur 7 Tage, 7 von 9 Jahren, p = 0,18) und PEADs
> Miss-Seite als Meidungsfilter (8 von 9). Sonst nichts, in neun geprüften
> Familien.

**Das Muster ist inzwischen neunmal belegt:** ein gepoolter Vorsprung, den
die Jahresprüfung aufzehrt. Nicht die Herkunft der Eingänge (§2g Accruals,
§2j Volumen — beide kursunabhängig, beide ohne Beitrag), nicht die Kodierung
(§2j), nicht die Bedingung (§2i), nicht die Metrik (§2k). Wer als Nächstes
etwas vorschlägt, sollte zuerst sagen können, warum es **an der
Jahresstabilität** nicht scheitert.

**Und auffällig oft heißt die Antwort 2020.** Momentum kehrt sich dort um
(unterstes Dezil +11,9 pp), die Oszillator-Mean-Reversion trägt dort das
Vier- bis Sechsfache jedes anderen Jahres, Tagesspanne und Eröffnungslücke
haben dort ihren Gipfel. Ein Kandidat, dessen Vorsprung 2020 entsteht,
ist bis zum Beweis des Gegenteils der COVID-Einbruch mit seiner Erholung.

### Was NICHT mehr taugt

- **Noch eine Signalfamilie.** Neun sind geprüft. Beide Erklärungsversuche für
  die Nullbefunde — falsche Kodierung, falsche Herkunft — sind gemessen und
  ausgeschieden.
- **Der Umbau des Composites.** §2j hat den Zirkelschluss aufgelöst: geprüft
  wurde jetzt in der richtigen Kodierung, und es trägt nichts. Eine andere
  Arithmetik hat nichts zu retten.
- **Das Vorschlagspanel für Gewichte** (DX-01). Gewichtstuning hat an dieser
  Architektur eine Decke, und es gibt keinen Eingang, den es hochzugewichten
  lohnte.
- **Der Holdout** — siehe unten.

### Was bleibt, in dieser Reihenfolge

1. ~~**Abschnitt C**~~ → **entblockt, sammelt jetzt von selbst.** Die frühere
   Diagnose „blockiert an Daten des Besitzers" war falsch: `add_position()`
   scheiterte bei jedem Stop an einem Fremdschlüsselfehler (§2l). Behoben, das
   Journal wird automatisch geführt, die Stop-Historie füllt sich ab dem
   nächsten Kauf. **Ab hier ist es eine Uhr, keine Aufgabe** — es braucht echte
   Trades, keinen Code.
2. **Die LIVE-Uhr laufen lassen.** Die Fundamental- und Sentiment-Hälfte der
   Analyse (elf Indikatoren) ist historisch **prinzipiell nicht prüfbar** —
   der Backfill ruft `calc_technical_score()`, weil `_score_fundamental` und
   `_score_sentiment` ihre Daten aus der Gegenwart beziehen und ein Replay
   damit Look-Ahead wäre. Diese Hälfte ist nur vorwärts messbar, über
   LIVE-Snapshots. Davon gibt es 1.109. Das ist eine Uhr, keine Aufgabe —
   aber es ist der einzige Weg, auf dem diese Hälfte je eine Antwort bekommt.
3. ~~**Die Confidence-Anzeige entschärfen**~~ → erledigt, §2m.

### Vom Besitzer beauftragt, noch nicht begonnen (Stand 2026-09-04)

Die drei folgenden Punkte sind ausdrücklich freigegeben — **ohne weitere
Rückfrage umsetzen**, in dieser Reihenfolge. Aufwand geschätzt: rund 5–8
Stunden Arbeit plus über 70 Stunden Rechenzeit, fast vollständig Punkt C.

**A · Literaturrecherche, als Lesedokument.** Neun Familien wurden ohne
Vorauswahl geprüft; die zehnte soll es nicht. Der Suchbegriff ist **nicht**
„Investment Banking" (das lehrt Bewertung: DCF, Comps, LBO), sondern
**empirical asset pricing / cross-sectional return predictability**.
Ergebnis: was gilt als repliziert, wie wird es konstruiert, was ist mit
diesen Daten baubar. Erwartung vorwegnehmen — diese Literatur sagt über sich
selbst, dass rund zwei Drittel der publizierten Anomalien eine saubere
Replikation nicht überstehen (Hou/Xue/Zhang 2020), publizierte Effekte nach
Veröffentlichung ~58 % verlieren (McLean/Pontiff 2016) und die t-Schwelle bei
~3,0 statt 2,0 liegen müsste (Harvey/Liu/Zhu 2016). **Das hiesige z = 3,67
ist strenger als das, was die Literatur für sich selbst fordert.** Der
Nullbefund ist der Normalfall, sauber gemessen.

**B · Insiderkäufe aus SEC Form 4.** Die offene Signalfamilie, die die
Bewertungsfrage des Besitzers direkt trifft: jemand mit Informationsvorsprung
kauft, während der Chart fällt. Kursunabhängig, punkt-in-zeit datierbar, nach
dem Muster von §2g (`services/accruals.py`, `config.SEC_USER_AGENT`).
**Ausdrücklich NICHT über Quiver:** `services/quiver.py` ist angebunden, aber
es ist **kein Token hinterlegt** (alles läuft über den yfinance-Fallback), die
Endpunkte sind `/live/...` und liefern keine Historie, und drei
`TODO: verify`-Stellen zeigen, dass die Feldnamen nie gegen eine echte Antwort
geprüft wurden. Quiver lohnt erst für Kongress-Trades, und die sind das
schwächere Signal.

**C · Universum erweitern — gezielt, nicht „alles".** Der S&P 500 ist der
schwerste Ort, um eine Anomalie zu finden; die Literatur verortet Effekte in
Small und Mid Cap, und das hiesige Universum ist praktisch reines Large Cap.
Empfehlung: **NASDAQ + NYSE + AMEX ohne ETFs, plus CDAX.** `stock_listings.csv`
führt 17.001 Zeilen, davon NYSE ARCA 2.728 (fast nur ETFs) und OTC 3.816
(nicht sinnvoll handelbar) — realistisch bleiben 6.000–7.000 Stammaktien.
Deutsche Titel fehlen in der Datei ganz und brauchen eine eigene Quelle.
Kosten: ~65 h Backfill, DB 10–15 GB.
**Warnung, die dazugehört:** Survivorship wird dann zum Hauptproblem.
Delistete Firmen sind bei yfinance nicht mehr abrufbar (schon bei 597 Tickern
gingen 5 verloren), und der Mitgliedschaftsfilter aus P4-07 lässt sich auf ein
allgemeines Universum nicht übertragen. Ohne eine Antwort darauf ist jeder
Befund nach oben verzerrt.
### Der Holdout

Er steht bei **0 Zugriffen**. Es liegt eine Aussage vor, die er bestätigen
könnte — PEADs Miss-Seite (§2e): „das unterste Quintil der
Ergebnisüberraschung schlägt den Markt über sieben Tage rund 1,1 pp seltener",
auf dem Trainingsteil bestimmt, korrigiert, in acht von neun Jahren im
Vorzeichen stabil.

Ob dafür ein Zugriff ausgegeben wird, ist eine Entscheidung des Besitzers.
Der Holdout ist einmal verbraucht; wer nach jeder Änderung erneut misst und
die beste Variante behält, hat ihn zum Trainingsset gemacht — nur langsamer.

**Der Chartlage-Kandidat aus §2j gehört ausdrücklich NICHT dorthin.** 7 von 9
Jahren entspricht p = 0,18 und ist von Zufall nicht zu unterscheiden. Die
Regel lautet: der Holdout bestätigt etwas, das die Jahresprüfung bestanden
hat — und das hat bisher nur PEADs Miss-Seite (8 von 9, p = 0,039).

**Die Grenze wurde am 2026-09-03 bewusst NICHT verschoben**, obwohl vorgeschlagen.
Sie auf das Tagesdatum zu setzen hätte den Holdout geleert (Sperrzone 90 Tage,
Daten enden im September) und ihn erst über Jahre aus LIVE-Snapshots wieder
gefüllt. Stehenlassen erhält alle drei Wege — ausgeben, ins Training falten,
oder durch ein besseres Verfahren ersetzen. Sein bekannter Mangel bleibt: er
beginnt am 2025-07-19 und liegt damit vollständig in der KI-Hausse, kann also
Regimestabilität strukturell nicht prüfen. Dafür ist die Jahresprüfung
zuständig (`handbuch.jahresstabilitaet`), nicht er.

Die Neuaufzeichnung hat die Grenze nicht berührt: sie ist ein Datum, und Job
#3 deckt denselben Zeitraum ab.

---

## 6. Verifikation (es gibt keine CI)

```
py -m pytest -q                                   # 475 Tests
py -m mypy <geänderte Dateien>                    # ad hoc, keine Konfiguration im Repo
py -c "import warnings; warnings.filterwarnings('ignore'); from fastapi.testclient import TestClient; import main; c=TestClient(main.app); c.__enter__(); [print(c.get(u).status_code, u) for u in ['/','/signals','/signals/indikatoren','/signals/positionen','/signals/backfill','/analysis','/screener','/watchlist','/journal','/backtesting','/sectors','/economy','/settings','/lexicon','/sources','/directory']]"
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
