# LITERATUR.md — Empirische Kapitalmarktforschung, gegen den eigenen Bestand gelesen

_Stand: 2026-09-04 · Auftrag A aus `CONTEXT.md` §5 · Lesedokument, keine Änderung am Code_

---

## 0. Was dieses Dokument ist

`CONTEXT.md` §5 hält fest: neun Signalfamilien sind **ohne Vorauswahl** geprüft
worden, neun Nullbefunde. Die zehnte soll nicht so entstehen. Dieses Dokument
ist der Vorauswahlfilter — es beantwortet drei Fragen:

1. **Was gilt in dieser Literatur als repliziert**, und wie sicher ist das?
2. **Wie wird es konstruiert**, und wo weicht die eigene Messung davon ab?
3. **Was davon ist mit den Daten baubar, die schon in der Datenbank liegen?**

Der Suchbegriff ist **empirical asset pricing / cross-sectional return
predictability**, nicht „Investment Banking". Letzteres lehrt Bewertung (DCF,
Comps, LBO) — die Frage, was ein Unternehmen wert ist. Hier geht es um die
andere Frage: welche messbare Eigenschaft eines Titels heute etwas über seine
Rendite morgen aussagt. Das sind zwei getrennte Fächer mit getrennten
Zeitschriften.

**Nichts in diesem Dokument ist auf dem eigenen Bestand gemessen.** Es ist
Fremdliteratur. Jede Zahl daraus ist eine Erwartung, kein Befund. Die Regeln aus
§7 der `CONTEXT.md` — Jahresprüfung, Šidák, Holdout — gelten für jeden
Kandidaten hier unverändert.

---

## 1. Die drei Zahlen, die den eigenen Nullbefund einordnen

Das Wichtigste zuerst, weil es die Stimmung des ganzen Projekts betrifft:
**der Nullbefund ist in diesem Fach der Normalfall, nicht das Versagen einer
Messung.**

| Befund | Quelle | Zahl |
|---|---|---|
| Die t-Schwelle müsste bei ~3,0 liegen, nicht bei 2,0 | Harvey/Liu/Zhu 2016 | wegen hunderter paralleler Tests |
| Publizierte Effekte verlieren nach Veröffentlichung | McLean/Pontiff 2016 | **−26 %** out-of-sample, **−58 %** nach Publikation (97 Prädiktoren) |
| Anomalien, die eine strengere Replikation nicht überstehen | Hou/Xue/Zhang 2020 | **65 %** von 452 verfehlen t = 1,96; bei t = 2,78 sind es **82 %** |

Zum Vergleich der eigene Maßstab: **Šidák über 210 Zellen ergibt z = 3,67**
(§2j), über 105 Zellen z = 3,49. **Das ist strenger als das, was diese
Literatur für sich selbst fordert.** Wer hier gegen z = 3,67 nichts findet,
hat nicht schlecht gemessen — er hat strenger gemessen als die Papiere, deren
Effekte er sucht.

Und die vierte Zahl, die am unbequemsten ist:

> Chen/Velikov (2023) rechnen 204 Anomalien nach. **Ab 2006 und ohne Microcaps
> bleibt der Median bei 7 Basispunkten pro Monat.** Nach Handelskosten, mit
> kostenminimierender Ausführung, im Mittel rund **4 bp/Monat.**

Sieben Basispunkte im Monat sind rund 0,8 % im Jahr, vor Kosten, als Median
über alle Anomalien, in genau dem Universum, in dem dieses Projekt misst. Eine
Verschiebung dieser Größe ist mit 188.347 Snapshots über neun Jahre nicht
zuverlässig auflösbar, und sie wäre auch dann keine Handelsentscheidung wert.

---

## 2. Der Replikationsstreit — und warum er kein Streit über Daten ist

Es gibt drei große Arbeiten, die zu drei verschiedenen Schlüssen kommen:

