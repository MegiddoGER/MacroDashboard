"""
services/congress_mapping.py — Committee Mapping für Kongress-Trades.

Beinhaltet Dictionaries zur Zuordnung von Politikern zu ihren Ausschüssen
und Sektoren zu relevanten Ausschüssen, um potenzielle Interessenkonflikte
("Conflicts of Interest") zu erkennen.
"""

# ---------------------------------------------------------------------------
# Zuordnung von prominenten US-Politikern zu ihren primären Ausschüssen
# (Fokus auf Ausschüsse mit starkem Markteinfluss)
# ---------------------------------------------------------------------------

POLITICIAN_COMMITTEES: dict[str, list[str]] = {
    # === HOUSE ===
    "Nancy Pelosi": ["Financial Services", "Rules"],
    "Ro Khanna": ["Armed Services", "Agriculture", "Oversight"],
    "Dan Crenshaw": ["Energy and Commerce", "Intelligence"],
    "Mark Green": ["Homeland Security", "Foreign Affairs", "Armed Services"],
    "Josh Gottheimer": ["Financial Services", "Intelligence"],
    "Michael McCaul": ["Foreign Affairs", "Homeland Security"],
    "Debbie Wasserman Schultz": ["Appropriations", "Oversight"],
    "Virginia Foxx": ["Education and Workforce", "Oversight"],
    "Kevin Hern": ["Ways and Means", "Budget"],
    "French Hill": ["Financial Services", "Intelligence"],
    "Pat Fallon": ["Armed Services", "Oversight"],
    "Michael Guest": ["Ethics", "Homeland Security"],
    "John Curtis": ["Energy and Commerce", "Natural Resources"],
    "Daniel Goldman": ["Homeland Security", "Oversight"],
    "Marie Gluesenkamp Perez": ["Agriculture", "Transportation"],
    "Marjorie Taylor Greene": ["Homeland Security", "Oversight"],
    "Anna Paulina Luna": ["Oversight", "Natural Resources"],

    # === SENATE ===
    "Tommy Tuberville": ["Armed Services", "Agriculture", "Veterans Affairs"],
    "Mitch McConnell": ["Rules", "Agriculture", "Appropriations"],
    "Chuck Schumer": ["Rules", "Intelligence"],
    "Ron Wyden": ["Finance", "Budget", "Intelligence"],
    "Elizabeth Warren": ["Banking", "Armed Services", "Finance"],
    "Bob Menendez": ["Foreign Relations", "Finance", "Banking"],
    "Sheldon Whitehouse": ["Finance", "Budget", "Environment"],
    "Rick Scott": ["Armed Services", "Budget", "Homeland Security"],
    "Markwayne Mullin": ["Armed Services", "Environment", "Intelligence"],
    "John Hickenlooper": ["Energy and Commerce", "Commerce"],
    "Pete Ricketts": ["Armed Services", "Foreign Relations", "Budget"],
    "Cynthia Lummis": ["Banking", "Commerce", "Environment"],
    "Bill Hagerty": ["Banking", "Foreign Relations", "Appropriations"],
    "Mark Kelly": ["Armed Services", "Commerce", "Intelligence"],
    "Gary Peters": ["Armed Services", "Commerce", "Homeland Security"],
    "Susan Collins": ["Appropriations", "Intelligence"],
    "John Hoeven": ["Agriculture", "Appropriations", "Energy"],
}


# ---------------------------------------------------------------------------
# Zuordnung von yfinance-Sektoren zu den relevanten US-Ausschüssen
# ---------------------------------------------------------------------------

SECTOR_COMMITTEES: dict[str, list[str]] = {
    "Technology": ["Intelligence", "Energy and Commerce", "Oversight", "Commerce"],
    "Financial Services": ["Financial Services", "Banking", "Finance", "Budget"],
    "Healthcare": ["Energy and Commerce", "Finance", "Veterans Affairs"],
    "Industrials": ["Armed Services", "Appropriations", "Transportation"],
    "Energy": ["Energy and Commerce", "Environment", "Agriculture", "Energy"],
    "Basic Materials": ["Energy and Commerce", "Agriculture", "Environment", "Natural Resources"],
    "Consumer Cyclical": ["Energy and Commerce", "Commerce"],
    "Consumer Defensive": ["Agriculture", "Energy and Commerce"],
    "Communication Services": ["Energy and Commerce", "Intelligence", "Commerce"],
    "Utilities": ["Energy and Commerce", "Environment"],
    "Real Estate": ["Financial Services", "Banking"],
}


def check_conflict_of_interest(politician_name: str, sector: str | None) -> tuple[bool, str | None]:
    """
    Prüft, ob der Politiker in einem Ausschuss sitzt, der für den
    angegebenen Sektor relevant ist.

    Args:
        politician_name: Name des Politikers (z.B. "Nancy Pelosi")
        sector: yfinance Sektor (z.B. "Technology", "Financial Services")

    Returns:
        Tuple (is_conflict: bool, matched_committee: str | None)
    """
    if not politician_name or not sector:
        return False, None

    # Flexible Namensprüfung (Nachname-Match, da API manchmal
    # Schreibweisen variiert, z.B. "Hon. Nancy Pelosi")
    committees_for_politician: list[str] = []
    for pol_name, committees in POLITICIAN_COMMITTEES.items():
        # Prüfe ob der Nachname im API-Namen vorkommt
        last_name = pol_name.split()[-1].lower()
        if last_name in politician_name.lower():
            committees_for_politician = committees
            break

    if not committees_for_politician:
        return False, None

    relevant_committees_for_sector = SECTOR_COMMITTEES.get(sector, [])
    if not relevant_committees_for_sector:
        return False, None

    # Check auf Überschneidungen
    for committee in committees_for_politician:
        if committee in relevant_committees_for_sector:
            return True, committee

    return False, None
