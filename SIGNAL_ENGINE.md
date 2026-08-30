# Signal Engine — Befund und offener Plan

_Stand: 2026-08-30 · Score-Version 2.0.0 · Basis: 87.699 Snapshots, 254.905 ausgewertete Outcomes, 608 Ticker_

Arbeitsdokument zur Analyse- und Signalqualitäts-Engine. Ergänzt `REVIEW.md`
(Struktur und Querschnittsthemen) um die inhaltliche Prüfung: rechnen die
Indikatoren das Richtige, und misst die Auswertung, was sie zu messen behauptet.

Interaktive Fassung: <https://claude.ai/code/artifact/0dbcfa21-4049-4568-800b-edfc83b2f3cb>

---

## Der zentrale Befund

Die stärksten Kaufsignale trafen bei 30 Tagen in 56,0 % der Fälle — gegen eine
Basisrate von 55,5 %. Vorsprung: **+0,5 pp bei ±3,8 pp Fehlerspanne**. Nach
Einführung der Fehlerbalken zeigte sich, dass auch die +2,2 pp (7 Tage) und
+2,1 pp (90 Tage) innerhalb ihres eigenen Rauschens liegen. **Auf der Kaufseite
ist derzeit bei keinem Horizont ein Vorsprung belegt.**

Die Verkaufsseite ist dagegen belegt — und belegt falsch: das unterste Band
liegt bei 30 Tagen 5,8 pp unter seiner Basisrate (±2,2 pp).

### Ursache: Gewicht ist nicht Wirkung

Im historischen Modus normalisieren sich die Gewichte auf trend 0,277,
volume 0,185, **oscillator 0,538**. Der Oszillator hält die Mehrheit des
Gewichts — aber nicht der Varianz:

| Indikator | Feuert bei … von 87.720 Snapshots |
|---|---|
| SMA-Cross, Trend 200, OBV, VWMA, POC | 87.719–87.720 (100 %) |
| RSI (14) | 9.728 (11 %) |
| Bollinger Bänder | 9.457 (11 %) |

Fünf der sechs Momentum-Indikatoren haben **keinen neutralen Zustand** und
liefern auf jedem Snapshot ±1. Die Oszillatoren stehen zu 89 % auf null. Eine
Kategorie, die meistens null ist, kann eine gewichtete Summe nicht bewegen —
unabhängig von ihrem Gewicht.

Anteil am gewichteten Ausschlag, und das gemessene Ergebnis dazu:

| Band | trend+volume | oscillator | Vorsprung |
|---|---|---|---|
| 0–29 VERKAUF | 84 % | 16 % | −5,8 pp _belegt_ |
| 30–44 VERKAUF | 85 % | 15 % | −2,2 pp _belegt_ |
| 60–74 KAUF | 98 % | 2 % | −1,4 pp _belegt_ |
| 75–100 KAUF | 51 % | 49 % | +0,5 pp _Rauschen_ |

Die Korrelation ist exakt: Bänder, die von Trend und Volumen dominiert werden,
haben negativen Vorsprung. Das einzige Band, in dem der Oszillator die Hälfte
beiträgt, ist das einzige mit positivem Punktschätzer.

**Folge: die Umgewichtung vom 07.08.2026 konnte nicht wirken.** Trend 0,30→0,18
und volume 0,25→0,12 waren aus gemessener Evidenz richtig abgeleitet — nur war
das Gewicht der falsche Hebel.

### Die Kategorien sind nicht unabhängig

Alle drei „Volumen"-Indikatoren sind Preis-Positions-Maße, die Volumen nur als
Gewichtung verwenden: VWMA = Momentum(20), OBV-Slope = Momentum(20),
POC = Momentum(252). Die Engine misst Momentum sechsmal und nennt die Hälfte
davon Order Flow.

```
trend ↔ volume       +0,553    ← messen dasselbe
volume ↔ oscillator  −0,599    ← heben sich gegenseitig auf
trend ↔ oscillator   −0,276
```

Die −0,599 sind der Kern: die einzige Kategorie mit belegtem Vorsprung wird
nicht nur verdünnt, sondern aktiv gegengerechnet.

### Isoliert ist das Oszillator-Signal belegt

30-Tage-Horizont, HISTORISCH, Signifikanz über die effektive Stichprobe:

```
osc ≥ +0,50  (long)              n=5.154   eff=1.683   +3,2 pp ±2,4   BELEGT
osc ≥ +0,75  (long)              n=1.041   eff=  340   +5,4 pp ±5,2   BELEGT
osc ≥ +0,50 UND trend ≤ −0,50    n=2.452   eff=  800   +4,8 pp ±3,4   BELEGT
osc ≤ −0,50  (short)             n=9.134   eff=2.983   +0,7 pp ±1,8   Rauschen
Gesamtes Universum (Kontrolle)   n=83.606  eff=27.311  ±0,0 pp ±0,6   Rauschen
```

