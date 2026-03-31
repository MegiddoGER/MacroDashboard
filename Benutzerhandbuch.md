# 📖 MacroDashboard – Das vollständige Benutzerhandbuch

Willkommen beim **MacroDashboard**! Dieses Handbuch ist so geschrieben, dass es jeder leicht verstehen kann. Es dient als Nachschlagewerk, um das volle Potenzial des Dashboards abzurufen – egal ob zur täglichen Portfolioführung oder für tiefgehende Analysen.

---

## 🧭 1. Die Navigation & Seitenleiste (Sidebar)

Auf der linken Seite finden Sie das ständige Kontrollzentrum des Dashboards.

*   **Navigation:** Hier wechseln Sie zwischen den verschiedenen Seiten hin und her.
*   **Was ist die Watchlist?** Hier können Sie über das Eingabefeld (Ticker oder Firmenname) jederzeit neue Aktien zu Ihrer Beobachtungsliste hinzufügen oder alte über das "✕" entfernen.
*   **Signal-Alerts 🔔:** Unter diesem Menüpunkt sehen Sie ausgelöste Alarme (z.B. wenn eine Aktie einen bestimmten Preis erreicht hat). Sie können hier auch neue Alarme anlegen, um sich benachrichtigen zu lassen, wenn Kurse oder Indikatoren (wie der RSI) bestimmte Marken durchbrechen.
*   **Daten Aktualisieren:** Das Dashboard speichert im Hintergrund Daten automatisch für wenige Minuten (als "Cache"), damit alles extrem schnell lädt. Klicken Sie diesen Button ganz unten in der Navigationsleiste, wenn Sie komplett frische Börsendaten erzwingen möchten.

---

## 📊 2. Die einzelnen Seiten im Detail

### 2.1 Startseite (Home)
**Nutzen:** Ihr tägliches morgendliches "Cockpit". Hier sehen Sie auf einen Blick, wie der Markt heute steht.
*   **Was Sie finden:** Den aktuellen Wert Ihres eigenen Portfolios (basierend auf Ihren eingetragenen Trades in der Watchlist), generelle Marktindizes (S&P 500, Gold) und den *Fear & Greed Index* (Gier- und Angst-Barometer).
*   **Wann verwenden:** Jeden Tag beim ersten Öffnen. Es hilft enorm, ein Gefühl dafür zu bekommen, ob der Markt gerade extrem überhitzt (extremer Greed/Gier) oder panisch (extreme Fear/Angst) agiert.

### 2.2 Gesamtwirtschaft (Makro)
**Nutzen:** Der Blick auf das "große Ganze". Das hilft zu verstehen, *warum* die Aktienmärkte gerade tendenziell steigen oder fallen.
*   **Was Sie finden:** Den Wirtschaftskalender mit allen anstehenden wichtigen Terminen in den USA, EU und Deutschland (Zinsentscheide, Arbeitsmarktdaten). Außerdem Live-Charts zu Gold, Öl, der Zinsstrukturkurve (ein extrem wichtiger Frühindikator für drohende Rezessionen) und der Inflationsrate. 
*   **Wann verwenden:** Um sich auf Termine vorzubereiten (hohe rote Markierungen bedeuten, dass an jenem Tag im Vorfeld mit extrem starken Kursausschlägen an den Börsen gerechnet werden muss).

### 2.3 Watchlist
**Nutzen:** Die übersichtliche Matrix-Verwaltung Ihrer beobachteten Aktien und echten Kauf-Positionen.
*   **Was Sie finden:** Eine große Tabelle mit allen Aktien Ihrer Seitenleiste. Sie können hier auf einen Blick ablesen, wie die Aktien aktuell stehen (Vorzeichen, Kurs, RSI-Momentum, Trend-Prognose).
*   **Wann verwenden:** Wenn Sie eine Aktie ins Portfolio aufnehmen wollen, klicken Sie in der Tabelle auf den entsprechenden Reiter und tragen Startkapital, Kaufpreis sowie die Stückzahl ein. Das System verfolgt dann Ihren realen Gewinn und Verlust ab diesem Datum. Unter dem Reiter "Drawdown" sehen Sie zudem visualisiert, wie stark Ihr gesamtes Portfolio im Vergleich zu seinem Spitzen-Hoch im Moment "unter Wasser" ist (klassisches Risikomanagement).