| | Bestand | Ergebnis |
|---|---|---|
| **Hou/Xue/Zhang 2020** | 452 Anomalien | 65 % fallen durch |
| **Chen/Zimmermann 2022** | 319 Prädiktoren | von 161 mit klarer Originalevidenz reproduzieren **98 %** mit t > 1,96; Regression reproduzierter auf originale t-Werte: Steigung 0,88, R² = 0,82 |
| **Jensen/Kelly/Pedersen 2023** | 153 Faktoren, 93 Länder | **über 80 %** replizieren, auch nach Korrektur für multiples Testen |

Das sieht nach einem Widerspruch aus. Es ist keiner. **Die drei rechnen auf
denselben Daten und unterscheiden sich fast ausschließlich in der Methode:**

- **HXZ** rechnen mit **NYSE-Grenzen** (die Quantilsgrenzen stammen nur aus den
  NYSE-Titeln, nicht aus allen) und **wertgewichtet**. Beides drückt Microcaps
  heraus. Von der Kategorie „trading frictions" fallen dabei **96 %** durch.
- **JKP** deckeln die Wertgewichte, damit keine Megacap das Ergebnis allein
  trägt, halten einheitlich einen Monat und rechnen bayesianisch über alle
  Faktoren gemeinsam — die Vielzahl der Faktoren **stärkt** bei ihnen die
  Evidenz, statt sie zu verwässern.
- **Chen/Zimmermann** reproduzieren die Originalarbeiten in deren eigener
  Methode und fragen nur: kommt heraus, was dort steht? Fast immer ja.

**Die drei Fragen sind verschieden:** „steht das Papier?" (CZ, ja), „hält es
unter einheitlicher, umsetzbarer Konstruktion?" (JKP, überwiegend ja), „hält es
ohne die kleinsten Titel und wertgewichtet?" (HXZ, überwiegend nein).

**Für dieses Projekt zählt die dritte Frage**, denn hier wird ausschließlich in
großen Titeln gemessen. Und dort lautet die Antwort der Literatur: überwiegend
nein.

---

## 3. Der Befund, der hier am meisten zählt: Größe

`CONTEXT.md` §5 formuliert die Hürde für jeden neuen Vorschlag: *„Wer als
Nächstes etwas vorschlägt, sollte zuerst sagen können, warum es an der
Jahresstabilität nicht scheitert."* Die Literatur hat eine Antwort auf die
Vorfrage, und die steht in §5 noch nicht auf der Ausschlussliste:

> **Weil der Effekt in diesem Universum nie war.**

Belege, in der Reihenfolge ihrer Härte:

- **Anomalierenditen konzentrieren sich in Microcaps.** Schließt man sie aus,
  überlebt rund ein Drittel. Das ist der Mechanismus hinter HXZ' 65 %.
- **Chen/Velikov 2023:** ab 2006, ohne Microcaps, Median **7 bp/Monat**.
- **Lakonishok/Lee 2001** finden den Insidereffekt (7–8 % über ein Jahr)
  **konzentriert in kleineren Firmen** — derselbe Größenschnitt.
- **Martineau 2022** (siehe §7): PEAD verschwindet bei Nicht-Microcaps um 2001
  und ist bei Large Caps ab etwa 2006 praktisch null.

Das eigene Universum sind **592 Titel, praktisch reines Large Cap**, gemessen
über **2017–2026**. Das ist nach dieser Literatur der Ort und der Zeitraum, an
dem am wenigsten zu finden ist.

**Damit hat der neunfache Nullbefund erstmals eine Erklärung, die weder
Kodierung noch Herkunft noch Metrik ist** — die drei, die §2g, §2j und §2k
bereits ausgeschlossen haben. Sie heißt Universum, und sie ist genau das, was
Auftrag **C** angeht.

### Die unbequeme Folgerung für die Reihenfolge

Der Besitzer hat A → B → C beauftragt, und so wird es umgesetzt. Der
Vollständigkeit halber gehört aber hierher, was die Literatur zur Reihenfolge
sagt:

**Jeder Kandidat aus §6 — und auch B — wird auf dem heutigen Universum
voraussichtlich einen Nullbefund liefern, und dieser Nullbefund wäre nicht
interpretierbar.** Man wüsste nicht, ob das Signal nichts taugt oder ob es nur
nicht in Large Caps lebt. Ein Test nach C beantwortet beide Fragen, ein Test
vor C keine von beiden.

