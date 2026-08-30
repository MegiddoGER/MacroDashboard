"""
config.py — Zentrale Konfiguration aus .env bzw. Umgebungsvariablen.

Der Import dieses Moduls lädt einmalig die .env-Datei im Projektwurzelverzeichnis,
bevor irgendein os.environ-Zugriff stattfindet. Dadurch ist die Import-Reihenfolge
der übrigen Module egal: Wer eine Einstellung braucht, importiert config.

Echte Umgebungsvariablen haben Vorrang vor der .env (override=False) — wichtig
für den späteren Serverbetrieb, wo Werte per systemd/Docker gesetzt werden.

Fehlt python-dotenv, läuft die Anwendung mit den Vorgabewerten weiter; es wird
lediglich eine Warnung ausgegeben.

Alle Variablen sind in .env.example dokumentiert.
"""

import os

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")


def _load_env() -> None:
    """Lädt .env einmalig. Fehlende Datei oder fehlendes python-dotenv ist kein Fehler."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("[WARN] python-dotenv nicht installiert — .env wird ignoriert. "
              "Installation: py -m pip install python-dotenv")
        return
    if os.path.exists(_ENV_FILE):
        load_dotenv(_ENV_FILE, override=False)


_load_env()


# ---------------------------------------------------------------------------
# Lese-Helfer
# ---------------------------------------------------------------------------

def get_env(key: str, default: str = "") -> str:
    """Liest eine Umgebungsvariable. Leere/nur-Whitespace-Werte gelten als nicht gesetzt."""
    value = os.environ.get(key)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def get_env_int(key: str, default: int) -> int:
    """Wie get_env, aber als int. Unparsbare Werte fallen auf den Vorgabewert zurück."""
    raw = get_env(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[WARN] {key}='{raw}' ist keine Zahl — nutze Vorgabewert {default}.")
        return default


def get_api_token(key: str) -> str | None:
    """Liest einen API-Token: zuerst aus der DB (Settings-Seite), dann aus der Umgebung.

    Die DB hat Vorrang, damit die Eingabe im UI (/settings) einen .env-Wert
    überschreiben kann, ohne dass die Anwendung neu gestartet werden muss.

    Der database-Import erfolgt bewusst lazy: database.py importiert seinerseits
    config, ein Top-Level-Import wäre zirkulär.
    """
    try:
        from database import get_setting
        db_token = get_setting(key)
        if db_token and db_token.strip():
            return db_token.strip()
    except Exception:
        pass
    return get_env(key) or None


# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------

# Leer => database.py nutzt den Vorgabepfad data/macrodashboard.db (absolut).
DATABASE_URL = get_env("DATABASE_URL")


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

APP_HOST = get_env("APP_HOST", "127.0.0.1")
APP_PORT = get_env_int("APP_PORT", 8501)


# ---------------------------------------------------------------------------
# HTTP User-Agents
# ---------------------------------------------------------------------------

# SEC EDGAR verlangt laut Fair-Access-Policy eine erreichbare Kontaktadresse.
SEC_USER_AGENT = get_env("SEC_USER_AGENT", "MacroDashboard contact@example.com")
SCRAPER_USER_AGENT = get_env("SCRAPER_USER_AGENT", "Mozilla/5.0")
CONGRESS_USER_AGENT = get_env("CONGRESS_USER_AGENT", "MacroDashboard/1.0")


# ---------------------------------------------------------------------------
# Snapshot-Engine
# ---------------------------------------------------------------------------

SNAPSHOT_RUN_TIME = get_env("SNAPSHOT_RUN_TIME", "18:30")
