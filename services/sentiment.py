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
    """Gibt einen Singleton VADER-Analyzer mit Finanz-Lexikon zurück."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
        
        # Finanzspezifische Gewichtungen (VADER Skala von -4 bis +4)
        finance_lexicon = {
            "upgrade": 2.5,
            "upgraded": 2.5,
            "upgrades": 2.5,
            "downgrade": -2.5,
            "downgraded": -2.5,
            "downgrades": -2.5,
            "beat": 2.0,
            "miss": -2.0,
            "smashes": 3.0,
            "crushes": 3.0,
            "plunge": -3.0,
            "plummet": -3.0,
            "surge": 2.5,
            "rally": 2.0,
            "bullish": 2.5,
            "bearish": -2.5,
            "outperform": 2.0,
            "underperform": -2.0,
            "soar": 2.5,
            "slump": -2.5,
            "buyback": 2.0,
            "dividend hike": 2.0,
            "dividend cut": -3.0,
            "scandal": -3.5,
            "fraud": -4.0,
            "resigns": -2.0,
            "steps down": -1.5,
            "record high": 3.0,
            "record low": -3.0,
            "raises guidance": 3.0,
            "cuts guidance": -3.0,
            "merger": 1.5,
            "acquisition": 1.5,
            "bankruptcy": -4.0,
            "default": -4.0,
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
    
    # Text pro News-Eintrag auswerten (Headline + kurze Summary)
    total_compound = 0.0
    bullish = 0
    bearish = 0
    neutral = 0
    
    headlines_analyzed = []
    
    for item in news_items:
        title = item.get("title", "")
        summary = item.get("summary", "")
        # Titel oft aussagekräftiger, wir verdoppeln das Gewicht des Titels
        text_to_analyze = f"{title}. {title}. {summary}" 
        
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
