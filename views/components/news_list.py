"""
views/components/news_list.py — Wiederverwendbare Nachrichtenlistenkomponente.
"""

import streamlit as st


def render_news_list(articles: list[dict]):
    """Rendert eine einheitliche Nachrichten-Liste im Dark-Theme."""
    for i, article in enumerate(articles):
        title = article.get("title", "")
        link = article.get("link", "")
        source = article.get("source", "")
        published = article.get("published")
        summary = article.get("summary", "")

        date_str = ""
        if published:
            try:
                if hasattr(published, "strftime"):
                    date_str = published.strftime("%d.%m.%Y, %H:%M")
            except Exception: pass

        meta_parts = []
        if source:
            # Premium-Badge für seriöse Quellen
            is_premium = article.get("premium", False)
            badge = " ⭐" if is_premium else ""
            meta_parts.append(f"<b>{source}{badge}</b>")
        if date_str: meta_parts.append(date_str)
        meta = " · ".join(meta_parts)

        summary_html = ""
        if summary:
            display_summary = summary if len(summary) <= 180 else summary[:177] + "…"
            summary_html = (
                f"<br><span style='color:#94a3b8; font-size:0.78rem; "
                f"line-height:1.3; display:block; margin-top:2px;'>"
                f"{display_summary}</span>"
            )

        if link:
            st.markdown(
                f"<div style='padding:8px 0; border-bottom:1px solid rgba(148,163,184,0.08);'>"
                f"<a href='{link}' target='_blank' style='color:#e2e8f0; text-decoration:none; "
                f"font-size:0.9rem; font-weight:500; line-height:1.4;'>{title}</a>"
                f"{summary_html}"
                f"<br><span style='color:#64748b; font-size:0.73rem;'>{meta}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='padding:8px 0; border-bottom:1px solid rgba(148,163,184,0.08);'>"
                f"<span style='color:#e2e8f0; font-size:0.9rem; font-weight:500;'>{title}</span>"
                f"{summary_html}"
                f"<br><span style='color:#64748b; font-size:0.73rem;'>{meta}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


# Rückwärtskompatibel
_render_news_list = render_news_list