Das ist kein Einwand gegen B — es ist der Hinweis, dass **B nach C deutlich
mehr wert ist als vor C**, bei identischem Bauaufwand. Die Entscheidung liegt
beim Besitzer; ohne gegenteilige Ansage bleibt es bei A → B → C.

---

## 4. Wie die Literatur misst — und wo die eigene Messung abweicht

Der praktisch wichtigste Abschnitt, weil hier Übertragungsfehler entstehen. Ein
Effekt, den die Literatur mit 5 % pro Jahr angibt, erscheint in der eigenen
Messung **weder in dieser Größe noch in dieser Einheit**.

| | Literatur (Standard) | Hier |
|---|---|---|
| Universum | alle US-Titel, ~3.000–5.000, mit **NYSE-Grenzen** | 592 Large Caps, Grenzen aus dem eigenen Bestand |
| Gewichtung | **wertgewichtet** (JKP: gedeckelt) | gleichgewichtete Quintile |
| Portfolio | **Long-Short-Dezil**, Differenz der Extreme | Quintil gegen den Markt, jede Schicht einzeln |
| Haltedauer | 1 Monat, monatlich neu gebildet | 7 / 30 / 90 Kalendertage, tägliche Stichtage |
| Kennzahl | **mittlere Monatsrendite** bzw. Alpha | Trefferquote **und** (seit §2k) mittlere Überrendite |
| Teststatistik | t auf der Zeitreihe der Monatsrenditen | z auf effektiver Stichprobe, Šidák-korrigiert |
| Bilanzdaten | **6 Monate pauschale Verzögerung**, Bildung Ende Juni | `bekannt_ab` aus dem tatsächlichen Einreichungsdatum |

Vier Konsequenzen, die beim Lesen jeder Literaturzahl mitgedacht werden müssen:

**a) Die eigene Bilanzdatierung ist besser als der Standard.** Die Literatur
setzt pauschal sechs Monate an, weil in Compustat kein verlässliches
Einreichungsdatum lag. `services/accruals.py` nimmt `bekannt_ab` als das
späteste der tatsächlichen Einreichungsdaten (Median ~54 Tage). Das ist
punktgenauer und liefert **mehr** verwertbare Zeit je Beobachtung. Hier ist
kein Nachholbedarf.

**b) Die Trefferquote ist nicht die Kennzahl der Literatur — die mittlere
Rendite ist es.** §2k hat das geschlossen, und die Begründung dort ist
dieselbe, die die Literatur gibt: die Quote ignoriert die Größe des Gewinns.
Ein Signal, das in 48 % der Fälle recht hat und dabei mehr verdient, ist nach
der Quote Rauschen und nach der Rendite ein Faktor. **Beide Metriken stehen
inzwischen nebeneinander — das ist der Stand der Kunst, und es war eine echte
Lücke.**

**c) Gleichgewichtung ist hier die *liberalere* Wahl.** Sie gibt den kleineren
der 592 Titel mehr Gewicht, also genau denen, in denen die Effekte laut §3 noch
am ehesten leben. Ein Nullbefund unter Gleichgewichtung ist damit **härter** als
einer unter Wertgewichtung — er schließt auch die günstigere Rechenart aus.

**d) Tägliche Stichtage über 7/30/90 Tage sind keine monatlichen Portfolios.**
Die Überlappung ist über `basis.effektive_stichprobe()` bereits behandelt. Was
bleibt: ein Effekt, der sich über rund 20 Handelstage aufbaut, verteilt sich
hier über drei Horizonte, statt in einer Zahl zu stehen.

### Was die zehn Instrumente in dieser Literatur sind

Der wichtigste Satz dieses Abschnitts, und er ist unangenehm:

