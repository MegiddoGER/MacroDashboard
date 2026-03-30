"""
services/economic_calendar.py — Wirtschaftskalender für das MacroDashboard.

Zeigt kommende Makro-Events (FOMC, EZB, CPI, NFP, GDP, ISM, PCE, ifo)
mit Impact-Rating, Countdown und länderspezifischer Filterung.

Datenquelle: data/economic_events.json (jährlich aktualisieren)
"""

import json
import os
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class EconomicEvent:
    """Ein einzelnes Wirtschafts-Event."""
    id: str                       # z.B. "fomc", "us_cpi"
    name: str                     # Deutscher Name
    name_en: str                  # Englischer Name
    category: str                 # central_bank, inflation, employment, growth
    country: str                  # US, EU, DE
    impact: str                   # high, medium, low
    description: str              # Kurze Erklärung
    date: datetime                # Termin
    time_cet: str | None = None   # Uhrzeit in CET (z.B. "14:30")
    # Countdown-Felder (werden dynamisch gesetzt)
    days_until: int = 0
    countdown_label: str = ""
    is_today: bool = False
    is_past: bool = False


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

CATEGORY_ICONS = {
    "central_bank": "🏦",
    "inflation": "📊",
    "employment": "💼",
    "growth": "📈",
    "other": "📋",
}

COUNTRY_FLAGS = {
    "US": "🇺🇸",
    "EU": "🇪🇺",
    "DE": "🇩🇪",
}

IMPACT_COLORS = {
    "high": "#ef4444",      # Rot
    "medium": "#f59e0b",    # Orange
    "low": "#22c55e",       # Grün
}

IMPACT_BADGES = {
    "high": "🔴 High Impact",
    "medium": "🟠 Medium Impact",
    "low": "🟢 Low Impact",
}


# ---------------------------------------------------------------------------
# Events laden
# ---------------------------------------------------------------------------

def _load_events_db() -> dict:
    """Lädt die Event-Datenbank aus data/economic_events.json."""
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "economic_events.json"
    )
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        warnings.warn(f"economic_events.json nicht gefunden: {json_path}")
        return {"events": []}
    except json.JSONDecodeError as e:
        warnings.warn(f"Fehler beim Parsen von economic_events.json: {e}")
        return {"events": []}


def _parse_all_events() -> list[EconomicEvent]:
    """Parst alle Events aus der JSON-Datenbank zu EconomicEvent-Objekten."""
    db = _load_events_db()
    all_events = []

    for event_def in db.get("events", []):
        event_id = event_def.get("id", "unknown")
        name = event_def.get("name", event_id)
        name_en = event_def.get("name_en", name)
        category = event_def.get("category", "other")
        country = event_def.get("country", "US")
        impact = event_def.get("impact", "medium")
        description = event_def.get("description", "")
        time_cet = event_def.get("time_cet")

        for date_str in event_def.get("dates", []):
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
                all_events.append(EconomicEvent(
                    id=event_id,
                    name=name,
                    name_en=name_en,
                    category=category,
                    country=country,
                    impact=impact,
                    description=description,
                    date=date,
                    time_cet=time_cet,
                ))
            except ValueError:
                warnings.warn(f"Ungültiges Datum '{date_str}' für Event '{event_id}'")

    return all_events


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def get_upcoming_events(days: int = 14,
                        country: str | None = None,
                        impact: str | None = None,
                        category: str | None = None,
                        include_today: bool = True) -> list[EconomicEvent]:
    """Gibt anstehende Events im Zeitfenster zurück.

    Args:
        days: Anzahl Tage in die Zukunft (default 14)
        country: Optional. Filter nach Land ("US", "EU", "DE")
        impact: Optional. Filter nach Impact ("high", "medium", "low")
        category: Optional. Filter nach Kategorie
        include_today: Ob heutige Events enthalten sein sollen

    Returns:
        Liste von EconomicEvent, sortiert nach Datum (nächste zuerst)
    """
    all_events = _parse_all_events()
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now + timedelta(days=days)

    results = []
    for event in all_events:
        event_date = event.date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Zeitfenster prüfen
        if include_today:
            if event_date < now or event_date > end_date:
                continue
        else:
            if event_date <= now or event_date > end_date:
                continue

        # Filter anwenden
        if country and event.country != country:
            continue
        if impact and event.impact != impact:
            continue
        if category and event.category != category:
            continue

        # Countdown berechnen
        delta = (event_date - now).days
        event.days_until = delta
        event.is_today = (delta == 0)
        event.is_past = (delta < 0)

        if delta == 0:
            time_str = f" um {event.time_cet}" if event.time_cet else ""
            event.countdown_label = f"🔴 HEUTE{time_str}"
        elif delta == 1:
            event.countdown_label = "⚡ MORGEN"
        elif delta <= 3:
            event.countdown_label = f"⏰ in {delta} Tagen"
        elif delta <= 7:
            event.countdown_label = f"📅 in {delta} Tagen"
        else:
            event.countdown_label = f"in {delta} Tagen"

        results.append(event)

    # Sortieren: nächste Events zuerst
    results.sort(key=lambda e: e.date)
    return results


