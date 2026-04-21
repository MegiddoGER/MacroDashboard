"""
services/news.py — Nachrichtenabruf (RSS-Feeds und yfinance).

Extrahiert aus data.py für saubere Trennung.
"""

import warnings
import yfinance as yf


# ---------------------------------------------------------------------------
# Kuratierte RSS-Feed-URLs nach Region
# ---------------------------------------------------------------------------

_RSS_FEEDS = {
    "europa": [
        ("Reuters DE",    "https://news.google.com/rss/search?q=when:24h+site:reuters.com+Wirtschaft&hl=de&gl=DE&ceid=DE:de"),
        ("Tagesschau",    "https://www.tagesschau.de/wirtschaft/konjunktur/index~rss2.xml"),
        ("Handelsblatt",  "https://www.handelsblatt.com/contentexport/feed/schlagzeilen"),
    ],
    "usa": [
        ("Reuters",       "https://news.google.com/rss/search?q=when:24h+site:reuters.com+markets&hl=en-US&gl=US&ceid=US:en"),
        ("CNBC",          "https://www.cnbc.com/id/100727362/device/rss/rss.html"),
    ],
    "asien": [
        ("Reuters Asia",  "https://news.google.com/rss/search?q=when:24h+site:reuters.com+Asia+markets&hl=en&gl=US&ceid=US:en"),
        ("Nikkei Asia",   "https://asia.nikkei.com/rss/feed/nar"),
        ("CNBC Asia",     "https://www.cnbc.com/id/19832390/device/rss/rss.html"),
    ],
}


# ---------------------------------------------------------------------------
# Quellenqualität — Filter & Badges
# ---------------------------------------------------------------------------

_PREMIUM_SOURCES = {
    "Reuters", "Bloomberg", "Financial Times", "AP News",
    "Wall Street Journal", "Barron's", "Yahoo Finance",
    "CNBC", "Handelsblatt", "Tagesschau", "Nikkei Asia",
}

_CLICKBAIT_SOURCES = {
    "Motley Fool", "The Motley Fool", "InvestorPlace",
    "24/7 Wall St.", "24/7 Wall Street", "Zacks",
    "TipRanks", "Benzinga", "TheStreet", "Insider Monkey",
    "GuruFocus", "Seeking Alpha",
}


def get_regional_news(region: str, max_items: int = 15) -> list[dict] | None:
    """Lädt Macro-Nachrichten für eine Region via RSS-Feeds.

    region: 'europa', 'usa' oder 'asien'.
    Rückgabe: Liste von Dicts [{title, link, published, source}, ...],
              sortiert nach Datum (neueste zuerst), oder None bei Fehler.
    """
    import feedparser
    from datetime import datetime
    from time import mktime

    feeds = _RSS_FEEDS.get(region.lower())
    if not feeds:
        warnings.warn(f"get_regional_news: unbekannte Region '{region}'")
        return None

    articles = []
    seen_titles = set()

    for source_name, feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                link = entry.get("link", "")
                # Datum parsen
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime.fromtimestamp(mktime(entry.published_parsed))
                    except Exception:
                        pass
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    try:
                        published = datetime.fromtimestamp(mktime(entry.updated_parsed))
                    except Exception:
                        pass

                # Zusammenfassung (Kernaussage) aus RSS-Feed
                summary = ""
                raw_summary = entry.get("summary", "") or entry.get("description", "")
                if raw_summary:
                    # HTML-Tags entfernen (einfach)
                    import re
                    summary = re.sub(r"<[^>]+>", "", raw_summary).strip()
                    # Auf sinnvolle Länge kürzen
                    if len(summary) > 200:
                        summary = summary[:197] + "…"

                articles.append({
                    "title": title,
                    "link": link,
                    "published": published,
                    "source": source_name,
                    "summary": summary,
                })
        except Exception as exc:
            warnings.warn(f"RSS-Feed {source_name} ({feed_url}): {exc}")
            continue

    if not articles:
        return None

    # Nach Datum sortieren (neueste zuerst), Einträge ohne Datum ans Ende
    articles.sort(
        key=lambda a: a["published"] or datetime.min,
        reverse=True,
    )
    return articles[:max_items]


def get_company_news(ticker: str, max_items: int = 10) -> list[dict] | None:
    """Lädt ticker-spezifische Nachrichten via yfinance.

    Rückgabe: Liste von Dicts [{title, link, published, source}, ...],
              oder None bei Fehler.
    """
    try:
        tk = yf.Ticker(ticker)
        raw_news = tk.news
        if not raw_news:
            return None

        articles = []
        for item in raw_news[:max_items]:
            content = item.get("content", {})
            if not content:
                continue

            title = content.get("title", "").strip()
            if not title:
                continue

            # Publisher
            provider = content.get("provider", {})
            source = provider.get("displayName", "Yahoo Finance") if provider else "Yahoo Finance"

            # Link
            click_url = content.get("clickThroughUrl", {})
            link = ""
            if click_url:
                link = click_url.get("url", "")
            if not link:
                canonical = content.get("canonicalUrl", {})
                link = canonical.get("url", "") if canonical else ""

            # Datum
            published = None
            pub_date = content.get("pubDate")
            if pub_date:
                try:
                    from datetime import datetime
                    # yfinance liefert ISO-Format
                    published = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                except Exception:
                    pass

            # Zusammenfassung (Kernaussage) — direkt von Yahoo geliefert
            summary = content.get("summary", "").strip()

            # Quellenqualität prüfen
            is_premium = any(ps.lower() in source.lower() for ps in _PREMIUM_SOURCES)
            is_clickbait = any(cs.lower() in source.lower() for cs in _CLICKBAIT_SOURCES)

            # Clickbait-Quellen komplett filtern
            if is_clickbait:
                continue

            articles.append({
                "title": title,
                "link": link,
                "published": published,
                "source": source,
                "summary": summary,
                "premium": is_premium,
            })

        return articles if articles else None
    except Exception as exc:
        warnings.warn(f"get_company_news({ticker}): {exc}")
        return None
