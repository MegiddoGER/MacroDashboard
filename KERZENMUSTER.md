# KERZENMUSTER.md — Reiter „Kursverhalten" in der Analyse

_Stand: 2026-09-09 · Reiter in der Einzeltitel-Analyse · Branch `main`_

---

## 0. Was das ist

Ein Reiter in der Einzeltitel-Analyse. Er erkennt anerkannte Kerzenmuster auf
der Tagesreihe und zeigt sie mit ihrer Ungültigkeitsmarke und der Lage des
Titels — Größe, Liquidität, Jahresband.

Ein Anzeige-Vorhaben: er erzeugt keine Empfehlung und verändert keinen Score.

### Fortschritt — hier weiterarbeiten

| # | Schritt | Stand |
|---|---|---|
| — | Literatur gesichtet, Bestand geprüft, Zuschnitt geklärt | **erledigt 2026-09-09** |
| K1 | `services/kerzenmuster.py` — Erkennung, reine OHLCV-Funktionen | **erledigt** |
| K2 | `tests/test_kerzenmuster.py` — 36 Tests, goldene Szenarien je Muster | **erledigt** |
| K3 | `services/kursverhalten.py` — Lage-Kontext und Ungültigkeitsmarke | **erledigt** |
| K4 | Markierungen im Kerzenchart (`charts.py`, Parameter `treffer`) | **erledigt** |
| K5 | ~~`cached_kursverhalten()`~~ | **entfällt — siehe unten** |
| K6 | Reiter `tab-kursverhalten` in `analysis_content.html` + Router | **erledigt** |
| K7 | 631 Tests grün · `mypy` sauber · 16 Routen 200 · Live-Render geprüft | **erledigt** |

**Der Reiter steht.** Nächste sinnvolle Schritte wären Feinschliff an der
Darstellung — nichts davon ist zugesagt oder offen im Sinne einer Schuld.

**Warum K5 entfallen ist:** die Erkennung kostet auf zehn Jahren Tagesdaten
**27,8 ms** (gemessen, 2.532 Kerzen). Sie läuft auf einer Reihe, die
`cached_stock_details()` bereits im Speicher hält — ein zweiter Cache hätte
Invalidierung und Schlüsselwahl gekostet und nichts eingespart.

**Zwei Dinge, die beim Bauen geprüft wurden und nicht wieder geprüft werden müssen:**

- **Die Währung stimmt.** `hist_1y` steht in der Originalwährung der
  *abgerufenen* Notiz, `stats`-Preise sind nach EUR gerechnet. Deshalb stammt
  im Reiter **jede Preisgröße aus `hist`**, beschriftet mit
  `stats["currency"]`. Das trägt beide Fälle: `resolve_ticker("AAPL")` liefert
  **`APC.DE`** (Xetra, EUR) — die angezeigten Kurse sind dann echte Euro; bei
  einer US-Notiz wären es Dollar, und die Beschriftung folgt mit.
- **Die Erkennung ist gegen echte Daten gegengerechnet.** Auf 2.532
  AAPL-Tageszeilen: bullisches Engulfing 3,59 %, Doji 5,45 % — dieselbe
  Größenordnung wie die Zählung über alle 9,25 Mio Zeilen (3,91 % / 6,13 %).

---

## 1. Was der Reiter leisten soll

Der Besitzer will beim Betrachten eines Titels sehen, **wie sich der Kurs
zuletzt bewegt hat** — in der Formensprache, die im Handel üblich ist — und
daraus ableiten können, ob ein Ein- oder Ausstieg sinnvoll erscheint.

Der Reiter beantwortet vier Fragen, in dieser Reihenfolge:

1. **Was ist passiert?** Welche anerkannten Muster sind zuletzt aufgetreten.
2. **Wo ist es passiert?** Markiert im Chart, nicht nur als Liste.
3. **Wem ist es passiert?** Grösse, Liquidität und Bewertung des Titels —
   dasselbe Muster liest sich bei einem engen Nebenwert anders als bei einem
   Schwergewicht.
4. **Was wäre die Konsequenz?** Wo läge die Marke, ab der das Setup widerlegt
   ist, und wie weit ist sie entfernt.

---

## 2. Die Leitidee — Muster sind Beobachtungen, keine Prognosen

Der Reiter behauptet nicht, dass ein Hammer steigende Kurse bedeutet. Er
behauptet etwas Schwächeres und Belastbareres:

> **Ein Muster ist eine Beobachtung mit einer definierten Ungültigkeitsmarke.**