def get_events_for_ticker(ticker: str, days: int = 7) -> list[EconomicEvent]:
    """Gibt für einen Ticker relevante High-Impact Events zurück.

    Bestimmt das Land des Tickers und zeigt passende Makro-Events.
    Immer inklusive US-Events (da US-Makro global relevant).

    Args:
        ticker: Aktien-Symbol (z.B. "AAPL", "SAP.DE")
        days: Tage in die Zukunft

    Returns:
        High-Impact Events der nächsten N Tage, relevant für diesen Ticker
    """
    # Land bestimmen
    is_german = ticker.endswith(".DE")
    is_european = ticker.endswith((".DE", ".PA", ".AS", ".MI", ".MC"))

    # US-Events immer zeigen (globaler Impact)
    relevant_countries = {"US"}
    if is_german:
        relevant_countries.add("DE")
        relevant_countries.add("EU")
    elif is_european:
        relevant_countries.add("EU")

    all_upcoming = get_upcoming_events(days=days, impact="high")

    # Auch Medium-Impact Events für das eigene Land
    medium_events = get_upcoming_events(days=days, impact="medium")

    results = []
    for event in all_upcoming:
        if event.country in relevant_countries:
            results.append(event)

    # Medium-Impact nur für das eigene Land
    for event in medium_events:
        if is_german and event.country == "DE":
            results.append(event)
        elif is_european and event.country == "EU":
            results.append(event)

    # Deduplizieren (gleicher ID + gleiches Datum)
    seen = set()
    unique = []
    for event in results:
        key = (event.id, event.date.strftime("%Y-%m-%d"))
        if key not in seen:
            seen.add(key)
            unique.append(event)

    unique.sort(key=lambda e: e.date)
    return unique


def get_event_categories() -> list[dict]:
    """Gibt alle Event-Kategorien mit Icons zurück."""
    return [
        {"id": "central_bank", "name": "Zentralbanken", "icon": "🏦"},
        {"id": "inflation", "name": "Inflation", "icon": "📊"},
        {"id": "employment", "name": "Arbeitsmarkt", "icon": "💼"},
        {"id": "growth", "name": "Wachstum", "icon": "📈"},
    ]


def get_calendar_summary() -> dict:
    """Gibt eine Zusammenfassung der nächsten Events zurück.

    Returns:
        Dict mit counts pro Impact-Level und nächstes Event.
    """
    upcoming = get_upcoming_events(days=14)

    high_events = [e for e in upcoming if e.impact == "high"]
    medium_events = [e for e in upcoming if e.impact == "medium"]

    next_event = upcoming[0] if upcoming else None
    next_high = high_events[0] if high_events else None

    return {
        "total": len(upcoming),
        "high_count": len(high_events),
        "medium_count": len(medium_events),
        "next_event": next_event,
        "next_high_event": next_high,
    }


# ---------------------------------------------------------------------------
# Hilfsfunktionen für UI
# ---------------------------------------------------------------------------

def get_impact_color(impact: str) -> str:
    """Gibt die Farbe für ein Impact-Level zurück."""
    return IMPACT_COLORS.get(impact, "#94a3b8")


def get_country_flag(country: str) -> str:
    """Gibt das Flaggen-Emoji für ein Land zurück."""
    return COUNTRY_FLAGS.get(country, "🌍")


def get_category_icon(category: str) -> str:
    """Gibt das Icon für eine Kategorie zurück."""
    return CATEGORY_ICONS.get(category, "📋")
