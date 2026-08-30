"""
services/sector_map.py — Kanonische Sektor-Bezeichnungen.

Im Projekt treffen zwei unterschiedliche Sektor-Nomenklaturen aufeinander:

  * yfinance (`info["sector"]`)      → "Healthcare", "Financial Services",
                                        "Consumer Cyclical", "Basic Materials"
  * GICS aus der S&P-500-Liste       → "Health Care", "Financials",
    (`GICS Sector` in market_data)     "Consumer Discretionary", "Materials"

Beide beschreiben dieselben Sektoren mit verschiedenen Zeichenketten. Wer
direkt gegen einen der beiden Schreibweisen vergleicht, trifft für die andere
Quelle nie — und zwar lautlos, weil ein nicht getroffener elif-Zweig einfach
in den Default fällt.

Genau das war der Fall: `calc_dcf_valuation` prüfte auf "health care",
yfinance liefert aber "Healthcare". Jede Gesundheits-/Pharma-Aktie bekam
dadurch stillschweigend die Default-Terminal-Growth-Rate statt der für den
Sektor vorgesehenen.

Deshalb: alle Sektor-Vergleiche laufen über `normalize_sector()`.

Die kanonischen Werte sind bewusst kleingeschrieben und mit Leerzeichen
(nicht Unterstrichen) gebildet, damit bestehende Teilstring-Prüfungen wie
`"consumer cyclical" in sector` oder `"financial" in sector` weiterhin
greifen.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Kanonische Sektoren
# ---------------------------------------------------------------------------

TECHNOLOGY = "technology"
HEALTHCARE = "healthcare"
FINANCIALS = "financial services"
ENERGY = "energy"
UTILITIES = "utilities"
REAL_ESTATE = "real estate"
COMMUNICATION = "communication services"
INDUSTRIALS = "industrials"
CONSUMER_CYCLICAL = "consumer cyclical"
CONSUMER_DEFENSIVE = "consumer defensive"
MATERIALS = "basic materials"
UNBEKANNT = ""

KANONISCHE_SEKTOREN: tuple[str, ...] = (
    TECHNOLOGY, HEALTHCARE, FINANCIALS, ENERGY, UTILITIES, REAL_ESTATE,
    COMMUNICATION, INDUSTRIALS, CONSUMER_CYCLICAL, CONSUMER_DEFENSIVE,
    MATERIALS,
)


# Schreibweisen beider Quellen auf den kanonischen Wert abbilden.
# Schlüssel sind bereits normalisiert (klein, Mehrfach-Leerzeichen entfernt).
_ALIASE: dict[str, str] = {
    # ── Technologie ────────────────────────────────────────────────
    "technology": TECHNOLOGY,
    "information technology": TECHNOLOGY,          # GICS
    "tech": TECHNOLOGY,
    "software": TECHNOLOGY,

    # ── Gesundheit ─────────────────────────────────────────────────
    "healthcare": HEALTHCARE,                      # yfinance
    "health care": HEALTHCARE,                     # GICS
    "health": HEALTHCARE,
    "pharmaceuticals": HEALTHCARE,
    "biotechnology": HEALTHCARE,

    # ── Finanzen ───────────────────────────────────────────────────
    "financial services": FINANCIALS,              # yfinance
    "financials": FINANCIALS,                      # GICS
    "financial": FINANCIALS,
    "finance": FINANCIALS,
    "banks": FINANCIALS,
    "insurance": FINANCIALS,

    # ── Energie ────────────────────────────────────────────────────
    "energy": ENERGY,
    "oil & gas": ENERGY,
    "oil and gas": ENERGY,

    # ── Versorger ──────────────────────────────────────────────────
    "utilities": UTILITIES,

    # ── Immobilien ─────────────────────────────────────────────────
    "real estate": REAL_ESTATE,
    "realestate": REAL_ESTATE,

    # ── Kommunikation ──────────────────────────────────────────────
    "communication services": COMMUNICATION,
    "communications": COMMUNICATION,
    "telecommunication services": COMMUNICATION,
    "telecom": COMMUNICATION,

    # ── Industrie ──────────────────────────────────────────────────
    "industrials": INDUSTRIALS,
    "industrial": INDUSTRIALS,
    "industry": INDUSTRIALS,

    # ── Zyklischer Konsum ──────────────────────────────────────────
    "consumer cyclical": CONSUMER_CYCLICAL,        # yfinance
    "consumer discretionary": CONSUMER_CYCLICAL,   # GICS
    "consumer cyclicals": CONSUMER_CYCLICAL,

    # ── Defensiver Konsum ──────────────────────────────────────────
    "consumer defensive": CONSUMER_DEFENSIVE,      # yfinance
    "consumer staples": CONSUMER_DEFENSIVE,        # GICS
    "consumer goods": CONSUMER_DEFENSIVE,

    # ── Rohstoffe ──────────────────────────────────────────────────
    "basic materials": MATERIALS,                  # yfinance
    "materials": MATERIALS,                        # GICS
    "basic material": MATERIALS,
}


def normalize_sector(raw: str | None) -> str:
    """Bildet eine beliebige Sektor-Schreibweise auf den kanonischen Wert ab.

    Unbekannte oder fehlende Sektoren ergeben `UNBEKANNT` (Leerstring) —
    Aufrufer behandeln das wie "kein Sektor bekannt" und fallen auf ihren
    Default zurück.

    >>> normalize_sector("Healthcare")
    'healthcare'
    >>> normalize_sector("Health Care")
    'healthcare'
    >>> normalize_sector(None)
    ''
    """
    if not raw:
        return UNBEKANNT

    schluessel = " ".join(str(raw).lower().split())
    if not schluessel:
        return UNBEKANNT

    treffer = _ALIASE.get(schluessel)
    if treffer:
        return treffer

    # Zweiter Versuch: Teilstring-Suche für zusammengesetzte Angaben
    # ("Technology Hardware", "Regional Banks — Financial Services").
    for alias, kanonisch in _ALIASE.items():
        if alias in schluessel:
            return kanonisch

    return UNBEKANNT


def ist_sektor(raw: str | None, kanonisch: str) -> bool:
    """Prüft, ob `raw` dem kanonischen Sektor entspricht — quellenunabhängig."""
    return normalize_sector(raw) == kanonisch
