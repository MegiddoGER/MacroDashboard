import streamlit as st

def page_lexicon():
    st.markdown("## 📖 Analyse-Lexikon")
    st.caption("Das essenzielle Nachschlagewerk für technische, strategische und fundamentale Bewertungsmodelle.")
    st.markdown("---")

    tab_guide, tab_fund, tab_quant, tab_tech, tab_strat, tab_risk, tab_sent, tab_arch = st.tabs([
        "📖 Benutzerhandbuch",
        "📊 Fundamentale Analyse",
        "🏦 Quant-Modelle (Sektoren)", 
        "📈 Technische Indikatoren", 
        "🎯 Strategische Taktiken",
        "🛡️ Risiko & Backtesting",
        "💬 Sentiment & Flow",
        "🧠 System-Architektur"
    ])

    # =========================================================================
    # 0. Benutzerhandbuch (Handbuch als Lesebuch)
    # =========================================================================
    with tab_guide:
        import os
        manual_path = os.path.join(os.path.dirname(__file__), "..", "..", "Benutzerhandbuch.md")
        if os.path.exists(manual_path):
            with open(manual_path, "r", encoding="utf-8") as f:
                # Da die md Datei schon einen # Titel hat, rendern wir sie direkt.
                st.markdown(f.read())
        else:
            st.info("Das Benutzerhandbuch (Benutzerhandbuch.md) wurde im Hauptverzeichnis nicht gefunden.")

    # =========================================================================
    # 1. Fundamentale Analyse (NEU)
    # =========================================================================
    with tab_fund:
        st.markdown("### Fundamentale Analyse — Das Fundament jeder Investitionsentscheidung")
        st.markdown(
            "Während die technische Analyse zeigt, **wann** man kaufen oder verkaufen sollte, "
            "beantwortet die fundamentale Analyse die weitaus wichtigere Frage: **Was ist ein Unternehmen wirklich wert?** "
            "Sie analysiert die wirtschaftliche Substanz hinter dem Kurs — Gewinne, Schulden, Cashflow und Wachstum."
        )
        st.markdown("---")

        with st.expander("💰 Discounted Cash Flow (DCF) — Der Innere Wert"):
            st.markdown("""
            **Das Herzstück der fundamentalen Bewertung.** Das DCF-Modell berechnet, was ein Unternehmen *tatsächlich* wert ist — 
            unabhängig davon, was der Markt gerade dafür bezahlt.
            
            **Grundprinzip:** Ein Euro, den du erst in einem Jahr erhältst, ist heute weniger wert als ein Euro in deiner Hand 
            (wegen Inflation, Risiko und Opportunitätskosten). Das DCF-Modell:
            
            1. **Schätzt die zukünftigen Free Cashflows** (was das Unternehmen verdient, abzüglich aller Investitionen) für 5 Jahre.
            2. **Diskontiert sie auf den heutigen Wert** mit einem Abzinsungsfaktor (WACC).
            3. **Addiert einen Terminal Value** (ewiger Restwert nach Jahr 5).
            4. **Zieht die Schulden ab und addiert Cash** → Ergibt den **Fair Value pro Aktie.**
            
            **Schlüsselbegriffe:**
            - **Free Cashflow (FCF):** Operativer Cashflow minus Investitionsausgaben. Das *echte* Geld, das ein Unternehmen generiert. Viel ehrlicher als der „Gewinn", der durch Buchhaltungstricks manipulierbar ist.
            - **WACC (Weighted Average Cost of Capital):** Die durchschnittlichen Kapitalkosten — ein Mischsatz aus Eigen- und Fremdkapitalkosten. Je riskanter das Unternehmen (höheres Beta), desto höher der WACC, desto niedriger der Fair Value.
            - **Terminal Value:** Der Wert aller Cashflows nach dem Prognosezeitraum. Basiert auf einer konservativen ewigen Wachstumsannahme (typisch 2-3%).
            - **Margin of Safety:** Ist der Fair Value *deutlich* (> 20%) über dem aktuellen Kurs, existiert ein Sicherheitspuffer — die Aktie ist günstiger als ihr innerer Wert.
            
            **⚠️ Limitierung:** Das Ergebnis ist nur so gut wie die Annahmen (Wachstumsrate, WACC). Kleine Änderungen können den Fair Value um ±30% verschieben. Immer als **Indikation**, nie als absolute Wahrheit betrachten.
            """)

        with st.expander("🏦 Bilanzqualität & Verschuldung — Das Sicherheitsnetz"):
            st.markdown("""
            Die Bilanz zeigt, ob ein Unternehmen finanziell stabil genug ist, um auch schwierige Zeiten zu überstehen. 
            **Ein Unternehmen mit tollem Umsatzwachstum, aber zu viel Schulden, kann trotzdem bankrott gehen.**
            
            **Schlüsselkennzahlen:**
            
            | Kennzahl | Formel | Gut | Kritisch | Bedeutung |
            |---|---|---|---|---|
            | **Debt/Equity** | Gesamtschulden / Eigenkapital | < 50% | > 150% | Wie stark ist das Unternehmen fremdfinanziert? |
            | **Current Ratio** | Kurzfr. Vermögen / Kurzfr. Verbindlichkeiten | > 1.5 | < 1.0 | Kann es seine Rechnungen in den nächsten 12 Monaten bezahlen? |
            | **Net Debt/EBITDA** | (Schulden − Cash) / EBITDA | < 2x | > 4x | Wie viele Jahre braucht das Unternehmen, um seine Nettoschulden aus dem operativen Geschäft abzubauen? |
            
            **Ampelsystem:**
            - 🟢 **Solide:** Niedrige Verschuldung, hohe Liquidität. Das Unternehmen kann Rezessionen absorbieren.
            - 🟡 **Akzeptabel:** Moderate Verschuldung. Bei Zinserhöhungen könnte Druck entstehen.
            - 🔴 **Kritisch:** Hohe Verschuldung bei geringer Liquidität. Refinanzierungsrisiko!
            
            **Branchen-Kontext:** Einige Branchen (z.B. Banken, Utilities) haben *strukturell* höhere Verschuldungsquoten — das ist normal und kein Warnsignal per se.
            """)

        with st.expander("📈 Margen & Cashflow-Trends — Die Qualität des Wachstums"):
            st.markdown("""
            Nicht jedes Umsatzwachstum ist gleich viel wert. Entscheidend ist, **wie profitabel** ein Unternehmen wächst.
            
            **Die drei Margen (von oben nach unten der Gewinn- und Verlustrechnung):**
            
            - **Bruttomarge** = (Umsatz − Herstellungskosten) / Umsatz
              → Zeigt die Preissetzungsmacht. Eine Bruttomarge von 70% (wie bei Software) bedeutet: Von jedem Euro Umsatz bleiben 70 Cent *vor* allen anderen Kosten.
            
            - **EBITDA-Marge** = EBITDA / Umsatz
              → Zeigt die operative Effizienz. Hier sind Gehälter, Marketing etc. bereits abgezogen, aber noch keine Abschreibungen oder Zinsen.
            
            - **Nettomarge** = Nettogewinn / Umsatz
              → Die „Wahrheit". Was bleibt am Ende *wirklich* übrig? Enthält alles — Steuern, Zinsen, Sondereffekte.
            
            **Free Cashflow (FCF):** Der *ehrlichste* Indikator für die Gesundheit eines Unternehmens. 
            - Ein Unternehmen, das Gewinne meldet, aber keinen positiven FCF generiert, ist ein **Red Flag** — die Gewinne sind möglicherweise buchhalterisch aufgebläht.
            - Steigende Margen über mehrere Jahre = Skalierungseffekte = gutes Zeichen.
            - Sinkende Margen bei steigendem Umsatz = das Wachstum wird „erkauft" = Warnsignal.
            """)

        with st.expander("🏭 Peer-Vergleich — Relative Bewertung"):
            st.markdown("""
            Ein KGV von 25 ist bei einem Tech-Unternehmen mit 30% Wachstum günstig — bei einem Versorger mit 3% Wachstum absurd teuer. 
            Deswegen muss man immer **innerhalb der gleichen Branche** vergleichen.
            
            **Kennzahlen im Peer-Vergleich:**
            
            - **KGV (Kurs-Gewinn-Verhältnis):** Wie viele Jahre Gewinn braucht man, um den Kaufpreis zu amortisieren? Niedrig = günstig (aber Vorsicht vor „Value Traps" — es gibt oft einen Grund).
            - **EV/EBITDA:** Enterprise Value (Marktkapitalisierung + Schulden − Cash) / EBITDA. Besser als das KGV, weil es die Kapitalstruktur einbezieht.
            - **Profitmarge:** Wie effizient arbeitet das Unternehmen im Vergleich?
            - **Umsatzwachstum:** Wächst es schneller oder langsamer als die Konkurrenz?
            
            **Interpretation:** Ist das analysierte Unternehmen bei *besseren* fundamentalen Kennzahlen *günstiger* bewertet als die Peers → potenzielle Unterbewertung.
            """)

        with st.expander("💎 Dividendenanalyse — Passive Einkünfte bewerten"):
            st.markdown("""
            Dividenden sind der Anteil des Gewinns, den das Unternehmen direkt an die Aktionäre ausschüttet.
            
            **Wichtige Kennzahlen:**
            
            - **Dividendenrendite:** Jährliche Dividende / aktueller Aktienkurs. Eine Rendite von 3% bedeutet: Für je 1.000 € Investment erhältst du 30 € pro Jahr.
            - **Payout Ratio:** Anteil des Gewinns, der als Dividende ausgezahlt wird.
              - < 60%: Nachhaltig. Das Unternehmen behält genug Gewinn für Reinvestitionen.
              - 60-80%: Moderat. Wenig Spielraum für Dividendenerhöhungen.
              - > 80%: **Gefährlich.** Bei einem Gewinneinbruch muss die Dividende wahrscheinlich gekürzt werden.
            - **Dividend Growth Rate (CAGR):** Die durchschnittliche jährliche Wachstumsrate der Dividende. 7-10% pro Jahr gilt als exzellent.
            - **Streak (Erhöhungsserie):**
              - ≥ 25 Jahre: **Dividendenaristokrat** (S&P 500 Kriterium)
              - ≥ 50 Jahre: **Dividendenkönig** (extrem selten)
            
            **Falle:** Eine *sehr hohe* Dividendenrendite (>8%) ist oft ein **Warnsignal** — der Kurs ist so weit gefallen, dass die Rendite optisch hoch aussieht, die Dividende wird aber wahrscheinlich bald gekürzt.
            """)

        with st.expander("👔 Insider-Transaktionen — Was die Chefs wirklich denken"):
            st.markdown("""
            Vorstände und Aufsichtsräte wissen mehr über ihr eigenes Unternehmen als jeder Analyst. Ihre Käufe und Verkäufe 
            eigener Aktien sind daher eines der stärksten Signale am Markt.
            
            **Datenquelle:** In den USA müssen Insider ihre Transaktionen innerhalb von 2 Werktagen der SEC (Börsenaufsicht) melden 
            (Form 4). Diese Daten sind öffentlich einsehbar. Für europäische Aktien gelten ähnliche Regeln (MAR/PDMR), aber die Datenlage ist weniger zentral.
            
            **Interpretation:**
            - **Insider-Käufe:** Sehr starkes bullisches Signal! Ein CEO, der für Millionen eigene Aktien kauft, setzt sein *persönliches Geld* auf die Zukunft seines Unternehmens.
            - **Insider-Verkäufe:** *Weniger eindeutig*. Insider verkaufen aus vielen Gründen — Steuerplanung, Diversifikation, Hauskauf. Massives Verkaufen durch *mehrere* Insider gleichzeitig ist jedoch ein Warnsignal.
            - **Net Sentiment:** Kaufen insgesamt mehr Insider als verkaufen → Bullisch. Umgekehrt → Vorsicht.
            
            **Cluster-Käufe** (mehrere Insider kaufen gleichzeitig) sind das stärkste Signal.
            """)

        with st.expander("🏛️ Institutionelle Investoren — Die Großen im Spiel"):
            st.markdown("""
            Institutionelle Investoren wie BlackRock, Vanguard, State Street oder Fidelity verwalten Billionen. 
            Ihre Positionen zeigen, welche Unternehmen von professionellen Portfolio-Managern als langfristig attraktiv eingestuft werden.
            
            **Was die Daten zeigen:**
            - **Top-Halter:** Die größten institutionellen Aktionäre und deren prozentualer Anteil.
            - **Hoher institutioneller Anteil (>70%):** Zeigt breites professionelles Vertrauen — aber auch: weniger „Free Float" für Privatanleger.
            - **Anstieg der Positionen:** Wenn große Institutionen ihre Positionen aufstocken, ist das ein subtiles Akkumulationssignal.
            
            **Kontextfaktor:** Passive Indexfonds (ETFs) kaufen automatisch basierend auf dem Index — deren Halten ist kein aktives „Kaufsignal". 
            Aufschlussreicher sind *aktiv verwaltete Fonds* und *Hedgefonds*.
            """)

        with st.expander("🎯 Analysten-Konsens — Die Weisheit der Wall Street"):
            st.markdown("""
            Sell-Side-Analysten großer Banken (Goldman Sachs, JP Morgan, Morgan Stanley etc.) veröffentlichen 
            regelmäßig **Kursziele**, **Schätzungen** und **Empfehlungen**.
            
            **Elemente:**
            - **Konsens-Kursziel:** Der Durchschnitt aller Analysten-Kursziele. Vergleich mit dem aktuellen Kurs ergibt das potenzielle Upside/Downside.
            - **Spanne (Low–High):** Die Range zwischen dem pessimistischsten und optimistischsten Analysten. Eine große Spanne = hohe Unsicherheit.
            - **Empfehlung:** Strong Buy / Buy / Hold / Sell / Strong Sell. Der Konsensus-Score geht von 1 (Strong Buy) bis 5 (Sell).
            
            **⚠️ Wichtige Einschränkungen:**
            - Analysten haben **eigene Interessenkonflikte** (ihre Banken wollen Geschäfte mit den analysierten Unternehmen machen). „Sell"-Empfehlungen sind daher extrem selten.
            - **Kursziele hinken dem Kurs hinterher** — sie werden oft erst *nach* einem Anstieg angehoben (pro-zyklisch).
            - Am aussagekräftigsten: Plötzliche **Downgrades** durch mehrere Analysten gleichzeitig.
            
            **Faustregeln:**
            - Konsensus-Score < 2.0 = starker Kaufkonsens
            - Konsensus-Score 2.0-3.0 = gemischt
            - Konsensus-Score > 3.0 = Halte- bis Verkaufszone
            """)

    # =========================================================================
    # 2. Quantitative Bewertungsmodelle (Nach Sektoren)
    # =========================================================================
    with tab_quant:
        st.markdown("### Sektorspezifische Bewertungsmodelle")
        st.markdown(
            "Universelle Bewertungsmetriken wie das einfache Kurs-Gewinn-Verhältnis (KGV) oder klassische DCF-Modelle "
            "werden den komplexen Realitäten globaler Kapitalmärkte nicht mehr gerecht. Jede Industrie hat eine eigene "
            "strukturelle DNA. Dieses Dashboard wendet vollautomatisch hochspezialisierte quantitave Modelle an, "
            "basierend auf der identifizierten Branche der jeweiligen Aktie."
        )
        
        st.markdown("---")
        
        with st.expander("🏦 Finanzen & Versicherungen (Excess Returns)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *Excess Returns Modell (Allstate-Methodik)*
                
                Das traditionelle KGV scheitert hier an der massiven regulatorischen Kapitalbindung und dem Zinsumfeld.
                Das Excess Returns Modell berechnet den wahren Unternehmenswert, indem es die **Eigenkapitalkosten (Cost of Equity)** 
                von der geschätzten Eigenkapitalrendite (**ROE**) subtrahiert. Ein Finanzunternehmen generiert erst dann **Rendite (Alpha)**, 
                wenn es einen positiven „Spread" (Excess Return) über den eigenen Kapitalkosten erwirtschaftet.
                
                *Filtert kurzfristiges Rauschen hinaus und offenbart intrinsische Bewertungsabschläge.*
                """
            )
            
        with st.expander("💻 Technologie & SaaS (Rule of 40)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *Rule of 40 & LTV/CAC-Framework*
                
                Software-as-a-Service (SaaS) Unternehmen werden an der **Unit Economics** (Einheitsökonomie) gemessen.
                - **Rule of 40:** Die Summe aus Umsatzwachstumsrate (%) und Cashflow-Marge (%) muss nachhaltig über 40 liegen. 
                - **LTV / CAC:** Das Verhältnis von Customer Lifetime Value zu Customer Acquisition Cost muss **> 3.0** betragen.
                
                *Wertvernichtendes „erkauftes" Wachstum durch massive Marketingkosten wird hier sofort entlarvt.*
                """
            )
            
        with st.expander("🔌 Halbleiter & Hardware (Zyklik-Proxy)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *Vorlaufende Zyklik & Book-to-Bill Ratio*
                
                Halbleiterhersteller unterliegen krassen Boom-and-Bust Zyklen. Traditionelle KGVs sind trügerisch ("Value Traps"):
                Am zyklischen Hochpunkt, wenn die Gewinne maximal sind, ist das KGV niedrig – ein falsches Kaufsignal!
                - Unser Proxy kombiniert **EV/EBITDA** und **Price-to-Book (P/B)**, um vor nahende Abschwüngen zu warnen.
                - Am Tiefpunkt des Zyklus dient der Buchwert (P/B) als rettende **Bewertungsuntergrenze (Floor)**.
                """
            )
            
        with st.expander("🧬 Biotechnologie & Pharma (rNPV Proxy)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *Risk-Adjusted Net Present Value (rNPV)*
                
                Für Biotechfirmen (oft klinische Studien ohne Einnahmen) ist klassisches DCF fatal. 
                Die rNPV-Methode entkoppelt das finanzielle Marktrisiko vom technischen **Versagensrisiko klinischer Studien (PTRS)**.
                Forschungskosten generieren nur dann Wert, wenn Wahrscheinlichkeiten und asymmetrisches Endmarktpotenzial stimmen.
                """
            )
            
        with st.expander("🛢️ Energie / Öl & Gas (EV / DACF)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *Enterprise Value / Debt-Adjusted Cash Flow (DACF)*
                
                Das beliebte EV/EBITDA ist hier fehlerhaft, da es massive Investitionsausgaben (Explorations-CapEx) ignoriert. 
                **DACF** bereinigt den operativen Cashflow um finanzielle Aufwendungen und Steuern. Dies egalisiert extrem 
                unterschiedliche Kapitalstrukturen von Ölkonzernen und erlaubt einen hochpräzisen, verzerrungsfreien Peer-Gruppen-Vergleich.
                """
            )

        with st.expander("📡 Telekommunikation (ARPU & Churn)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *ARPU-adjustiertes EV/EBITDA*
                
                Reines Abonnentenwachstum ist ein trügerischer Indikator, wenn es durch teure Rabatte erkauft wird.
                Wichtig ist der **ARPU** (Average Revenue Per User) in Kombination mit einer extrem niedrigen **Churn-Rate** (Kundenabwanderung).
                Zusätzlich rechtfertigt physische Netzqualität (z.B. FTTH-Glasfaser = tiefer ökonomischer Burggraben) massive Aufschläge beim EV/EBITDA.
                """
            )
            
        with st.expander("🚢 Logistik & Transport (EV / EBITDAR)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *EV / EBITDAR (Rent/Leasing-Adjustierung)*
                
                Das klassische EBITDA scheitert massiv: Einige Firmen leasen LKW/Flugzeuge (hohe Mietkosten senken EBITDA), 
                andere kaufen sie (Abschreibungen belasten EBITDA nicht). Die Nutzung von **EBITDAR** integriert 
                die Miet- & Leasingkosten (Rent) und macht Airlines oder Speditionen erstmals unabhängig ihrer Finanzierungsstrategie messbar.
                """
            )

        with st.expander("🇩🇪 Deutsche Aktien (HGB Hidden Champions)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *Asset-Based (HGB) vs IFRS / ROA-Prämie*
                
                Das deutsche Handelsrecht (HGB) zwingt zum Vorsichtsprinzip. Die Folge: immense **stille Reserven**.
                Kapitalmarktforschung zeigt: Konservative **HGB-Buchwerte** weisen am Markt eine fast 1:1 Erklärungskraft für die Bepreisung auf (massiv besser als hoch volatile IFRS Fair-Values). 
                Ein „Hidden Champion" zeichnet sich durch im globalen Vergleich systematisch höhere Marktmacht, messbar durch einen konsequenten Aufschlag bei der **Return on Assets (ROA)** Prämie aus (im historischen Schnitt +1,7% über dem Durchschnitt).
                """
            )

        with st.expander("🇨🇳 Chinesische A-Aktien (CSVS)"):
            st.markdown(
                """
                **🔥 Kern-Matrix:** *Chinese-Style Valuation System (CSVS)*
                
                Ein westlicher Investor, der chinesische Firmen (SOEs - staatseigene Betriebe) nach US-DCF Modellen bewertet, scheitert.
                - Kapital wird in China in Sektoren gelenkt, die den Fünfjahresplänen dienen.
                - **Primary Indicator / Kaufsignal:** Ein extremer Abschlag beim **Price-to-Book (P/B)** (Infrastruktur der Staatsbetriebe) kombiniert mit einer staatlich regulierten Erhöhung der **Dividendenrendite**.
                CSVS generiert institutionelle "Policy-Supported Value Stocks".
                """
            )


    # =========================================================================
    # 3. Technische Indikatoren
    # =========================================================================
    with tab_tech:
        st.markdown("### Klassische Chart-Indikatoren")
        st.markdown("Fundamentaldaten zeigen, **welche** Aktie attraktiv ist. Die Technische Analyse hilft bei der Beantwortung der Frage, **wann** man ein- oder aussteigen sollte.")
        st.markdown("---")

        with st.expander("Relative Strength Index (RSI)"):
            st.markdown("""
            Ein Momentum-Oszillator, der die Geschwindigkeit und Veränderung von Kursbewegungen misst. Die Skala reicht von 0 bis 100.
            
            - **< 30 (Grün):** Der Markt gilt als überverkauft (Oversold). Panik herrscht. Häufig nahe an kurzfristigen Tälern.
            - **> 70 (Rot):** Der Markt gilt als überkauft (Overbought). Euphorie! Die Gefahr eines Pullbacks (Korrektur) steigt stark an.
            - **Interpretation:** Nur weil der RSI auf >70 springt, muss der Kurs nicht sofort fallen – in starken fundamentalen Bullenmärkten kann er sehr lange dort verharren.
            
            **Divergenzen:** Wenn der Kurs neue Hochs macht, aber der RSI *nicht* mitzieht (tiefere RSI-Hochs), nennt man das eine **Bearish Divergence** — ein frühes Warnsignal für eine bevorstehende Trendumkehr.
            """)

        with st.expander("Simple Moving Average (SMA)"):
            st.markdown("""
            Gleitende Durchschnitte. Ein SMA 200 berechnet exakt den Durchschnittspreis der letzten 200 Handelstage.
            
            - **SMA 20:** Schneller Trend; für kurzes Swing-Trading.
            - **SMA 50:** Mittelfristiger Trend. Einer der wichtigsten Indikatoren in der Wallstreet. Ein Durchbruch nach unten ist ein starkes Warnsignal.
            - **SMA 200:** Langfristiger Trend. Befindet sich der Kurs oberhalb des SMA 200, herrscht prinzipiell ein intakter Bullenmarkt. Fällt er drunter: Bärenmarkt.
            - **Golden Cross / Death Cross:** Kreuzt der SMA 50 den SMA 200 nach *oben*, gilt das als äußerst massives, langfristiges Kaufsignal (Golden Cross). Kreuzt er nach *unten*, droht Schweres (Death Cross).
            """)

        with st.expander("MACD (Moving Average Convergence Divergence)"):
            st.markdown("""
            Dieser Indikator zeigt an, wie sich zwei kurzfristigere EMAs in Relation zueinander verhalten, um frühe Trendwechsel erkennen zu können.
            
            - **MACD Line (Blau) kreuzt Signal Line (Orange) nach oben:** Bullisches kurzfristiges Kaufsignal (Momentum dreht aufwärts).
            - **Nach unten:** Bärish (Momentum schwächt sich ab).
            - **Histogram (Balken):** Zeigt den absoluten Abstand (Spread) zwischen den beiden Linien. Je höher/tiefer die Balken extrem ausschlagen, desto überdehnter ist der aktuelle Schwung.
            
            **Null-Linie:** Kreuzt die MACD-Linie die Nulllinie nach oben, bestätigt das einen mittelfristigen Trendwechsel von bearish zu bullish (und umgekehrt).
            """)

        with st.expander("Bollinger Bänder"):
            st.markdown("""
            Bestehen aus einem zentralen SMA (meist 20), flankiert von zwei Standardabweichungs-Bändern (Volatilitäts-Kanälen).
            
            - **Enge Bänder (Squeeze):** Ein Squeeze deutet darauf hin, dass die Volatilität drastisch eingeschlafen ist. Sehr oft folgt aus so einem „Flaschenhals" binnen kurz eine brutale und explosive Kursbewegung (in eine beliebige Richtung).
            - **Anstoßen ans Band:** Stößt der Kurs oben an, ist er statistisch derzeit maximal überdehnt (heiß). Stößt er unten an, ist er kurzfristig komplett ausverkauft.
            
            **Bandbreite als Volatilitätsmaß:** Je weiter die Bänder auseinander, desto höher die aktuelle Volatilität. Nach Phasen extremer Bandbreite folgt oft eine Beruhigung (Mean Reversion der Volatilität).
            """)

        with st.expander("Stochastic Oscillator"):
            st.markdown("""
            Ähnlich dem RSI, fokussiert sich aber auf den Schlusskurs in Relation zur Handelsspanne der letzten Tage.
            
            - Eine Aktie schließt in Aufwärtstrends tendenziell nahe ihrem Tageshoch. Bricht diese Routine, warnt der Stochastic früh. 
            - Kreuzt die `%K-Linie` die `%D-Linie` oberhalb des 80er-Niveaus nach unten, wird eine kurzfristige Umkehr eingeleitet.
            
            **Stärke:** Reagiert *schneller* als der RSI und liefert daher frühzeitigere Signale — ist aber auch anfälliger für Fehlsignale in trendstarken Märkten.
            """)

        with st.expander("Average True Range (ATR) & Volatilität"):
            st.markdown("""
            Der ATR misst im Gegensatz zu fast allen anderen Indikatoren keine Richtung, sondern ausschließlich die absolute Hitze / Bewegung des Kurses in Echtgeld (Euro/USD).
            
            Ein ATR von "4,50" besagt: Die Aktie ist heute im Schnitt 4,50 € von Tief zu Hoch geschwankt. 
            **Strategischer Einsatz:** Trader setzen ihren Stop-Loss exakt auf z.B. Einstiegskurs - (1.5 × ATR). So kann das normale "Markt-Rauschen" einen nicht ausstoppen, sondern erst wenn eine unnatürliche starke Schwankung auftritt.
            
            **Positionsgrößen-Management:** Je höher der ATR, desto kleiner sollte die Position sein (gleiche Euro-Risiko-Steuerung bei unterschiedlicher Volatilität).
            """)

        with st.expander("ADX (Average Directional Index) — Trendstärke"):
            st.markdown("""
            **Der ADX misst nicht die *Richtung*, sondern die *Stärke* eines Trends.**
            
            | ADX-Wert | Bedeutung |
            |---|---|
            | < 20 | **Kein Trend** — der Markt bewegt sich seitwärts. Trendfolge-Strategien verlieren Geld. |
            | 20–25 | Trend bildet sich möglicherweise heraus |
            | 25–50 | **Starker Trend** — ideal für Trendfolge-Trades |
            | > 50 | **Extrem starker Trend** — sehr selten, aber hochprofitabel wenn man aufspringt |
            
            **Wichtig:** Der ADX sagt nichts über die Richtung! ADX 40 kann sowohl in einem Aufwärts- als auch Abwärtstrend auftreten. Die Richtung wird durch andere Indikatoren (SMA, MACD) bestimmt.
            """)


    # =========================================================================
    # 4. Strategische Entscheidungen (Fortgeschrittene Tools)
    # =========================================================================
    with tab_strat:
        st.markdown("### Fortgeschrittene Analyse-Instrumente")
        st.markdown("Werkzeuge, die primär von Day-Tradern und algorithmischen Händlern an der Wall Street genutzt und für das Macro Dashboard adaptiert wurden.")
        st.markdown("---")

        with st.expander("🔄 Liquidity Sweeps (Stop-Hunting)"):
            st.markdown("""
            Oft wundern sich Anleger, warum eine extrem wichtige Unterstützungs-Linie bricht, alle verkaufen und die Aktie 5 Minuten später wie eine Rakete wieder nach oben kehrt. 
            Dieses Phänomen wird "Liquidity Sweep" oder "Turtle Soup" genannt.
            
            - **Turtle Soup Bullish:** Institutionelle Akteure drücken den Preis bewusst unter ein tagelanges Tief (da dort alle Retail-Trader ihre automatisierten Stop-Loss-Orders platziert haben). Die Stop-Orders feuern und werfen Millionen Aktien auf den Markt. Die Groß-Investoren kaufen diese billige Liquidität komplett auf – und jagen den Kurs nach oben.
            - *Das Dashboard markiert solche Swing-Hochstapeleien grafisch.*
            
            **Erkennung im Dashboard:** Grüne Markierungen = bullische Sweeps (Akkumulation nach unten). Rote Markierungen = bearische Sweeps (Distribution nach oben).
            """)

        with st.expander("📊 Order Flow Profiling & VWAP"):
            st.markdown("""
            - **VWAP (Volume-Weighted Average Price):** Einer der einzigen Metriken, auf die auch Hedge-Fonds-Computer extrem achten. Ein Preis, der exakt jeden gehandelten Dollar berücksichtigt. Driftet der Kurs massiv über den VWAP, verkaufen Algorithmen oft gegen den Kurs (Mean Reversion).
            - **OBV (On-Balance Volume):** Kumuliert das Handelsvolumen: An Tagen mit steigendem Kurs wird das Volumen addiert, an Tagen mit fallendem Kurs subtrahiert. Steigendes OBV bei steigendem Kurs = Akkumulation. Steigender Kurs bei fallendem OBV = **gefährliche Divergenz** (wenig Überzeugung hinter der Rally).
            - **Volume-Profil (Seitwärts-Histogramm):** Klassische Charts zeigen Volumen am "X"-Datum. Das Profil zeigt das Volumen nach *Preis*. Wo (bei wieviel Euro) wurde das meiste Geld im letzten Jahr bewegt? Dieser fette Balken wird **POC (Point of Control)** genannt. Das ist ein massiver Magnet; der Kurs tendiert dazu, zum POC zurückzukehren.
            """)

        with st.expander("📈 Pivot-Punkte (Swing Trading Matrix)"):
            st.markdown("""
            Berechnet nach der Markteröffnung statische Level für den Tag oder Monat, basierend auf dem Hoch/Tief/Schluss des Vortages.
            
            - **Pivot (P):** Der Ankerpunkt. Kurs über P = bullisher Tag. Unter P = bärischer Tag.
            - **S1 / S2 (Supports):** Rechnerische Levels, an denen sich extrem oft Algorithmen platzieren, um abzuprallen.
            - **R1 / R2 (Resistances):** Mathematische Zielzonen, an denen Daytrader ihre Gewinne einstreichen (Take-Profit).
            
            **Risk/Reward Ratio:** Das Dashboard berechnet automatisch ein Stop-Loss (basierend auf 1.5× ATR) und ein Take-Profit-Level (2.5× ATR). Ein gutes R:R-Verhältnis ist mindestens 1:2 — du riskierst 1 €, um 2 € zu gewinnen.
            """)

        with st.expander("🧲 Fair Value Gap (FVG) — Smart Money Concepts"):
            st.markdown("""
            **Das Konzept:** Eine Fair Value Gap entsteht, wenn ein Impuls so stark ist, dass zwischen drei aufeinanderfolgenden Kerzen eine **Preislücke** bleibt — ein Bereich, in dem kein wirklicher Handel stattgefunden hat.
            
            **Mechanik (Bullish FVG):**
            1. Kerze 1 hat ein Hoch bei 100 €.
            2. Kerze 2 ist eine massive grüne Impuls-Kerze (z.B. durch Earnings Surprise).
            3. Kerze 3 hat ein Tief bei 103 €.
            4. → Die Lücke zwischen 100 € und 103 € ist das **FVG** — hier wurde „unfairer" Preis geschaffen.
            
            **Warum wichtig?**
            - Der Markt hat die Tendenz, FVGs irgendwann zu „füllen" (mitigieren) — der Kurs kehrt zu dieser Zone zurück.
            - **Offene bullische FVGs unter dem aktuellen Kurs** = potenzielle Support-Zonen (der Kurs wird dort wahrscheinlich aufgefangen).
            - **Offene bearische FVGs über dem aktuellen Kurs** = potenzielle Resistance-Zonen (der Kurs wird dort wahrscheinlich abprallen).
            - **Mitigierte FVGs** = bereits gefüllt, keine weitere Relevanz.
            
            **Im Dashboard:** Grüne Zonen = bullische FVGs (Support), Rote Zonen = bearische FVGs (Resistance).
            """)

        with st.expander("⚖️ Equal Highs & Equal Lows (EQH / EQL) — Liquiditäts-Magnete"):
            st.markdown("""
            **Das Konzept:** Wenn der Kurs zwei oder mehr Swing-Hochs auf nahezu dem gleichen Level bildet (Equal Highs), 
            oder zwei Swing-Tiefs auf dem gleichen Level (Equal Lows), entsteht ein **Liquiditäts-Pool**.
            
            **Warum sind sie Magnete?**
            - Über EQHs sammeln sich massenhaft **Stop-Loss-Orders von Short-Sellern** und **Breakout-Buy-Orders** von Tradern.
            - Unter EQLs sammeln sich massenhaft **Stop-Loss-Orders von Long-Positionen** und **Breakout-Sell-Orders**.
            - Institutionelle Akteure (Smart Money) wissen das — und treiben den Kurs gezielt zu diesen Leveln, um diese Liquidität zu „ernten".
            
            **Interpretation:**
            - Befindet sich der Kurs nahe einem **EQH** → Die Wahrscheinlichkeit steigt, dass er dieses Level *durchbricht* (Sweep), um die darüberliegende Liquidität einzusammeln.
            - Befindet sich der Kurs nahe einem **EQL** → Risiko eines Sweeps nach unten.
            - **Nach dem Sweep** dreht der Kurs oft abrupt in die Gegenrichtung — das ist die eigentliche Trading-Chance.
            
            **Im Dashboard:** EQH werden als horizontale Linien über dem Kurs angezeigt, EQL darunter. Die Distanz in % zum aktuellen Kurs wird in der Zusammenfassung angezeigt.
            """)

        with st.expander("📝 Zusammenfassung (Gesamtbewertung) — Wie der Score funktioniert"):
            st.markdown("""
            Die Zusammenfassung aggregiert alle technischen und strategischen Signale in einem **Gesamtscore** und drei **Textinterpretationen**.
            
            **Scoring-System:**
            Jeder Indikator liefert +1 (bullisch), 0 (neutral) oder -1 (bearisch):
            
            | Indikator | +1 wenn | -1 wenn |
            |---|---|---|
            | SMA 200 | Kurs über SMA 200 | Kurs unter SMA 200 |
            | SMA 50/20 Cross | Golden Cross | Death Cross |
            | MACD | MACD > Signal | MACD < Signal |
            | RSI | Neutral (30-70) | Überkauft oder Überverkauft |
            | Stochastic | %K > %D | %K < %D |
            | Bollinger | Mittleres Band | Am oberen/unteren Band |
            | ADX | Trendstärke > 25 | — |
            | VWAP | Kurs über VWAP | Kurs unter VWAP |
            | OBV | Steigend (Akkumulation) | Fallend (Distribution) |
            | FVG | Mehr bullische als bearische offene Gaps | Umgekehrt |
            
            **Drei Interpretationsebenen:**
            1. **Makro-Bild (Trend):** Fasst die langfristige Trendlage zusammen (SMA 200, Cross, ADX).
            2. **Mikro-Bild (Momentum):** Kurzfristige Extreme, Volumen-Divergenzen, FVG/EQH/EQL-Nähe.
            3. **Actionable Insight:** Konkrete Handlungsempfehlung basierend auf dem Gesamtbild.
            
            **Score-Labels:**
            - ≥ 3: Bullisch 🟢
            - 1-2: Leicht Bullisch ↗️
            - 0: Neutral ➖
            - -1 bis -2: Leicht Bearisch ↘️
            - ≤ -3: Bearisch 🔴
            """)

    # =========================================================================
    # 5. Risiko & Backtesting
    # =========================================================================
    with tab_risk:
        st.markdown("### Risiko-Management & Strategie-Validierung")
        st.markdown("Der Unterscheid zwischen einem Zocker und einem Investor ist die mathematische Kontrolle über sein Risiko.")
        st.markdown("---")

        with st.expander("💸 Value at Risk (VaR) & Monte Carlo Simulation"):
            st.markdown("""
            Das ultimative Risiko-Maß für institutionelle Portfolios. VaR beantwortet die Frage:
            **"Wie viel Geld kann ich an einem extrem schlechten Tag realistisch verlieren?"**
            
            - **Monte Carlo Methode:** Eine statistische Simulation, die anhand der historischen Volatilität zehntausende fiktive "Zukünfte" berechnet.
            - **Beispiel (95% Confidence):** Ein VaR von -2.500 € bedeutet: An 95 von 100 Handelstagen verlierst du *nicht mehr* als 2.500€. Nur an den verbleibenden 5 extremen "Schwarzer Schwan"-Tagen wird dieser Verlust überschritten.
            
            **Warum wichtig?** Wer seinen VaR kennt, schließt keine panischen Kurzschluss-Verkäufe ab, wenn das Portfolio mal um 2.000€ schwankt, weil dies noch im erwartbaren statistischen Norm-Rahmen liegt.
            """)

        with st.expander("📉 Max Drawdown (MDD)"):
            st.markdown("""
            Der MDD ist der schlimmste prozentuale Sturzflug, den dein Aktienportfolio jemals "im Schmerz" aussitzen müsste, von einem historischen Hochpunkt (Peak) bis zum tiefsten Tal (Trough), bevor ein neues Hoch erreicht wurde.
            
            - Ein MDD von **-40%** bedeutet: Wer am absolut schlechtesten Tag "am Top" investiert hat, saß zwischenzeitlich auf 40% Buchverlust.
            - **Drawdown Recovery:** Um einen Drawdown von -50% wettzumachen, braucht man +100% Rendite!
            
            **Strategie:** Beim Backtesting ist ein exzellenter Profit Factor fast wertlos, wenn der Max Drawdown bei -70% liegt – du wärst psychologisch höchstwahrscheinlich vorher ausgestiegen. Ein MDD < -20% gilt bei professionellen Strategien als Grenzwert.
            """)

        with st.expander("⚖️ Sharpe Ratio & Profit Factor"):
            st.markdown("""
            Die perfekten Indikatoren zur Messung, wie effizient und stressfrei eine Strategie Geld verdient.
            
            - **Profit Factor:** Bruttogewinn / Bruttoverlust aller Trades. Ein Wert von 1.0 bedeutet Break-Even. Ein Profit-Factor > 1.5 gilt als überragend gut, da jeder investierte verlorene Euro dir 1,50€ neuen Gewinn bringt.
            - **Sharpe Ratio:** Risikoadjustierte Rendite. Sie misst, wie viel "Überrendite" du gegenüber einem völlig risikofreien Zinssatz pro Einheit Volatilität ("Stress") erhältst.
            
            Ein Sharpe Ratio > 1.0 ist gut, > 2.0 ist grandios. (Bedeutet: Die Renditekurve verläuft extrem geschmeidig bergauf ohne heftige Auf-und-Abs).
            """)

        with st.expander("🛒 Slippage"):
            st.markdown("""
            Der unsichtbare Rendite-Killer im Trading.
            **Slippage** ist die Differenz zwischen dem Preis, zu dem ein Trading-Signal (z.B. aus dem Screener) gefeuert wurde, und dem tatsächlichen *Ausführungspreis* der Order bei deinem Broker.
            
            - Passiert meistens durch extrem schnell drehende Kurse oder schlechte Liquidität (hoher Ask/Bid-Spread).
            - Die **Backtesting Engine** in dieser App kalkuliert aktiv reale Gebühren (z.B. Trade Republic Flat Fee) sowie *Slippage* ein, um keine unrealistischen Excel-Illusionen zu erschaffen, sondern harte Praxis-Realität.
            """)

    # =========================================================================
    # 6. Sentiment & News Flow
    # =========================================================================
    with tab_sent:
        st.markdown("### Qualitative Stimmung & News-Algorithmen")
        st.markdown("Märkte werden nicht primär von Zahlen bewegt, sondern von Gier, Angst und narrativer Stimmungs-Manipulation.")
        st.markdown("---")

        with st.expander("🧠 VADER NLP (Sentiment-Analysis)"):
            st.markdown("""
            **VADER** (Valence Aware Dictionary and sEntiment Reasoner) ist ein fortschrittlicher "Natural Language Processing" (NLP) Algorithmus zur Textanalyse.
            
            - Anstatt dass du alle Yahoo-Finance Artikel selbst lesen musst, lädt die App im Hintergrund Tausende Wörter und füttert sie durch die VADER-Engine, welche durch unsere **spezifische Wall-Street-Erweiterung** kalibriert ist.
            - "Missed Estimates" oder "Dividend Cut" strafen den Score hart ab, während Worte wie "Surge" oder "Upgrade" den AI-Kompass ins Bullische treiben.
            - Der **Compound-Score** liegt zwischen -1.0 (Apokalypse) und +1.0 (Euphorie) und fließt live in den Confidence-Score der App mit ein.
            """)

        with st.expander("🧨 Die Euphorie-Falle (Contrarian-Signal)"):
            st.markdown("""
            Eine systemeigene Logik deines MacroDashboards, um "Buy the Rumor, Sell the News" Phänomene abzufangen.
            
            Wenn das **NLP-Sentiment** astronomisch positiv ist (Score > 0.15) – sprich die Medienlandschaft lobpreist die Aktie auf jedem Kanal – aber gleichzeitig der technische **RSI (14)** bereits weit über 70 (Overbought) liegt, droht akute Gefahr.
            Das Dashboard löst einen automatischen **Confidence-Penalty (-15%)** aus, um dich davon abzuhalten, am absoluten lokalen "Retail-Top" zu kaufen.
            """)

        with st.expander("🔁 Options Flow: Put/Call-Ratio & Max Pain"):
            st.markdown("""
            Der professionelle Optionsmarkt diktiert oft, wo eine Aktie am Verfallstag landen muss, da Großinvestoren ("Market Maker") versuchen, ihre Profite zu maximieren.
            
            - **Put/Call-Ratio:** Ein extremer Contrarian-Indikator. Ein sehr hoher Wert (> 1.2) bedeutet irrationale Massen-Panik (alle sichern sich ab) – das eigentliche Kaufsignal. Ein extrem tiefer Wert (< 0.5) deutet auf blinde Gier.
            - **Max Pain Level:** Der magnetische Kurs-Preis (Strike-Preis), bei dem am Verfallstag (Options Expiration) die absolute *Mehrheit* aller Put- und Call-Käufer wertlos verfallen und ihr Geld an die institutionellen Aussteller der Optionen verlieren. Der Aktienkurs "gleitet" magischerweise am Freitag oftmals genau auf die Max-Pain Marke hin.
            """)

    # =========================================================================
    # 7. System-Architektur — Warum jedes Tool existiert
    # =========================================================================
    with tab_arch:
        st.markdown("### 🧠 System-Architektur — Warum jedes Tool existiert")
        st.markdown(
            "Studien zeigen: **80–90% aller privaten Trader verlieren Geld.** "
            "Nicht wegen fehlender Strategie, sondern wegen wiederkehrender, vermeidbarer Fehler. "
            "Jedes Feature im MacroDashboard existiert, um einen spezifischen dieser Fehler zu verhindern."
        )
        st.markdown("---")

        # ── Fehler-Präventions-Tabelle ────────────────────────────────
        st.markdown("#### Die 7 häufigsten Trading-Fehler")
        import pandas as pd
        error_data = pd.DataFrame([
            {"#": "1", "Fehlertyp": "Ohne Analyse kaufen (FOMO)", "Häufigkeit": "Sehr häufig", "Schutzmechanismus": "Scoring Engine + Analyse"},
            {"#": "2", "Fehlertyp": "Kein Stop-Loss setzen", "Häufigkeit": "Häufig", "Schutzmechanismus": "Position Sizing + SL-Pflichtfeld"},
            {"#": "3", "Fehlertyp": "Zu viel in einen Sektor", "Häufigkeit": "Häufig", "Schutzmechanismus": "Risiko-Analyse (Herfindahl)"},
            {"#": "4", "Fehlertyp": "Gegen den Markttrend handeln", "Häufigkeit": "Häufig", "Schutzmechanismus": "Home (Fear & Greed) + Makro"},
            {"#": "5", "Fehlertyp": "Aus Fehlern nicht lernen", "Häufigkeit": "Sehr häufig", "Schutzmechanismus": "Trade-Journal (Auto-Review)"},
            {"#": "6", "Fehlertyp": "Strategie nie getestet", "Häufigkeit": "Häufig", "Schutzmechanismus": "Backtesting Engine"},
            {"#": "7", "Fehlertyp": "Euphorie-Falle (Retail-Top)", "Häufigkeit": "Häufig", "Schutzmechanismus": "Contrarian-Warnung (-15% Conf.)"},
        ])
        st.dataframe(error_data, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Der 8-Phasen Workflow ─────────────────────────────────────
        st.markdown("#### Der optimale Trading-Workflow (8 Phasen)")

        with st.expander("🌍 Phase 1: Marktlage checken (Home + Gesamtwirtschaft)", expanded=False):
            st.markdown("""
            **Ziel:** Niemals kaufen, wenn der Gesamtmarkt zusammenbricht.

            | Feature | Funktion | Regel |
            |---------|----------|-------|
            | Fear & Greed Index | Marktstimmung (0-100) | Extreme Gier (>80) → NICHT kaufen. Extreme Angst (<20) → Kaufchancen |
            | Wirtschaftskalender | Wichtige Termine | Nie kurz vor Fed-Zinsentscheid einsteigen |
            | Zinsstrukturkurve | Rezessions-Frühindikator | Wenn invertiert → defensiv bleiben |
            """)

        with st.expander("🔍 Phase 2: Kandidaten finden (Screener + Sektoren)", expanded=False):
            st.markdown("""
            **Ziel:** Aus tausenden Aktien die besten filtern.

            - **Screener:** Filtert S&P 500 nach deinen Kriterien (z.B. RSI < 30 + über SMA 200)
            - **Sektor-Heatmap:** Profis kaufen die stärkste Aktie im stärksten Sektor — nie eine "billige" Aktie in einem sterbenden Sektor
            """)

        with st.expander("🔬 Phase 3: Tiefenanalyse + Scoring Engine", expanded=False):
            st.markdown("""
            **Ziel:** Emotionale Entscheidungen verhindern. Das Herzstück der Analyse.

            Die Scoring Engine bewertet jede Aktie auf **5 Kategorien**:

            | Kategorie | Gewichtung | Indikatoren |
            |-----------|-----------|-------------|
            | Trend | 30% | SMA 200, MACD, ADX |
            | Volumen | 25% | OBV, VWAP, POC |
            | Fundamental | 20% | DCF, Bilanz, Insider |
            | Sentiment | 15% | News NLP Analyse |
            | Oszillator | 10% | RSI, Stochastic, Bollinger |

            **Euphorie-Falle:** Wenn News extrem bullish (>0.15) UND RSI überkauft (>70) → automatisch **-15% Confidence**.
            Das verhindert Käufe am "Retail-Top".
            """)

        with st.expander("⏱ Phase 4: Backtesting — Strategie beweisen", expanded=False):
            st.markdown("""
            **Ziel:** Nie echtes Geld in eine ungetestete Strategie stecken.

            - Simuliert Strategien über 1+ Jahre historischer Daten
            - Zeigt Win-Rate, Max Drawdown, Sharpe Ratio
            - **Beispiel:** "Kaufen wenn RSI < 30" → Backtest zeigt: 62% Win-Rate, aber Max Drawdown -28%. Kannst du das aushalten?
            """)

        with st.expander("🛒 Phase 5: Position eröffnen — Professionelle Buchführung", expanded=False):
            st.markdown("""
            **Ziel:** Disziplin erzwingen durch 3 Mechanismen:

            **1. Stop-Loss & Take-Profit VOR dem Kauf definieren**
            - Ohne SL: Apple bei 150€ gekauft → fällt auf 100€ → -33% Verlust
            - Mit SL bei 135€: Maximal -10% Verlust → Kapital für bessere Trades frei

            **2. Position Sizing Calculator**
            - Berechnet automatisch: "Bei 2% Risiko auf 10.000€ Konto und SL 15€ unter Kaufkurs → max. 13 Stück"
            - Zeigt Risk/Reward Ratio (ideal ≥ 1:2)

            **3. Live P&L + Risiko-Analyse**
            - Unrealisierter Gewinn/Verlust in Echtzeit
            - VaR, Beta, Sektor-Konzentration, Korrelationsrisiko
            """)

        with st.expander("🛡️ Phase 6: Risiko überwachen", expanded=False):
            st.markdown("""
            **Ziel:** Wissen, ob das Gesamtportfolio gesund ist.

            | Metrik | Was es sagt | Grenzwert |
            |--------|------------|----------|
            | VaR (95%) | "Max. 500€ Tagesverlust mit 95% Wahrscheinlichkeit" | Individuell |
            | Portfolio-Beta | Schwankung relativ zum Markt | > 1.5 = zu aggressiv |
            | Herfindahl-Index | Sektor-Konzentration | > 0.4 = Klumpenrisiko |
            | Korrelation | "NVDA und AMD korrelieren 0.85" | > 0.7 = schlechte Diversifikation |
            | Max Drawdown | Tiefster Punkt seit dem Hoch | > -20% = Strategie überdenken |
            """)

        with st.expander("📤 Phase 7: Position schließen + Auto-Journal", expanded=False):
            st.markdown("""
            **Ziel:** Jeder Trade wird dokumentiert — automatisch.

            Beim Schließen einer Position wird automatisch ein Journal-Eintrag erstellt mit:
            - Entry/Exit Preis + Datum
            - P&L in € und % (automatisch als Gewonnen/Verloren/Break-Even klassifiziert)
            - Setup-Kategorie (SMC, Trendfolge, Breakout, etc.)
            - Dein persönliches "Lessons Learned" Review
            """)

        with st.expander("📓 Phase 8: Lernen (Trade-Journal)", expanded=False):
            st.markdown("""
            **Ziel:** Aus Fehlern lernen, Stärken erkennen.

            Das Journal zeigt:
            - **Win-Rate pro Setup-Typ:** "Trendfolge hat 68% Win-Rate, Breakout nur 42%" → Mehr Trendfolge!
            - **AI-Signale:** Wie treffsicher war der automatische Scoring-Algorithmus? Kalibrierungschart nach Confidence-Bereichen.
            - **Historische Trades:** Vollständige Chronik mit Review-Kommentaren.
            """)

        st.markdown("---")

        # ── Vergleich: Mit vs. Ohne ───────────────────────────────────
        st.markdown("#### Ohne vs. Mit MacroDashboard")
        compare_data = pd.DataFrame([
            {"Bereich": "Analyse", "Ohne": '"Hab auf Reddit gelesen"', "Mit MacroDashboard": "5-Kategorie-Score + Euphorie-Check"},
            {"Bereich": "Timing", "Ohne": '"Gefühl"', "Mit MacroDashboard": "RSI + MACD + Bollinger"},
            {"Bereich": "Risiko", "Ohne": '"Geht schon"', "Mit MacroDashboard": "VaR, Beta, Korrelation"},
            {"Bereich": "Stop-Loss", "Ohne": "Vergessen", "Mit MacroDashboard": "Beim Kauf definiert + Position Sizing"},
            {"Bereich": "Dokumentation", "Ohne": "Keine", "Mit MacroDashboard": "Auto-Journal bei jedem Exit"},
            {"Bereich": "Lernen", "Ohne": '"Aus Fehlern? Welche?"', "Mit MacroDashboard": "Win-Rate pro Setup + P&L Historie"},
            {"Bereich": "Strategie-Test", "Ohne": '"Trust me bro"', "Mit MacroDashboard": "Backtesting mit echten Daten"},
        ])
        st.dataframe(compare_data, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Täglicher Workflow ────────────────────────────────────────
        st.markdown("#### 🎯 Optimaler täglicher Workflow (~25 Min.)")
        workflow_data = pd.DataFrame([
            {"Zeit": "08:00", "Aktion": "Marktcheck: Fear & Greed, Termine", "Tool": "Home + Gesamtwirtschaft", "Dauer": "5 Min"},
            {"Zeit": "08:05", "Aktion": "Screener laufen lassen", "Tool": "Screener", "Dauer": "3 Min"},
            {"Zeit": "08:08", "Aktion": "Top-Kandidaten analysieren", "Tool": "Analyse + Scoring", "Dauer": "10 Min"},
            {"Zeit": "08:18", "Aktion": "Strategie per Backtest validieren", "Tool": "Backtesting", "Dauer": "5 Min"},
            {"Zeit": "08:23", "Aktion": "Position eröffnen mit SL/TP", "Tool": "Watchlist", "Dauer": "2 Min"},
            {"Zeit": "Laufend", "Aktion": "Portfolio + Risiko überwachen", "Tool": "Watchlist → Risiko", "Dauer": "—"},
            {"Zeit": "Bei Exit", "Aktion": "Position schließen + Journal", "Tool": "Journal", "Dauer": "5 Min"},
        ])
        st.dataframe(workflow_data, use_container_width=True, hide_index=True)

        st.info(
            "💡 **Jedes einzelne Feature existiert, weil es einen spezifischen Fehler verhindert, "
            "der nachweislich zu Verlusten führt.** Nichts ist \"nice to have\" — es ist die Differenz "
            "zwischen einem emotionalen Gambler und einem datengetriebenen Trader."
        )