> Von den zehn Instrumenten der Einstiegsanalyse (RSI, Stochastic, Bollinger,
> MACD, OBV, VWMA, POC, SMA 200, SMA-Cross, FVG) haben **zwei** in der
> replizierten Querschnittsliteratur überhaupt einen Verwandten: Momentum
> (12-1) und die kurzfristige Umkehr — und beide sind **Renditemaße**, keine
> Indikatorkonstruktionen.

Die Kataloge dieses Fachs — 319 Prädiktoren bei Chen/Zimmermann, 153 Faktoren
bei JKP — bestehen aus Bilanzkennzahlen, vergangenen Renditen, Emissionen,
Analystendaten und Handelsfriktionen. Chartkonstruktionen wie Bollinger-Bänder,
MACD oder Fair-Value-Gaps sind darin **praktisch nicht vertreten** — nicht
widerlegt, sondern nie als Querschnittsprädiktoren behauptet.

**Die neun Nullbefunde messen damit weitgehend eine Familie, für die diese
Literatur nie eine Behauptung aufgestellt hat.** Das entwertet die Arbeit
nicht — es erklärt sie. Und es sagt, wo die zehnte Familie herkommen sollte.

---

## 5. Was als repliziert gilt — 13 Themen, gegen den eigenen Bestand gehalten

JKP fassen 153 Faktoren durch hierarchisches Clustering (Distanz = 1 −
Korrelation, Ward-Verfahren) zu **13 Themen** zusammen. Der Stern markiert
Themen, bei denen gegen die Eigenschaft gewettet wird (hohe Accruals sind
schlecht, nicht gut). **Zehn der 13 gehen mit signifikant positivem Gewicht ins
Tangentialportfolio**; verdrängt werden Profitability, Investment und Size.

| Thema | Status hier | Baubar? |
|---|---|---|
| **Accruals\*** | §2g gemessen — **trägt nichts** | erledigt |
| **Momentum** | §2c gemessen — an der Jahresprüfung gescheitert | erledigt |
| **Size\*** | im Bestand praktisch konstant (reines Large Cap) | **erst nach C** |
| **Investment\*** (Bilanzwachstum) | nie gemessen | **ja, ohne neuen Abruf** (§6.1) |
| **Profitability** | nie gemessen | **ja, ohne neuen Abruf** (§6.1) |
| **Profit Growth** | nie gemessen | **ja, ohne neuen Abruf** (§6.1) |
| **Low risk** (Beta, idiosynkr. Vola) | nie gemessen | ja, allein aus `kurs_historie` |
| **Skewness\*** (MAX / Lotterie) | nie gemessen | ja, allein aus `kurs_historie` |
| **Seasonality** | nie gemessen | ja, allein aus `kurs_historie` |
| **Debt Issuance\*** | nie gemessen | ja, über SEC (§6.3) |
| **Leverage\*** | nie gemessen | ja, über SEC (§6.3) |
| **Value** | nie gemessen | ja, über SEC + Aktienzahl (§6.3) |
| **Quality** | nie gemessen | Komposit aus den obigen — zuletzt |

Zwei weitere Familien liegen außerhalb der 13 Themen und sind hier bereits
gemessen: **PEAD** (§2e, der einzige Fund mit bestandener Jahresprüfung, siehe
§7) und **Analystenrevisionen** (§2f, zur Hälfte der Kurs selbst).

Drei Einzelbefunde, die für die Auswahl unmittelbar zählen:

- **Nettoemission von Aktien** (Pontiff/Woodgate 2008, Daniel/Titman 2006): wer
  Aktien ausgibt, liefert schlechtere Folgerenditen. Nach 1970 statistisch
  **stärker als Size, Value oder Momentum einzeln**, und international
  **robust über kleine und große Firmen** — eine der wenigen Anomalien, für die
  die Größenwarnung aus §3 ausdrücklich nicht gilt.
- **Bruttoprofitabilität** (Novy-Marx 2013) hält der HXZ-Nachrechnung **nicht**
  stand: 0,16 % pro Monat bei t = 1,04. Operative und Cash-Profitabilität
  schneiden in der Nachfolgeliteratur besser ab als die Bruttoform.