Bei einem bullischen Engulfing ist das Tief der Engulfing-Kerze der Punkt, an
dem die Ablesung falsch war. Diese Marke ist eine **Struktureigenschaft des
Kursverlaufs**, keine Vorhersage — sie gilt unabhängig davon, ob das Muster
irgendetwas prognostiziert. Genau darin liegt der praktische Nutzen, und genau
deshalb darf der Reiter existieren, ohne eine Prognosebehauptung aufzustellen.

Daraus folgt die Sprachregelung, die im ganzen Reiter durchgehalten wird:

| nicht so | sondern so |
|---|---|
| „Kaufsignal" | „Bullisches Engulfing erkannt" |
| „Kursziel 182 EUR" | „Nächstes Swing-Hoch bei 182 EUR" |
| „Stop bei 164 EUR" | „Ablesung widerlegt unter 164 EUR (−3,1 %, 1,4 ATR)" |
| „starkes Signal" | „mit 2,4-fachem Umsatz gegenüber dem 60-Tage-Median" |

§7 begründet, warum diese Zurückhaltung nicht Bescheidenheit ist, sondern der
Stand der Literatur.

---

## 3. Was schon da ist

### Marktkapitalisierung — bereits vorhanden

`services/market_data.py:242` liest `info["marketCap"]`, rechnet nach EUR um und
gibt es als `market_cap` aus `get_stock_stats()` zurück. **Der Reiter muss dafür
nichts bauen und nichts abrufen.** Ebenso vorhanden: `pe_ratio`, `sector`,
`volatility`, `avg_volume`, die 52-Wochen-Spanne und SMA 20/50/200.

Bewertungskennzahlen darüber hinaus liegen in `services/fundamental.py` und
`services/valuation.py`.

*(Nur der Vollständigkeit halber, weil es in einer früheren Fassung falsch
zugespitzt war: die Rekonstruktion einer **zehnjährigen** Marktkapitalisierungs-
Reihe wäre heikel, weil `kurs_historie` durchgehend split-bereinigt ist
(`angepasst = 1` in allen 9.249.373 Zeilen) und SEC-Aktienzahlen roh sind. Das
betrifft ausschliesslich Rückrechnungen und ist für diesen Reiter ohne
Bedeutung. `yfinance.Ticker.get_shares_full()` liefert im Übrigen eine
Aktienzahl-Historie — für AAPL 420 Stützstellen ab 2015.)*

### Kursreihen — vollständig vorhanden

| | |
|---|---|
| `kurs_historie` | 9.249.373 Zeilen · 4.162 Ticker · 2015-01 bis 2026-09 |
| Spalten | `eroeffnung`, `hoch`, `tief`, `schluss`, `volumen` — volles OHLCV |

Für die Analyseansicht wird ohnehin schon eine Kursreihe geladen
(`routers/analysis.py:197 ff.`); die Mustererkennung hängt sich dort an und
kostet **keinen zusätzlichen Abruf**.

### Wie oft der Reiter etwas zu zeigen hat — gemessen

Über alle 9,25 Mio Zeilen, mit einer provisorischen Definition:

| | Ereignisse | Anteil der Zeilen | grob je Titel |
|---|---|---|---|
| Bullisches Engulfing | 361.108 | 3,91 % | ~1 je 26 Handelstage |
| Bärisches Engulfing | 415.597 | 4,50 % | ~1 je 22 Handelstage |
| Hammer-artig | 745.785 | 8,07 % | ~1 je 12 Handelstage |
| Doji | 567.042 | 6,13 % | ~1 je 16 Handelstage |

**Das ist die eigentlich wichtige Produktzahl:** der Reiter ist nie leer, aber
er läuft auch nicht über. Eine Liste der letzten zehn Treffer deckt bei einem
einzelnen Titel rund ein halbes Jahr ab.

### Vorhandene Bausteine, die nicht neu entstehen müssen

- `charts.plot_candlestick()` — der Kerzenchart steht, Markierungen kommen dazu.
- `smc/indicators.py` — FVG, EQH/EQL, Swing-Punkte sind bereits implementiert.
- `services/technical.py` — ATR und die gleitenden Durchschnitte.
- `services/cache_core.py` — das `cached_*`-Muster für den Abrufschutz.

---

## 4. Der Aufbau des Reiters

Vier Blöcke, von oben nach unten.

### Block 1 — Erkannte Muster

Die letzten zehn Treffer, neueste zuerst:

