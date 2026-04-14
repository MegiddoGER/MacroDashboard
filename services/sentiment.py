"""
services/sentiment.py — Sentiment-Analyse für Finanznachrichten.

Nutzt VADER Sentiment-Analyse (angereichert mit Finanz-Vokabular),
um News-Headlines als Bullish, Bearish oder Neutral zu klassifizieren.
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import pandas as pd


# ---------------------------------------------------------------------------
# Initialisierung & Custom Lexicon
# ---------------------------------------------------------------------------

_analyzer = None

def _get_analyzer() -> SentimentIntensityAnalyzer:
    """Gibt einen Singleton VADER-Analyzer mit erweitertem Finanz-Lexikon zurück."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
        
        # Erweitertes Finanz-Lexikon (VADER Skala von -4 bis +4)
        # Kategorien: Earnings, M&A, Bewertung, Management, Regulierung, Makro
        finance_lexicon = {
            # --- Earnings & Guidance ---
            "beat": 2.0,
            "beats": 2.0,
            "miss": -2.0,
            "misses": -2.0,
            "missed": -2.0,
            "smashes": 3.0,
            "crushes": 3.0,
            "topped": 2.0,
            "exceeded": 2.0,
            "fell short": -2.5,
            "shortfall": -2.5,
            "raises guidance": 3.0,
            "raised guidance": 3.0,
            "cuts guidance": -3.0,
            "lowered guidance": -3.0,
            "narrowed guidance": -0.5,
            "record earnings": 3.5,
            "earnings miss": -2.5,
            "earnings beat": 2.5,
            "revenue miss": -2.0,
            "revenue beat": 2.0,
            "profit warning": -3.5,
            # --- Upgrades/Downgrades ---
            "upgrade": 2.5,
            "upgraded": 2.5,
            "upgrades": 2.5,
            "downgrade": -2.5,
            "downgraded": -2.5,
            "downgrades": -2.5,
            "outperform": 2.0,
            "underperform": -2.0,
            "overweight": 1.5,
            "underweight": -1.5,
            "price target raised": 2.0,
            "price target cut": -2.0,
            "initiated coverage": 0.5,
            # --- M&A & Corporate Actions ---
            "merger": 1.5,
            "acquisition": 1.5,
            "acquires": 1.5,
            "buyback": 2.0,
            "share repurchase": 2.0,
            "stock split": 1.0,
            "spinoff": 0.5,
            "ipo": 1.0,
            "delisting": -2.5,
            # --- Dividenden ---
            "dividend hike": 2.0,
            "dividend increase": 2.0,
            "dividend cut": -3.0,
            "dividend suspension": -3.5,
            "eliminated dividend": -3.5,
            "special dividend": 2.5,
            # --- Preisbewegungen ---
            "surge": 2.5,
            "surges": 2.5,
            "soar": 2.5,
            "soars": 2.5,
            "rally": 2.0,
            "rallies": 2.0,
            "rebound": 1.5,
            "recovery": 1.0,
            "plunge": -3.0,
            "plunges": -3.0,
            "plummet": -3.0,
            "plummets": -3.0,
            "slump": -2.5,
            "slumps": -2.5,
            "tumble": -2.5,
            "tumbles": -2.5,
            "crash": -3.5,
            "selloff": -2.5,
            "sell-off": -2.5,
            "correction": -1.5,
            "decline": -1.5,
            "record high": 3.0,
            "all-time high": 3.0,
            "record low": -3.0,
            "52-week low": -2.0,
            "52-week high": 2.0,
            # --- Sentiment-Begriffe ---
            "bullish": 2.5,
            "bearish": -2.5,
            "hawkish": -1.0,
            "dovish": 1.0,
            "optimistic": 2.0,
            "pessimistic": -2.0,
            "cautious": -0.5,
            "confident": 1.5,
            # --- Negativ-Events ---
            "scandal": -3.5,
            "fraud": -4.0,
            "investigation": -2.0,
            "probe": -1.5,
            "lawsuit": -2.0,
            "sued": -2.0,
            "fined": -2.5,
            "penalty": -2.0,
            "recall": -2.0,
            "breach": -2.5,
            "hack": -2.5,
            "layoffs": -1.5,
            "restructuring": -1.0,
            "resigns": -2.0,
            "steps down": -1.5,
            "fired": -2.0,
            "bankruptcy": -4.0,
            "default": -4.0,
            "insolvent": -4.0,
            "chapter 11": -3.5,
            # --- Makro ---
            "rate hike": -1.0,
            "rate cut": 1.0,
            "inflation": -0.5,
            "recession": -2.5,
            "stimulus": 1.5,
            "tariff": -1.5,
            "sanctions": -2.0,
            "shutdown": -1.5,
        }
        _analyzer.lexicon.update(finance_lexicon)
        
    return _analyzer