### 2.4 Screener
**Nutzen:** Der vollautomatische Assistent, um aus unzähligen Aktien genau die wenigen Kaufgelegenheiten herauszufiltern, die Ihren Vorgaben entsprechen.
*   **Was Sie finden:** Frei wählbare Filter für Technische Indikatoren und Fundamentales (Beispiel: *"Zeige mir alle Aktien aus dem Bereich Tech, die heute zwar stark gefallen, aber langfristig betrachtet immer noch stabil über ihrem SMA 200 sind."*)
*   **Wann verwenden:** Wenn Sie eine vielversprechende neue, analytisch-gedeckte Investment-Idee suchen, ohne alle Papiere händisch abzusuchen. Finden Sie einen Treffer, merken Sie sich das Kürzel, oder fügen die Aktie direkt der Watchlist hinzu.

### 2.5 Analyse
**Nutzen:** Das Herz und die kognitive Intelligenz des Dashboards. Hier durchleuchten Sie eine *einzelne* Aktie komplett wie ein Röntgengerät.
*   **Was Sie finden:** Oben rechts die gewünschte Aktie eingeben. Sie erhalten tiefstes Detailwissen:
    *   **Basis-Übersicht & Finanzdaten:** Wichtige Kernkennzahlen (KGV, Jahres-Umsätze, echter Unternehmensgewinn, Bilanzen (SEC-Echtzeitdaten)).
    *   **Charts:** Von einfachen Kerzencharts über Momentum-Indikatoren (RSI, MACD) bis hin zu *Bollinger Bändern*.
    *   **Quant-Analyse:** Ein revolutionäres Tool, bei dem das System **vollautomatisch** ein auf den *Sektor* maßgeschneidertes Prüfmodell ausführt (z.B. zeigt das System für Banken "Excess Returns" an, nutzt für Cloud-Software aber die "Rule of 40"). Damit erfahren Sie sofort, ob das Unternehmen in seiner Branche teuer oder billig ist.
    *   **SMC & Liquidity Sweeps:** Fortgeschrittene Diagramme für Profis. Sie decken Zonen auf, in denen Großbanken vermutlich Stopp-Orders auslösen, um günstige Einstiege zu erzeugen (*Fair Value Gaps, Liquiditätszonen, Order Flow-Peaks*).
*   **Wann verwenden:** Vor **absolut jedem** Kaufentscheid. Lesen Sie hier das Markt-Momentum exakt ab und prüfen Sie (unter dem Reiter "Swing Trading"), wo Sie einen validen und gut platzierten Stop-Loss (Sicherungslinie) setzten müssten, um optimal einzusteigen.

### 2.6 Backtesting
**Nutzen:** Die Zeitmaschine. Hilft dabei, eine Theorie erst zu beweisen, bevor Sie Ihr Erspartes darauf setzen.
*   **Was Sie finden:** Eine Simulations-Engine, die die Historie von Parametern berechnet. Sie können eine Aktie (oder alle der Watchlist) auswählen, Strategien definieren (z.B. *"Immer kaufen, wenn RSI unter 30 fällt"*), und klicken "Test Starten". 
*   **Wann verwenden:** Wenn Sie unentschlossen sind, ob ein bestimmtes Handelssignal langfristig wirklich funktioniert. Das System zeigt schwarz auf weiß, welchen kumulierten Verlust oder Gewinn man beispielsweise über ein ganzes Jahr gemacht hätte.

### 2.7 Trade-Journal (Tagebuch)
**Nutzen:** Die saubere Buchführung Ihrer Gedanken und Trades, um kontinuierlich aus Fehlern oder Siegen zu lernen.
*   **Was Sie finden:** Zwei große Reiter ("Offen" und "Historie"). Offen zeigt alle aktuellen Anlagen aus Ihrer Watchlist und deren laufenden Profilbetrag (Live-Wert). Wollen Sie nach Wochen einen Verkauf durchführen, schließen Sie den Trade hier. Anschließend schreiben Sie dort zwingend einen Kommentar (z.B. *"Panikverkauf wegen Leitzinserhöhung"*, oder *"Wie im Stop-Loss-Plan vorher festgelegt"*).
*   **Wann verwenden:** Bei jeder realen Positions-Entscheidung. Ohne ehrliches Bewerten der eigenen Züge (Lessons Learned in der Historie) wird Trading langfristig sehr schwierig.

