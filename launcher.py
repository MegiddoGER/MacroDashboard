"""
launcher.py — Startet das Macro Dashboard als natives Desktop-Fenster mit Tray Icon.

Nutzt Microsoft Edge (oder Chrome) im App-Modus, sodass das Dashboard
wie eine native Desktop-Anwendung aussieht (ohne Adressleiste, Tabs etc.).
Das Programm nistet sich im Windows System Tray ein und lässt sich von dort öffnen/beenden.

Verwendung:  py launcher.py
"""

import subprocess
import sys
import time
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import threading

import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
PORT = 8501
URL = f"http://127.0.0.1:{PORT}"
WINDOW_SIZE = "1400,900"


def _server_ready(url: str, timeout: float = 1.0) -> bool:
    """Prüft ob der HTTP-Server eine 200-Antwort liefert."""
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return r.status == 200
    except (urllib.error.URLError, OSError, Exception):
        return False


def _find_browser() -> str | None:
    """Sucht nach Edge oder Chrome auf dem System."""
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    for name in ("msedge", "chrome", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None

def create_icon_image():
    """Erzeugt ein simples Icon für den System Tray (blaues Viereck mit weißem M)."""
    image = Image.new('RGB', (64, 64), color=(30, 41, 59))
    dc = ImageDraw.Draw(image)
    # Simple Zentrierung
    dc.text((22, 18), "M", fill=(255, 255, 255), align="center")
    # Alternativ einfach ein farbiges Quadrat falls Schriftarten fehlen
    return image


browser_procs = []

def open_browser():
    """Öffnet das native Browser-Fenster und speichert den Prozess für späteres Aufräumen."""
    browser = _find_browser()
    if not browser:
        print(f"⚠️  Kein Edge/Chrome gefunden. Öffne manuell: {URL}")
        return

    user_data_dir = os.path.join(tempfile.gettempdir(), "macro_dashboard_browser")
    os.makedirs(user_data_dir, exist_ok=True)

    print(f"🖥️  Öffne natives Fenster mit: {os.path.basename(browser)}")
    proc = subprocess.Popen([
        browser,
        f"--app={URL}",
        f"--window-size={WINDOW_SIZE}",
        f"--user-data-dir={user_data_dir}",
        "--disable-extensions",
        "--disable-infobars",
        "--disable-features=TranslateUI",
        "--no-first-run",
        "--no-default-browser-check",
    ])
    browser_procs.append(proc)


def main():
    # 1. FastAPI/Uvicorn-Server im Hintergrund starten
    server_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", "127.0.0.1",
            "--port", str(PORT),
            "--timeout-keep-alive", "120",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    # 2. Warten bis der HTTP-Server wirklich antwortet (max 45 Sek.)
    print("⏳ Starte FastAPI-Server …")
    for i in range(90):
        if _server_ready(URL):
            break
        # Prüfen ob der Prozess abgestürzt ist
        if server_proc.poll() is not None:
            print("❌ Server-Prozess unerwartet beendet.")
            sys.exit(1)
        time.sleep(0.5)
    else:
        print("❌ Server antwortet nicht. Timeout.")
        server_proc.terminate()
        sys.exit(1)

    time.sleep(1.0)
    print(f"✅ Server bereit auf {URL}")

    # 3. Direkt das Browserfenster öffen
    open_browser()

    # 4. System Tray Icon Setup
    def on_open_clicked(icon, item):
        open_browser()

    def on_quit_clicked(icon, item):
        icon.stop()

    menu = pystray.Menu(
        item('Dashboard Öffnen', on_open_clicked, default=True),
        item('Beenden', on_quit_clicked)
    )

    icon = pystray.Icon("MacroDashboard", create_icon_image(), "Macro Dashboard", menu)

    # 5. Monitor Thread: Überwacht ob der Server stirbt
    def monitor_process():
        while True:
            if server_proc.poll() is not None:
                icon.stop()
                break
            time.sleep(1)

    threading.Thread(target=monitor_process, daemon=True).start()

    # 6. Starte Icon (Blockiert den Main-Thread bis icon.stop() gerufen wird)
    print("🔔 System Tray Icon aktiv.")
    try:
        icon.run()
    except Exception as e:
        print(f"❌ Error in icon.run(): {e}")

    # 7. Aufräumen nachdem icon.stop() gerufen wurde
    print("🛑 Beende Server …")
    if server_proc.poll() is None:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            
    # Browser-Fenster schließen
    for bproc in browser_procs:
        try:
            if bproc.poll() is None:
                bproc.kill()
        except:
            pass

    print("✅ Fertig.")


if __name__ == "__main__":
    main()