# ---------------------------------------------------------------------------
# Single Text Analysis
# ---------------------------------------------------------------------------

def analyze_text_sentiment(text: str) -> dict:
    """Berechnet Sentiment eines einzelnen Textes.
    
    Returns:
        Dict mit {'compound', 'pos', 'neu', 'neg', 'label'}
    """
    if not text or not isinstance(text, str):
        return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0, "label": "Neutral"}
        
    analyzer = _get_analyzer()
    scores = analyzer.polarity_scores(text)
    
    # Labeling nach Compound Score
    c = scores["compound"]
    if c >= 0.05:
        label = "Bullish"
    elif c <= -0.05:
        label = "Bearish"
    else:
        label = "Neutral"
        
    scores["label"] = label
    return scores


# ---------------------------------------------------------------------------
# Ticker News Analysis
# ---------------------------------------------------------------------------

def analyze_ticker_news(ticker: str) -> dict:
    """Sammelt die letzten News für einen Ticker und bewertet das Gesamt-Sentiment.
    
    Returns:
        Dict mit avg_compound, n_articles, bullish_pct, bearish_pct, recent_headlines
    """
    # Import hier um Zirkelbezüge zu vermeiden, falls data_cache sentiment.py importiert
    from services.cache import cached_company_news
    
    news_items = cached_company_news(ticker)
    
    if not news_items:
        return {
            "avg_compound": 0.0,
            "n_articles": 0,
            "bullish_pct": 0.0,
            "bearish_pct": 0.0,
            "neutral_pct": 100.0,
            "recent_headlines": [],
            "overall_label": "Keine Daten",
        }
    
    # Text pro News-Eintrag auswerten (Headline + Summary)
    total_compound = 0.0
    bullish = 0
    bearish = 0
    neutral = 0
    
    headlines_analyzed = []
    
    for item in news_items:
        title = item.get("title", "")
        summary = item.get("summary", "")
        # Titel und Summary als einzelnen zusammenhängenden Text analysieren
        # (kein Titel-Verdopplungs-Trick — das verzerrt VADER's nicht-lineares Scoring)
        text_to_analyze = f"{title}. {summary}" if summary else title
        
        scores = analyze_text_sentiment(text_to_analyze)
        c = scores["compound"]
        
        # Original Title Score fürs Display
        title_scores = analyze_text_sentiment(title)
        
        total_compound += c
        
        if c >= 0.05:
            bullish += 1
        elif c <= -0.05:
            bearish += 1
        else:
            neutral += 1
            
        headlines_analyzed.append({
            "title": title,
            "link": item.get("link", "#"),
            "publisher": item.get("publisher", ""),
            "timestamp": item.get("timestamp", ""),
            "compound": title_scores["compound"],
            "label": title_scores["label"],
        })
        
    n = len(news_items)
    avg_compound = total_compound / n
    
    # Gesamt-Label
    if avg_compound >= 0.15:
        overall_label = "🔥 Stark Bullish"
    elif avg_compound >= 0.05:
        overall_label = "🟢 Bullish"
    elif avg_compound <= -0.15:
        overall_label = "🧨 Stark Bearish"
    elif avg_compound <= -0.05:
        overall_label = "🔴 Bearish"
    else:
        overall_label = "➖ Neutral / Gemischt"
        
    return {
        "avg_compound": round(avg_compound, 3),
        "n_articles": n,
        "bullish_pct": round(bullish / n * 100, 1),
        "bearish_pct": round(bearish / n * 100, 1),
        "neutral_pct": round(neutral / n * 100, 1),
        "recent_headlines": headlines_analyzed[:5],  # Nur die Top 5 mitgeben
        "overall_label": overall_label,
    }