- **Kurzfristige Umkehr** trägt bei Large Caps 0,84 %/Monat (t = 5,45) brutto —
  und wird von Handelskosten in der Größenordnung von 1,94 %/Monat vollständig
  aufgezehrt. **Als Messgegenstand interessant, als Strategie tot.**

---

## 6. Was mit DIESEN Daten baubar ist — nach Kosten geordnet

Der eigentliche Ertrag dieser Recherche. Alle Bestandsangaben sind gegen die
Datenbank vom 2026-09-04 geprüft, nicht geschätzt.

### 6.1 Ohne einen einzigen neuen Abruf — die Daten liegen schon da

`accrual_kennzahlen` trägt **6.556 Zeilen, 461 Ticker, Geschäftsjahre
2008–2026**, und in jeder Zeile stehen neben dem Accrual auch `bilanzsumme`,
`netto_gewinn` und `operativer_cashflow` — **jeweils mit `bekannt_ab`**, also
punkt-in-zeit datiert. Erhoben wurden sie für den Accrual; drei weitere
Kennzahlen der Literatur stecken ungenutzt darin:

| Kennzahl | Formel | Thema | Erwartetes Vorzeichen |
|---|---|---|---|
| **Bilanzwachstum** | `bilanzsumme[t] / bilanzsumme[t−1] − 1` | Investment\* | hoch = **schlecht** (Cooper/Gulen/Schill 2008) |
| **Cash-Profitabilität** | `operativer_cashflow / bilanzsumme` | Profitability | hoch = gut |
| **Gewinnwachstum** | `Δ netto_gewinn / bilanzsumme` | Profit Growth | hoch = gut |

Verfügbarkeit: rund 430 Ticker je Jahr mit vollständiger Bilanz **und**
Kapitalflussrechnung, also je Messjahr etwa 400 verwertbare Firmenjahre für das
Bilanzwachstum (es braucht zwei aufeinanderfolgende Jahre). Über neun Jahre
sind das ~3.600 Beobachtungen, die sich nach dem Muster von §2g auf die
Snapshot-Zeilen ihres Gültigkeitsfensters abbilden.

**Aufwand: ein Auswertungsmodul, kein Dienstmodul, keine Netzlast.** Zum
Vergleich: `snapshot_engine/auswertung/accruals.py` hat 245 Zeilen. Das ist der
mit Abstand billigste offene Test im Projekt — **drei der 13 Themen für
ungefähr einen Arbeitstag und null Rechenzeit.**

Die Warnung, die dazugehört: **Investment und Profitability sind genau die
beiden Themen, die JKP aus dem Tangentialportfolio verdrängt**, und die
Bruttoprofitabilität ist bei HXZ durchgefallen. Die Erwartung ist gedämpft.
Der Preis ist aber auch nahe null, und diese drei sind die einzigen Kandidaten,
bei denen das gilt.

### 6.2 Allein aus `kurs_historie` — 1.465.410 Tageszeilen, 592 Ticker, 2016-08 bis 2026-09

Vier Kennzahlen der Literatur, die nur Kurse und Volumen brauchen und deshalb
ohne jeden Abruf entstehen:

| Kennzahl | Konstruktion | Thema |
|---|---|---|
| Kurzfristige Umkehr | Rendite der letzten 21 Handelstage, invers | (Friktionen) |
| Idiosynkratische Volatilität | Reststreuung gegen den Markt, 60 Tage | Low risk |
| MAX / Lotterie | höchste Tagesrendite der letzten 21 Tage | Skewness\* |
| Saisonalität | mittlere Rendite desselben Kalendermonats in Vorjahren | Seasonality |

Alle vier sind **reine Kursgrößen** — und damit trifft sie derselbe Einwand,
den §2j gegen die zehn Instrumente erhebt. Die Leitidee „weg vom Kurs" ist zwar
zweimal widerlegt (§2g, §2j), aber ein fünfter Kursindikator ist trotzdem kein
guter Einsatz, solange §6.1 und §6.3 offen sind. **Nachrangig, ausdrücklich.**