Monoton steigend mit der Schwelle — die Signatur eines echten Signals. Die
Kontrollzeile belegt, dass das Verfahren keine Vorsprünge erfindet. Der Effekt
ist **long-only**; die Short-Seite ist bei jeder Schwelle Rauschen.

---

## Umgesetzt

| # | Thema | Kern |
|---|---|---|
| P0-01 | Score-Versionierung | `SCORE_VERSION` je Snapshot; Bestand auf 1.0.0 |
| P1-01 | Kalibrierungs-Fazit | vergleicht gegen die Basisrate; neuer Status `kein_vorsprung` |
| P1-02 | Datenmodi getrennt | Vorgabe HISTORISCH; `vermischung_pruefen` warnt |
| P1-07 | Fehlerbalken | 95 % über effektive Stichprobe; Vorsprung im Rauschen bleibt grau |
| P1-08 | NEUTRAL-Band | nennt den Grund seiner Leere |
| P4-01 | Sektor-Zuordnung | `services/sector_map.py`; Healthcare-Zweig griff nie |
| P4-02 | Split-Sicherheit | Basiskurs aus derselben Reihe; `basis_kurs` je Outcome |
| BC-04 | Stochastic | erfasst statt unsichtbar (Bewertung unverändert) |
| BC-05 | MACD | `Granularitaet.INFO` — gemessen, aber ohne Score-Wirkung |
| BC-06 | VWMA / POC | kein Verkaufssignal mehr ohne Richtungsaussage |
| PC-01 | Position-Score | fehlende SMA 200 ≠ Abwärtstrend |
| DX-03 | Verkaufsempfehlung | war bereits unterdrückt; nur die Signal-Historie zog nach |
| DX-04 | Oszillator-Gate | sperrt Confidence ohne Oszillator-Deckung |
| DX-05 | Mean-Reversion-Setup | befördert, was die Confidence sonst verwirft |

Wirkung der Oszillator-Logik, an der Historie rekonstruiert:

```
30 Tage   Empfohlen: Confidence + Oszillator   +2,1 pp ±3,7   Rauschen
          Empfohlen: Mean-Reversion-Setup      +3,9 pp ±3,1   BELEGT
          Gesperrt:  Confidence ohne Oszill.   −1,5 pp ±1,0   BELEGT (negativ)
```

Bemerkenswert: die neu beförderte Gruppe ist belegt, die vom Composite
durchgelassene nicht. **Die Signale, die die Confidence ablehnt, sind besser
als die, die sie annimmt.**

> **Alle Zahlen oben sind in-sample.** Beide Schwellen stammen aus denselben
> Daten. Sie belegen, dass die Umsetzung zur Evidenz passt — nicht, dass der
> Effekt hält. Score-Version 2.0.0 trennt die Bestände; die erste ehrliche
> Aussage kommt aus Beobachtungen ab dieser Version.

---

## Offen

### Messung
- **P1-04 Benchmark-Spalte** — ohne Index-Rendite je Outcome ist keine Trefferquote
  ein Alpha. Trennt „findet steigende Aktien" von „findet High-Beta im Bullenmarkt".
- **P1-05 Walk-Forward-Split** — Gewichte auf allen Daten anzupassen und auf
  denselben zu messen ergibt garantiert ein schmeichelhaftes, bedeutungsloses Ergebnis.
- **P1-06 Horizont je Kategorie** — `STANDARD_HORIZONT = 30` misst jedes Signal
  an derselben Uhr. SMC gehört nicht auf 90 Tage, ein DCF nicht auf 7.
- **P1-03 LIVE ≠ HISTORISCH** _(halb erledigt)_ — Backfill kennt kein Sentiment,
  die Euphorie-Falle kann dort nie gegriffen haben. Entscheidung nötig:
  historisch rekonstruieren oder als eigene `score_version` führen.

### Scoring
- **P2-01 Sektor-Modelle in den Score** — `determine_sector_category` kennt zwölf
  Sektoren mit dem je richtigen Verfahren, wirkt aber nur auf die
  Bewertungs-Anzeige. `_score_fundamental` rechnet generisches DCF auf alles,
  auch auf Banken, REITs und Biotech — innerhalb des größten Gewichtsblocks (0,30).
- **P2-02 Cross-Sectional Momentum** — 12-1-Monats-Relative-Stärke fehlt im
  Einstiegs-Score vollständig.
- **P2-03 ADX als Regime-Gate** — wird berechnet und verworfen. Er misst
  Trendstärke, also genau die Variable, die entscheidet, welches Werkzeug greift.
- **P2-04 Additive Architektur** — Σ(Gewicht × Score) kann Interaktionen nicht
  ausdrücken und lässt die varianzstärkste Eingabe dominieren. Die
  Interaktions-Hypothese hat positiv getestet (+4,8 pp gegen den Trend).