### 2.8 Sektoren
**Nutzen:** Die Marktkapital-Landkarte. Hier sieht man, wo momentan das große Geld konzentriert abfließt oder reinwandert.
*   **Was Sie finden:** Eine Farb-Heatmap des S&P 500 und STOXX Europe 600. Grün bedeutet dieser gesamte Sektor (z.B. "Technologie") boomt extrem, rot signalisiert das Gegenteil.
*   **Wann verwenden:** Für das Screening der generellen Trendlage. Institutionelle Profis versuchen meistens nur die *stärkste* Aktie in einem momentan ohnehin enorm *starken* Gesamtsektor zu finden, und meiden jegliche Einzelunternehmen, die in einem komplett stürzenden Sektor festsitzen (auch wenn sie billig erscheinen).

### 2.9 Analyse-Lexikon
**Nutzen:** Das Wikipedia für komplexe Börsenbegriffe, im Zweifel genau dann da, wenn man es braucht.
*   **Was Sie finden:** Leicht lesbare, aufgeschlüsselte Erklärungen zu allen oft erwähnten Fachbegriffen (z.B. Was ist ein MACD? Wie benutzt man Fibonacci? Was bedeuten DCF-Modelle oder Drawdowns?).
*   **Wann verwenden:** Wenn Sie auf der Analyse-Seite auf einen Metriken-Wert stoßen, den Sie noch nicht vollends verinnerlicht haben und nachschlagen möchten, ob der vorliegende Wert eher "gut" oder "gefährlich" einzuordnen ist.

### 2.10 Aktien-Verzeichnis
**Nutzen:** Die riesige Datenbank aller Firmen am Markt, um unkompliziert Ticker-Symbole nachzuschauen.
*   **Was Sie finden:** Weit über 16.000 listierte Aktien verschiedener großer US/EU-Börsen, kategorisiert und alphabetisch/nach Namen durchsuchbar. 
*   **Wann verwenden:** Sie haben von der Firma "Alphabet" oder "Palantir" gelesen und suchen nun zur raschen Einordnung in das Dashboard das korrekte offizielle Ticker-Symbol (GOOG, PLTR).

---

## 🎯 3. Best Practice: Ein optimaler, täglicher Arbeitsablauf (Workflow)

Um nicht erschlagen zu werden, empfiehlt sich ein geregelter Plan für die Morgen-Routine, oft bevor die US-Öffnung überhaupt stattfindet:

1. **Die Peilung einholen (5 Min):** Beginnen Sie auf der **Startseite** (Wie stark ist die Gier aktuell?), und sehen Sie unter **Gesamtwirtschaft** nach wichtigen News / Zins-Terminen desselben Tages. 
2. **Kandidaten aufspüren (5 Min):** Lassen Sie den technischen **Screener** eine Vorauswahl treffen, oder prüfen Sie unter **Sektoren**, welche Branchen abheben oder extrem zurückgesetzt wurden.
3. **Fundierte Untersuchung (10 Min):** Werfen Sie gefilterte Favoriten tief in die **Analyse**. Verifizieren Sie fundamentale Kaufkraft und das Risiko von Value Traps über den Reiter *Quant-Analyse*, während Sie das Timing des Trends an der Kreuzung des MACD auf den Graphen festmachen.
4. **Warteschleife vs. Ausführung:** 
   * *Variante A (Abwarten):* Nehmen Sie die Aktie links in die **Watchlist** auf und setzen im Menü einen "🔔 Signal-Alert" ein, der Sie z.B. bei der nächsten Korrektur weckt (Buy in The Dip).
   * *Variante B (Einstieg):* Tragen Sie den echten Start-"Trade" nach erfolgreichem Broker-Kauf ebenfalls in die Watchlist ein.
5. **Konklusive Auswertung:** Halten Sie Ihre Lektion und Erkenntnis nach jeglichem Exit später lückenlos im Modul **Trade-Journal** fest.