Immerhin: `services/volumen.py` und `snapshot_engine/auswertung/volumen.py`
haben die Infrastruktur dafür bereits gebaut (§2j). Ein weiterer Kandidat
kostet dort wenig — er ist nur wenig wert.

### 6.3 Über die SEC — bewährter Weg, geringe Kosten

**Der wichtigste Punkt dieses Abschnitts**, weil er im Projekt bislang
unterschätzt wird: `services/accruals.py` hat die Punkt-in-Zeit-Anbindung an
die SEC **bereits gelöst und gemessen**. `companyconcept` liefert `filed` an
jeder einzelnen Zahl; `frames` ist geprüft und untauglich (für `CY2020Q1`
stammen 84 % der Werte aus Einreichungen von 2021). Der Bestandsaufbau für drei
us-gaap-Konzepte über 592 Ticker dauerte **rund zehn Minuten**.

Damit ist **jedes weitere us-gaap-Konzept ein Abruf je Ticker**, also
größenordnungsmäßig drei bis fünf Minuten. Was das freischaltet:

| Kennzahl | Konzept(e) | Thema |
|---|---|---|
| **Nettoemission** | Aktienzahl im Zeitverlauf | Debt Issuance\* / Investment\* |
| Buchwert/Marktwert | `StockholdersEquity` + Aktienzahl + Kurs | Value |
| Verschuldung | Fremdkapital / Bilanzsumme | Leverage\* |
| Operative Profitabilität | Umsatz − Kosten, auf Bilanzsumme | Profitability |

**Die Nettoemission ist der stärkste Einzelkandidat dieses Dokuments.** Sie ist
kursunabhängig, punkt-in-zeit datierbar, über den bewährten Weg für wenige
Minuten Rechenzeit erhebbar — und sie ist die einzige der hier geprüften
Familien, für die die Literatur ausdrücklich **Robustheit über kleine und große
Firmen** berichtet. Damit ist sie der einzige Kandidat, der die Größenwarnung
aus §3 überlebt, und der einzige, der auch **vor** C einen interpretierbaren
Befund liefern kann.

Sie beantwortet zudem die Vorabfrage aus §5: sie muss an der Jahresprüfung
nicht scheitern, weil ihr Vorzeichen nicht aus einem Marktregime stammt,
sondern aus einer Unternehmensentscheidung — Emissionen häufen sich in
Hochphasen, und genau darauf beruht der Effekt.

### 6.4 Nicht baubar, und warum

- **Size** als Faktor: das Universum ist praktisch einheitlich groß. Erst nach C.
- **Short Interest, institutionelle Bestände, Analystenabdeckung als Historie**:
  keine Quelle mit Punkt-in-Zeit-Historie angebunden. Quiver hat **kein
  hinterlegtes Token**, seine Endpunkte sind `/live/...` ohne Historie, und drei
  `TODO: verify`-Stellen zeigen, dass die Feldnamen nie gegen eine echte Antwort
  geprüft wurden.
- **Delistete Firmen**: bei yfinance nicht mehr abrufbar. Schon bei 597 Tickern
  gingen fünf verloren (§0c). Das ist die Survivorship-Warnung zu C — und sie
  gilt jeder Messung hier bereits heute.
- **Die Fundamental- und Sentiment-Hälfte der eigenen Analyse**: historisch
  prinzipiell nicht prüfbar (§5), nur vorwärts über LIVE-Snapshots.

---

## 7. Ein Einwand gegen den einzigen eigenen Fund

Der Holdout steht bei null Zugriffen, und der einzige Kandidat für einen
Zugriff ist **PEADs Miss-Seite** (§2e): das unterste Quintil der
Ergebnisüberraschung schlägt den Markt über sieben Tage rund 1,1 pp seltener,
in acht von neun Jahren im Vorzeichen stabil (p = 0,039).

Dazu gehört ab jetzt diese Fremdaussage:

> **Martineau (2022), „Rest in Peace Post-Earnings Announcement Drift":** PEAD
> verschwindet bei Nicht-Microcaps um 2001 und ist bei Large Caps ab etwa 2006
> **praktisch null.** Als Ursachen gelten Dezimalisierung, Reg NMS und
> Hochfrequenzhandel — Kurse passen sich zunehmend schon am Ankündigungstag
> vollständig an. Der Abstand zwischen hohem und niedrigem SUE-Quintil fällt
> von rund 5 % in den 1980/90ern auf 3 % oder weniger Ende der 2010er.
> Kettell/McInnis/Zhao (2022) ergänzen: ein Großteil des Rückgangs erklärt sich
> aus **nachlassender Persistenz der Gewinnüberraschung selbst**, nicht aus
> mehr Arbitrage.

**Das widerlegt den eigenen Befund nicht.** Drei Gründe:

1. Gemessen wurde hier die **Miss-Seite allein** — die Meidungsrichtung, nicht
   der klassische Long-Short-Abstand. Die Abbau-Literatur beschreibt überwiegend
   den Gesamtabstand, und Arbitrage räumt die Kaufseite leichter ab als die
   Verkaufsseite, an der Leerverkaufskosten stehen.
2. Gemessen wurde eine **Trefferquote gegen den Markt**, nicht die Monatsrendite
   eines SUE-Dezils. Die beiden Größen sind nicht ineinander umrechenbar.
3. Der eigene Zeitraum (2017–2026) liegt **vollständig hinter** Martineaus
   Abbaudatum. Ein Effekt, der dort noch acht von neun Jahren im Vorzeichen
   hält, ist damit nicht der klassische PEAD, sondern etwas, das ihn überlebt
   hat — oder ein Zufall mit p = 0,039.

**Was daraus folgt:** Die Fremdliteratur liefert eine konkrete, benannte
Gegenhypothese zu dem einen Befund, für den ein Holdout-Zugriff erwogen wird.
Der Holdout ist einmal verbraucht. **Diese Gegenhypothese gehört auf den Tisch,
bevor der Zugriff ausgegeben wird** — sie senkt die Wahrscheinlichkeit spürbar,
dass er bestätigt. Die Entscheidung bleibt beim Besitzer.

---

## 8. Was dieses Dokument nicht sagt

- **Es empfiehlt keine Änderung am Score.** Kein Kandidat hier ist auf diesem
  Bestand gemessen. Für jeden gelten Šidák, Jahresprüfung und §7 unverändert.
- **Es hebt die Warnung aus §5 nicht auf.** „Noch eine Signalfamilie" bleibt ein
  schlechter Reflex — was §5 ausschließt, ist die **unausgewählte** Familie.
  §6 ist die Auswahl, um die §5 gebeten hat, mit benannter Vorabbegründung,
  warum ein Kandidat an der Jahresstabilität nicht scheitern muss.
- **Es verspricht keinen Fund.** Die ehrlichste Zusammenfassung dieser Literatur
  für ein Large-Cap-Universum nach 2016 lautet: 7 Basispunkte im Monat, Median,
  vor Kosten. Wer damit rechnet, wird nicht enttäuscht.
- **Es ersetzt die Jahresprüfung nicht.** 6 von 9 Jahren ist p = 0,51, 7 von 9
  ist p = 0,18. Auch ein Kandidat mit Literaturrückhalt scheitert daran, wenn er
  scheitert.

### Die kürzeste Fassung

1. Der neunfache Nullbefund ist sauber gemessen und in dieser Literatur normal.
2. Er hat eine bisher nicht ausgeschlossene Erklärung: **das Universum** (§3) —
   und die adressiert Auftrag C.
3. Acht der zehn geprüften Instrumente gehören einer Familie an, für die diese
   Literatur nie eine Behauptung aufgestellt hat (§4).
4. Der billigste offene Test sind **drei Themen aus Daten, die schon in der
   Datenbank liegen** (§6.1) — ein Arbeitstag, null Rechenzeit.
5. Der stärkste Kandidat ist die **Nettoemission** (§6.3): kursunabhängig,
   Minuten an Abrufen, und die einzige Familie mit berichteter Robustheit über
   Firmengrößen hinweg.
6. Der Holdout-Kandidat PEAD hat eine benannte Gegenhypothese (§7).

---

## 9. Quellen

