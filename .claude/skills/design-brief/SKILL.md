---
name: design-brief
description: Visuelles Design-Briefing für das MacroDashboard — Tokens, Komponenten, Motion-System und harte Randbedingungen (kein Build-Schritt, HTMX, Plotly-Dark). Verwenden beim Überarbeiten von static/css/* oder Jinja2-Templates und beim Ausführen des ui-designer-Agenten.
---

# Design-Brief: Visuelle Überarbeitung des MacroDashboards

> Auftrag an den `ui-designer`-Subagenten. Dieser Brief ist als Skill hinterlegt und
> wird mit `/design-brief` geladen; der Skill-Ordner ist
> `.claude/skills/design-brief/`.

## Das Produkt

MacroDashboard ist ein selbst gehostetes Trading-/Investment-Terminal, das sein
Besitzer als **sein eigenes, besseres, persönliches Bloomberg-Terminal** baut.
Dieser Anspruch ist der Maßstab: Es soll wie ein professionelles Instrument
wirken, nicht wie ein Hobbyprojekt. Umfang: Portfolio-Tracking, Screener,
Einzelaktien-Tiefenanalyse (technisch + fundamental + Smart Money Concepts),
Backtesting, Trade-Journal und eine Signal-Qualitäts-Engine, die misst, ob die
eigenen Empfehlungen tatsächlich eintreffen.

Solo-Entwickler, alleiniger Nutzer. Kommentare und Commits auf Deutsch —
**diese Konvention beibehalten**.

## Was den Besitzer stört (eigene Worte)

> "Looks amateurish / not professional enough — it doesnt look clean and uses no
> animations. also missing on fluent positioning and design"

Daraus abgeleitet:
1. **Sauberkeit** — wirkt zusammengesetzt statt gestaltet
2. **Bewegung** — es gibt praktisch keine Animation; gezielte, zurückhaltende Motion einführen
3. **"Fluent positioning"** — flüssigere Anordnung und räumlicher Rhythmus
4. **Professionelle Glaubwürdigkeit** — der Bloomberg-Maßstab

**Abgestimmter Umfang: Token- und Komponenten-Refresh über das gesamte Dashboard.**
Dunkle Terminal-Richtung und bestehende Seitenstruktur bleiben — es ist eine
Verfeinerung eines funktionierenden Systems, keine neue Identität, kein Umbau.

## Technik und harte Randbedingungen (Verstoß bricht die App)

- **FastAPI + Jinja2 + HTMX 2.0.4.** Kein React/Vue, kein JS-Framework.
- **Kein Build-Schritt.** Kein Bundler, kein Sass/PostCSS/Tailwind. CSS wird von
  Hand geschrieben und statisch aus `static/css/` ausgeliefert. Alles, was
  Kompilierung braucht, ist unbrauchbar.
- **Keine neuen externen Abhängigkeiten oder CDN-Einbindungen.** Inter ist bereits
  in `tokens.css` eingebunden; nichts Weiteres hinzufügen.
- **Bestehende CSS-Klassennamen nicht umbenennen oder entfernen**, ohne jedes
  betroffene Template mitzuziehen. Templates referenzieren u.a. `.card`, `.btn`,
  `.badge`, `.data-table`, `.table-wrapper`, `.caption`, `.muted`, `.positive`,
  `.negative`, `.nav-section`, `.page-header`, `.alert`, `.form-label`.
  Vor jedem Umbenennen greppen.
- **HTMX tauscht DOM-Fragmente** (`hx-get`/`hx-post` mit `hx-swap`). Eintritts-
  Animationen müssen auch für nachträglich eingefügten Inhalt greifen, nicht nur
  beim ersten Laden. Das vorhandene `.htmx-indicator`-Muster verbessern, nicht brechen.
- **Plotly-Charts** werden clientseitig mit `template="plotly_dark"` gerendert.
  Die Palette muss dazu passen.
- **Barrierefreiheit**: Jede Animation braucht einen
  `@media (prefers-reduced-motion: reduce)`-Ausweg. Kontrast wahren — dies ist
  eine dichte Daten-Oberfläche, Lesbarkeit schlägt Dekoration.
- **Performance**: `transform` und `opacity` animieren. Keine Layout-auslösenden
  Eigenschaften (width/height/top/left) in Listen und Tabellen mit hunderten Zeilen.

## Ausgangslage

`static/css/` — Ladereihenfolge laut `base.html` ist bedeutsam:
`tokens.css → layout.css → components.css → topnav.css → motion.css`

- `tokens.css` — Tokens als CSS Custom Properties: dunkles Navy/Slate
  (`#0a0f1a` → `#111827`), Akzent-Türkis `#00d4aa`, Statusfarben, Inter
- `layout.css` — App-Shell
- `components.css` — Cards, Tabellen, Buttons, Badges, Formulare, Alerts
- `topnav.css` — obere Navigationsleiste (`partials/topnav.html`); die frühere
  linke `sidebar.css` existiert nicht mehr
- `motion.css` — Motion-Ebene

Templates: `templates/base.html`, 17 Seiten in `templates/pages/`, Fragmente
in `templates/partials/`.

**Bekannte Altlast, die mit aufgeräumt werden soll:** Die drei neuesten Seiten —
`pages/signal_quality.html`, `pages/signal_indikatoren.html`,
`pages/signal_backfill.html` und `partials/signal_backfill_status.html` — nutzen
stark Inline-`style="..."` (Flex-Zeilen, Grids, Abstände) statt gemeinsamer
Klassen und fallen sichtbar aus dem Rahmen. Diese Muster in wiederverwendbare
Komponenten zu überführen ist ausdrücklich Teil des Auftrags und zeigt gut,
welche Komponenten bislang fehlen.

## Auftrag

1. **Erst sichten.** Die vier CSS-Dateien und eine repräsentative Auswahl an
   Templates lesen (`base.html`, `partials/topnav.html`, `pages/home.html`,
   `pages/screener.html`, `pages/signal_quality.html`,
   `partials/analysis_content.html`), bevor etwas geändert wird.
2. **Token-Ebene erneuern** — stimmige typografische Skala, konsistenter
   Abstandsrhythmus, Elevation/Tiefe, verfeinerte Ränder und Flächen sowie
   Motion-Tokens (Dauern, Easing). Die Token-Ebene hat die größte Hebelwirkung.
3. **Gemeinsame Komponenten überarbeiten** — Cards, **Tabellen** (besonders
   wichtig: die App besteht überwiegend aus dichten Zahlentabellen), Buttons,
   Badges, Formularelemente, Alerts, Sidebar, Page-Header-Muster.
4. **Zurückhaltendes Motion-System** — Hover/Focus-Feedback, HTMX-Eintritt,
   Sidebar-Interaktion, Ladezustände, Tabellenzeilen. Zweckgebunden und schnell
   (ca. 120–250 ms). Hier werden den ganzen Tag Zahlen gelesen: Bewegung soll
   präzise und souverän wirken, nie verspielt oder träge. Nichts darf das Ablesen
   einer Zahl verzögern.
5. **Layout-Rhythmus korrigieren** ("fluent positioning") — konsistente vertikale
   Abstände, Ausrichtung, Containerbreiten, responsives Verhalten.
6. **Inline-Style-Altlast** der Signal-Seiten in gemeinsame Klassen überführen.

## Verifikation (Pflicht)

Nach den Änderungen muss geprüft werden, dass die App weiterhin rendert:

```
py -c "import warnings; warnings.filterwarnings('ignore'); from fastapi.testclient import TestClient; import main; c=TestClient(main.app); c.__enter__(); [print(c.get(u).status_code, u) for u in ['/','/signals','/signals/indikatoren','/analysis','/screener','/watchlist','/journal','/backtesting','/sectors','/economy','/settings','/lexicon','/sources','/directory']]"
```

Jede Route muss 200 liefern. Zusätzlich `py -m pytest -q` (15 Tests). Bricht eine
Seite, vor Abschluss reparieren — kein kaputtes Dashboard zurückgeben.

Hinweis: Die App läuft eventuell bereits auf Port 8501, die SQLite-DB ist ~279 MB.
Beides ist normal. **Nicht anfassen:** Datenbank sowie alle Python-Dateien unter
`services/`, `routers/`, `snapshot_engine/` und jegliche Geschäftslogik.
**Zuständigkeitsbereich: `static/css/*` und, soweit für Markup/Klassen nötig, die
Jinja2-Templates.**

## Rückmeldung

Konkret zusammenfassen: geänderte Dateien, neues Token-System (Skala, Palette,
Motion-Tokens), überarbeitete Komponenten, eingeführte Bewegung und wo, Umgang mit
`prefers-reduced-motion` und Kontrast, Ergebnis der Verifikation. Bewusst
Ausgelassenes mit Begründung nennen sowie Risiken, die nachgeprüft werden sollten.