- **P2-06 Fehlende Signale** — PEAD (Grundlage existiert: `Earnings Surprise`,
  772 Zeilen), Analysten-Revisionen statt Konsens-Niveau, relative Stärke je
  Sektor, Short Interest, Insider-Cluster, Accruals.

### Positionsanalyse
- **P3-01 Stop-Historie** — `previous_stop`/`initial_stop` sind immer `None`,
  die dokumentierte Ratchet-Regel kann nicht greifen. R-Multiple, MAE/MFE und
  Drawdown seit Einstieg sind damit nicht berechenbar. Größte Funktionslücke.
- **P3-02 SHORT ist toter Code** — `side` fest auf LONG.
- **P3-03 Keine Snapshots** — alle 87.699 Snapshots tragen `NEUE_POSITION`. Die
  zwölf Teilgewichte sind ungeprüft und ohne Weg zur Prüfung. Instrumentieren
  bringt mehr als auditieren.
- **PC-03 RSI-Bruch** — Mean Reversion an den Rändern, Momentum in der Mitte;
  zwischen RSI 69 und 71 kippt der Beitrag um 15 Punkte.
- **PC-04 ADX gegensätzlich** — im Positionspfad Richtungsbeitrag (+10), im
  Einstiegspfad bewusst ausgeschlossen.
- **PC-06** — `distance_to_stop_pct`, `distance_to_target_pct` und
  `secured_profit_pct_at_stop` werden berechnet und nirgends gelesen.

### Präzision der Daten
- **P4-07 Survivorship** — höchster Hebel. `scoring.py:786` verweigert die
  Umkehrung des unteren Bandes ausdrücklich wegen Überlebensverzerrung. Delistete
  Ticker fallen nach `MAX_OUTCOME_VERSUCHE` still heraus — ein gescheitertes
  Unternehmen ist ein systematisch negatives Ergebnis, das aus der Stichprobe
  verschwindet. Zählen und ausweisen.
- **P4-03 Währungen** — Xetra und US gemischt; jede Summe ohne FX-Umrechnung ist
  falsch, und der Fehler wandert mit dem Wechselkurs.
- **P4-04 Relative Schwellen** — RSI < 30 bei einem Versorger (15 % Vola) und bei
  einem Biotech (70 %) sind verschiedene Ereignisse, identisch bewertet.
- **P4-05 Nenner nahe null**, **P4-06 illiquide Reihen**, **P4-08 Preisspannen
  über fünf Größenordnungen**, **P4-09 ADR-Doppelzählung**.

### Werkzeuge
- **`signal-researcher`** (Agent) — prüft eine Hypothese gegen die gespeicherten
  Outcomes, mit effektiver Stichprobe und Fehlerbalken. Für jeden P2-Punkt nötig.
- **`market-data-integrity`** (Agent) — der P4-Durchgang über Sektoren, Währungen
  und Liquiditätsstufen.
- **`sector-models`** (Skill) — welches Bewertungsverfahren zu welchem Sektor
  gehört und warum.
- **`snapshot-schema`** (Skill) — wann `score_version` steigt, wann
  `neugewichtung` reparieren kann und wann nicht.

---

## Wie es weitergeht — der Engpass ist der Betrieb

Beobachtete LIVE-Daten: 1.077 Snapshots zwischen 2026-03-31 und 2026-08-30, in
Schüben mit wochenlangen Lücken. **Das ist kein Tagesrhythmus** — der 18:30-Cron
läuft nur, solange der Prozess lebt.

Im Dauerbetrieb erzeugt die Engine rund **87 Snapshots pro Tag** (608 Ticker,
Neubewertung frühestens nach `_MIN_HORIZONT` = 7 Tagen). Davon landen etwa 3,5 %
in der beförderten Gruppe. Für eine erste belastbare Aussage auf dem
7-Tage-Horizont braucht es ungefähr 300–500 effektive Beobachtungen — also
**vier bis sechs Monate Dauerbetrieb**. Der 30-Tage-Horizont dauert länger, weil
die Überlappungskorrektur die effektive Stichprobe rund dritteln muss.

Es gibt keine Abkürzung: ein erneuter Backfill erzeugte zwar 2.0.0-Snapshots,
aber über dieselbe Historie, aus der die Schwellen stammen — das bliebe
in-sample.

**Zwei Regeln, solange die Uhr läuft:**
1. Keine Änderung der Scoring-Formel ohne `SCORE_VERSION`-Erhöhung. Eine
   Erhöhung setzt das Fenster zurück.
2. Schwellen nicht senken, weil früh wenig herauskommt — genau das ist die
   Überanpassung, gegen die der ganze Apparat gebaut ist.