| Datum | Muster | Richtung | Vortrend | Umsatz | Ungültig unter |
|---|---|---|---|---|---|
| 2026-09-04 | Bullisches Engulfing | long | abwärts | 2,4× Median | 164,20 EUR |
| 2026-08-21 | Shooting Star | short | aufwärts | 0,9× Median | 191,80 EUR |

Die Umsatzspalte ist bewusst dabei: ein Muster auf dünnem Umsatz ist eine
andere Beobachtung als dasselbe Muster auf dem Zweieinhalbfachen.

### Block 2 — Chart mit Markierungen

Der bestehende Kerzenchart, ergänzt um Dreiecke unter bullischen und über
bärischen Treffern, mit dem Musternamen im Hover. Nur die im Zeitfenster
sichtbaren Treffer, sonst wird der Chart unleserlich.

### Block 3 — Lage-Kontext

Hier kommen Marktkapitalisierung und Unternehmenswert ins Spiel — als
**Einordnung des Musters**, nicht als eigenes Signal:

```
Marktkapitalisierung   1,42 Mrd EUR          Nebenwert
Dollar-Umsatz (60 T)   8,3 Mio EUR/Tag       eng — Slippage beachten
Position 52W-Spanne    18 %                  nahe am Jahrestief
Abstand SMA 200        −22,4 %
KGV (nachlaufend)      11,3
```

Der Nutzen ist die Relativierung: ein Umkehrmuster nahe dem Jahrestief bei
einem eng gehandelten Nebenwert ist eine andere Lage als dasselbe Muster bei
einem Schwergewicht im Aufwärtstrend — und das Dashboard sagt das, statt es
dem Betrachter zu überlassen.

### Block 4 — Einstieg und Ausstieg

Für den jüngsten Treffer, rein strukturell:

```
Bullisches Engulfing vom 2026-09-04

Ablesung widerlegt unter    164,20 EUR   (−3,1 %  ·  1,4 ATR)
Nächstes Swing-Hoch         182,40 EUR   (+7,6 %  ·  3,4 ATR)
Verhältnis                  1 : 2,5
```

Kein Kursziel, keine Wahrscheinlichkeit — eine Marke, ein Widerstand und deren
Verhältnis. Für eine **bestehende** Position wird dieselbe Marke gegen den
eingetragenen Stop gehalten, damit sichtbar wird, ob die Struktur den Stop
inzwischen überholt hat.

---

## 5. Module und Bauschritte

Layerung nach `CLAUDE.md`: Logik in `services/`, Router dünn, Vorlagen
gerendert. Kommentare auf Deutsch, `logging.getLogger(__name__)` statt `print()`.

### K1 · `services/kerzenmuster.py`

Reine Funktionen auf OHLCV — kein DB-Zugriff, kein Netz, damit ohne Datenbank
testbar.

```python
MUSTER: dict[str, Muster]                    # die 16 aus Paragraph 6
def vortrend(reihe, i) -> int                # −1 / 0 / +1
def erkennen(reihe, i) -> list[Treffer]      # Muster an Zeile i
def letzte_treffer(reihe, anzahl=10) -> list[Treffer]
```

`Treffer` trägt Datum, Musternamen, Richtung, Vortrend, Umsatzverhältnis und
die **Ungültigkeitsmarke** — letztere gehört in die Musterdefinition, weil sie
je Muster verschieden ist (Engulfing: Tief der Signalkerze; Hammer: Tief des
Dochts; Morning Star: Tief der mittleren Kerze).

### K2 · Tests

Nach `.claude/skills/quant-testing`, Stil von `tests/test_position_management.py`:
je Muster ein goldenes Szenario mit von Hand gerechneten Kerzen, plus die
Randfälle `hoch == tief`, fehlende Vorgängerzeilen, Reihenanfang und `None` in
OHLCV. Ein Test muss zeigen, dass Hammer und Hanging Man **allein am Vortrend**
auseinandergehen (§6).

### K3 · `services/kursverhalten.py`

Setzt Block 3 und 4 zusammen: Lage-Kontext aus `market_data.get_stock_stats()`
und `fundamental`, Swing-Punkte aus `smc/indicators.py`, ATR aus
`services/technical.py`, Abstand zur Ungültigkeitsmarke.

### K4 · Markierungen in `charts.py`

`plot_candlestick()` um einen optionalen Parameter `treffer` erweitern —
zusätzlich, nicht ersetzend, damit die bestehenden Aufrufer unverändert bleiben.

