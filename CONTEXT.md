# CONTEXT.md — Arbeitsstand Signal-Engine

_Stand: 2026-08-30 · HEAD `6f2f3db` · Branch `signal-engine-overhaul` (= `main`)_

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

### b) `.gitignore` ist beschädigt — WAL-Dateien landen im Repo

Commit `6f2f3db` hat die Regeln `*.db-wal` und `*.db-shm` aus `.gitignore`
entfernt und im selben Zug eine **37,3 MB große WAL-Datei** eingecheckt. Der
gelöschte Kommentar hatte genau davor gewarnt. Folgen:

- 37,3 MB Binärdaten dauerhaft in der Git-Historie
- der Fehler wiederholt sich bei **jedem weiteren Commit**, solange die Regeln fehlen
- `SIGNAL_ENGINE.md` (220 Zeilen Doku) wurde im selben Commit gelöscht

**Vor dem nächsten Commit die beiden Regeln in `.gitignore` wiederherstellen**
und `git rm --cached data/macrodashboard.db-wal data/macrodashboard.db-shm`
ausführen. Ob die Historie bereinigt wird (`filter-repo`), ist eine Entscheidung
des Besitzers — Historie umschreiben nie ungefragt.

### c) Pushes gehen auf `main`

Stehende Anweisung des Besitzers. Vom Feature-Branch aus ohne Branch-Wechsel:

```
git merge-base --is-ancestor main <branch>      # Fast-Forward prüfen
git push origin <branch>:main
git fetch origin && git branch -f main origin/main
```

Kein `checkout main` — der Arbeitsbaum trägt meist unzusammenhängende gestagte
Arbeit (`config.py`, `.env.example`, `SNAPSHOT_RUN_TIME`-Verdrahtung), die dabei
gestört würde. Nur die Dateien der jeweiligen Änderung committen.

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

## 3. Erledigt — nicht noch einmal bauen

| Was | Wo |
|---|---|
| Sektor-Normalisierung (yfinance vs. GICS) | `services/sector_map.py` |
| Score-Versionierung, aktuell **2.0.0** | `services/scoring.py`, Changelog im Kopf |
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

**Wichtig:** Es existiert **noch kein einziger Snapshot mit `score_version` 2.0.0**
— alle 88.033 tragen 1.0.0. Die Out-of-Sample-Prüfung des Gates beginnt erst mit
dem nächsten Scheduler-Lauf (18:30). Bis dahin sind alle Gate-Zahlen in-sample.

---

## 4. Offen — nach Wirkung geordnet

### A. Blockiert das eigentliche Ziel (automatische Verbesserung)
- **P1-05** kein Train/Holdout-Split — jede Gewichtsanpassung wäre in-sample. **Härteste Vorbedingung.**
- **P1-04** keine Benchmark-Rendite je Outcome — Trefferquoten sind absolut, kein Alpha
- **P1-06** ein 30-Tage-Takt für alle Kategorien, unabhängig von der Signal-Halbwertszeit
- **P1-03** Backfill kennt kein Sentiment, misst also ein anderes System als das laufende (Designentscheidung offen)

### B. Die strukturelle Ursache (Gate umgeht sie, löst sie nicht)
- **BC-01/02/03 + P2-04** sechs korrelierte Momentum-Messungen dominieren drei meist stille Oszillator-Slots. Das Gate filtert obenauf; der Composite darunter bleibt fehlkomponiert. **Größter offener Posten, architektonisch.**

### C. Positionspfad — kaum begonnen
- **P3-03** erzeugt keine Snapshots → seine zwölf Gewichte sind nicht validierbar. **Gatekeeper für B, C und D unten.**
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

**P3-03 — den Positionspfad instrumentieren.** Als einziger Posten schaltet er
eine ganze Phase frei, und jeder Tag ohne ihn ist ein Tag ohne Evidenz.
Messungen lassen sich für bereits getroffene Entscheidungen nicht nachholen.

Danach **P1-05**, weil ohne Holdout jede Gewichtsanpassung wertlos bleibt.

**Nicht** mit dem Vorschlagspanel für Gewichte anfangen: DX-01 zeigt, dass
Gewichtstuning an dieser Architektur eine Decke hat, und ohne P1-05 validiert es
sich gegen sich selbst.

---

## 6. Verifikation (es gibt keine CI)

```
py -m pytest -q                                   # 15 Tests
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
  die Confidence aus gespeicherten `cat_scores` exakt neu rechnen.
- **Kommentare und Commits auf Deutsch.** Diese Datei und `CLAUDE.md` sind die
  Ausnahme (Meta-Dokumentation, wie `REVIEW.md`).