**Replikation und Mehrfachtests**

- Hou, K., Xue, C., Zhang, L. (2020): *Replicating Anomalies.* Review of
  Financial Studies 33, 2019–2133.
  <https://global-q.org/uploads/1/2/2/6/122679606/houxuezhang2020rfs.pdf>
- Jensen, T. I., Kelly, B., Pedersen, L. H. (2023): *Is There a Replication
  Crisis in Finance?* Journal of Finance 78(5), 2465–2518.
  <https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13249> ·
  Daten und Code: <https://github.com/bkelly-lab/ReplicationCrisis> ·
  <https://jkpfactors.com/>
- Chen, A. Y., Zimmermann, T. (2022): *Open Source Cross-Sectional Asset
  Pricing.* Critical Finance Review. <https://www.openassetpricing.com/> ·
  <https://github.com/OpenSourceAP/CrossSection>
- Harvey, C. R., Liu, Y., Zhu, H. (2016): *…and the Cross-Section of Expected
  Returns.* Review of Financial Studies 29(1), 5–68.
- McLean, R. D., Pontiff, J. (2016): *Does Academic Research Destroy Stock
  Return Predictability?* Journal of Finance 71(1), 5–32.
  <https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365>
- Chen, A. Y., Velikov, M. (2023): *Zeroing in on the Expected Returns of
  Anomalies.* Journal of Financial and Quantitative Analysis.
  <https://www.federalreserve.gov/econres/feds/files/2020039pap.pdf>

**Einzelne Familien**

- Martineau, C. (2022): *Rest in Peace Post-Earnings Announcement Drift.*
  Critical Finance Review.
  <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111607>
- Pontiff, J., Woodgate, A. (2008): *Share Issuance and Cross-Sectional
  Returns.* Journal of Finance 63(2) — mit Daniel/Titman (2006) und der
  internationalen Nachprüfung von McLean/Pontiff/Watanabe (2009),
  <https://www.sciencedirect.com/science/article/abs/pii/S0304405X09001007>
- Novy-Marx, R. (2013): *The Other Side of Value: The Gross Profitability
  Premium.* <https://mysimon.rochester.edu/novy-marx/research/OSoV.pdf>
- Cooper, M., Gulen, H., Schill, M. (2008): *Asset Growth and the Cross-Section
  of Stock Returns.* Journal of Finance 63(4).
- Sloan, R. (1996): *Do Stock Prices Fully Reflect Information in Accruals and
  Cash Flows About Future Earnings?* — bereits umgesetzt in
  `services/accruals.py`.
- de Groot, W., Huij, J., Zhou, W. (2012): *Another Look at Trading Costs and
  Short-Term Reversal Profits.* Journal of Banking & Finance.
  <https://www.efmaefm.org/0efmameetings/efma%20annual%20meetings/2011-Braga/papers/0259.pdf>

**Insider (Grundlage für Auftrag B)**

- Lakonishok, J., Lee, I. (2001): *Are Insider Trades Informative?* Review of
  Financial Studies 14(1) — über eine Million Form-4-Transaktionen 1975–1995;
  7–8 % Abstand über zwölf Monate, **konzentriert in kleineren Firmen**.
- Cohen, L., Malloy, C., Pomorski, L. (2012): *Decoding Inside Information.*
  Journal of Finance 67(3) — die Trennung in **routinemäßige** und
  **opportunistische** Insider. Routinegeschäfte tragen **null**;
  opportunistische **82 bp/Monat**.
  <https://www.nber.org/system/files/working_papers/w16454/w16454.pdf>

> **Für Auftrag B vorzumerken:** Ohne die Routine-/Opportunismus-Trennung misst
> man laut Cohen/Malloy/Pomorski überwiegend Rauschen — über die Hälfte aller
> Insidergeschäfte sind kalendergetrieben und ohne Prognosewert. Die Trennung
> braucht die **Historie je Person**, nicht nur je Unternehmen. Das ist eine
> Anforderung an das Datenmodell von B und muss vor dem Bestandsaufbau
> feststehen, nicht danach.