### K5 · `cached_kursverhalten()` in `services/cache_core.py`

Eigene `TTLCache` nach dem Muster der Nachbarn. `clear_all_caches()` erfasst sie
dadurch automatisch (Knopf „Aktualisieren" in der Seitenleiste).

### K6 · Route und Vorlage

Nach `.claude/skills/new-surface`: Reiter `tab-kursverhalten` im bestehenden
Block von `templates/partials/analysis_content.html` (dort liegen schon
`tab-candle`, `tab-smc`, `tab-liq`), Teilvorlage unter `templates/partials/`,
Route in `routers/analysis.py`. **Keine neue Seite** — es ist ein Reiter in der
bestehenden Analyse.

### K7 · Abnahme

```
py -m pytest -q
py -m mypy services/kerzenmuster.py services/kursverhalten.py
```

Plus der Route-Smoke aus `CONTEXT.md` §6 — alle Routen müssen 200 liefern.
`.gitignore` vor dem Commit auf `*.db-wal` / `*.db-shm` prüfen; Pushes auf
`main`, kein Feature-Branch.

---

## 6. Die Muster

Definitionen nach Nison und der kanonischen TA-Lib-Fassung. Hilfsgrössen:

```
koerper       = |C − O|            spanne        = H − L
oberer_docht  = H − max(O, C)      unterer_docht = min(O, C) − L
bullisch      = C > O              baerisch      = C < O
Vortrend      = Vorzeichen von  C[t−1] / C[t−11] − 1
```

Der Vortrend endet bei `t−1` — die Musterkerze selbst geht nicht ein, sonst ist
die Bedingung zirkulär. Zeilen mit `spanne = 0` fallen heraus.

| # | Muster | Richtung | Bedingung | Vortrend | Ungültig |
|---|---|---|---|---|---|
| 1 | Hammer | long | `unterer_docht ≥ 2·koerper` ∧ `oberer_docht ≤ koerper` | abwärts | `L[t]` |
| 2 | Hanging Man | short | Geometrie wie 1 | aufwärts | `H[t]` |
| 3 | Inverted Hammer | long | `oberer_docht ≥ 2·koerper` ∧ `unterer_docht ≤ koerper` | abwärts | `L[t]` |
| 4 | Shooting Star | short | Geometrie wie 3 | aufwärts | `H[t]` |
| 5 | Marubozu bullisch | long | beide Dochte `≤ 0,05·spanne`, bullisch | — | `L[t]` |
| 6 | Marubozu bärisch | short | wie 5, baerisch | — | `H[t]` |
| 7 | Bullisches Engulfing | long | `t−1` baerisch ∧ `t` bullisch ∧ `O[t] ≤ C[t−1]` ∧ `C[t] ≥ O[t−1]` | — | `L[t]` |
| 8 | Bärisches Engulfing | short | `t−1` bullisch ∧ `t` baerisch ∧ `O[t] ≥ C[t−1]` ∧ `C[t] ≤ O[t−1]` | — | `H[t]` |
| 9 | Piercing Line | long | `t−1` baerisch ∧ `O[t] < L[t−1]` ∧ `C[t] >` Körpermitte `t−1` ∧ `C[t] < O[t−1]` | — | `L[t]` |
| 10 | Dark Cloud Cover | short | `t−1` bullisch ∧ `O[t] > H[t−1]` ∧ `C[t] <` Körpermitte `t−1` ∧ `C[t] > O[t−1]` | — | `H[t]` |
| 11 | Bullisches Harami | long | `t−1` baerisch ∧ `max(O,C)[t] ≤ O[t−1]` ∧ `min(O,C)[t] ≥ C[t−1]` | — | `L[t−1]` |
| 12 | Bärisches Harami | short | `t−1` bullisch ∧ `max(O,C)[t] ≤ C[t−1]` ∧ `min(O,C)[t] ≥ O[t−1]` | — | `H[t−1]` |
| 13 | Morning Star | long | `t−2` baerisch ∧ `koerper[t−1] ≤ 0,3·koerper[t−2]` ∧ `t` bullisch ∧ `C[t] >` Körpermitte `t−2` | — | `L[t−1]` |
| 14 | Evening Star | short | Spiegelbild zu 13 | — | `H[t−1]` |
| 15 | Three White Soldiers | long | drei bullische Kerzen, je `C` höher, je `O` im Körper der vorigen, je `koerper ≥ 0,5·spanne` | — | `L[t−2]` |
| 16 | Three Black Crows | short | Spiegelbild zu 15 | — | `H[t−2]` |
| 17 | Doji | keine | `koerper ≤ 0,05·spanne` | — | — |

**Doji trägt keine Richtung** und wird als Unentschlossenheit angezeigt, nicht
als Treffer in Block 4.

**Die Paare 1/2 und 3/4 sind geometrisch identisch** und nur durch den Vortrend
getrennt — das ist die Lehrbuchdefinition und der Grund für den Test in K2.

---

## 7. Warum der Reiter nicht überverspricht

Die Zurückhaltung aus §2 ist keine Stilfrage. Die Literatur zu Kerzenmustern
ist ungewöhnlich klar, und sie ist negativ:

- **Marshall/Young/Rose (2006)**, J. Banking & Finance — DJIA-Titel, Bootstrap.
  Kein Wert.
- **Marshall/Young/Cahan (2008)**, Rev. Quantitative Finance & Accounting — die
  100 grössten Titel der Börse **Tokio, 1975–2004**. Nichts über 30 Jahre,
  nichts in drei Teilperioden, nichts in Hausse oder Baisse. Kerzen sind
  japanisch; die Ausrede „im Westen kennt sie niemand" gibt es nicht.
- **Park/Irwin (2007)**, J. Economic Surveys — 95 moderne Studien, 56 positiv,
  aber durchzogen von Data Snooping und nachträglicher Regelauswahl.
- **Bajgrowicz/Scaillet (2012)**, JFE — DJIA 1897–2011: niemand hätte die
  künftig besten Regeln vorab wählen können, und geringe Handelskosten zehren
  die Leistung auf.

Was in der Nähe *funktioniert*, ist nicht das Muster, sondern die Bedingung:
**Lo/Mamaysky/Wang (2000)**, J. Finance, finden mit Kernregression zusätzliche
Information in geometrischen Mustern — und sagen selbst, dass das keine
Handelbarkeit ist. **Han/Yang/Zhou (2013)**, JFQA, erzielen Alpha mit einer
Durchschnittsregel auf **nach Volatilität sortierten** Portfolios; die Sortierung
trägt, nicht die Regel.

**Der Schluss für dieses Vorhaben:** ein Reiter, der Muster als Kaufsignale
ausgibt, würde etwas behaupten, das mehrfach widerlegt ist. Ein Reiter, der
Muster als Beobachtung mit Ungültigkeitsmarke und Lage-Kontext zeigt,
behauptet nichts Falsches und bleibt nützlich. Der Unterschied liegt
vollständig in der Beschriftung — und deshalb ist die Tabelle in §2 Teil der
Spezifikation und nicht Kosmetik.

---

## 8. Quellen

- Marshall, B. R., Young, M. R., Rose, L. C. (2006): *Candlestick technical
  trading strategies: Can they create value for investors?* Journal of Banking
  & Finance 30, 2303–2323.
  <https://www.sciencedirect.com/science/article/abs/pii/S0378426605002116>
- Marshall, B. R., Young, M. R., Cahan, R. (2008): *Are candlestick technical
  trading strategies profitable in the Japanese equity market?* Review of
  Quantitative Finance and Accounting 31(2), 191–207.
  <https://link.springer.com/article/10.1007/s11156-007-0068-1>
- Lo, A. W., Mamaysky, H., Wang, J. (2000): *Foundations of Technical Analysis.*
  Journal of Finance 55(4), 1705–1765.
  <https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00265>
- Han, Y., Yang, K., Zhou, G. (2013): *A New Anomaly: The Cross-Sectional
  Profitability of Technical Analysis.* JFQA 48(5), 1433–1461.
  <https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/new-anomaly-the-crosssectional-profitability-of-technical-analysis/B9E41049F2E55B4F274D46E72ECA8E29>
- Sullivan, R., Timmermann, A., White, H. (1999): *Data-Snooping, Technical
  Trading Rule Performance, and the Bootstrap.* Journal of Finance 54(5),
  1647–1691. <https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00163>
- Bajgrowicz, P., Scaillet, O. (2012): *Technical trading revisited.* Journal of
  Financial Economics 106(3), 473–491.
  <https://www.sciencedirect.com/science/article/abs/pii/S0304405X1200116X>
- Park, C. H., Irwin, S. H. (2007): *What Do We Know About the Profitability of
  Technical Analysis?* Journal of Economic Surveys 21(4), 786–826.
  <https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-6419.2007.00519.x>
