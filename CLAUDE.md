# Regeln für Claude-Instanzen in diesem Repo

An NexHub arbeiten Claude-Instanzen von Fabio (gamunex) und Navonex. Navonex hat zwei: eine auf
dem PC und eine auf seinem Heimserver. Diese Regeln gelten für alle.

## Wer bist du?
Kürzel für Sperre, Protokoll und Commits: `claude-gamunex` (Fabio), `claude-navonex` (Navonex, PC) oder
`claude-navoserver` (Navonex, Heimserver). Jede Instanz nutzt nur ihr eigenes Kürzel, sonst hält die
Sperre sie nicht auseinander. Weißt du nicht, welche Instanz du bist, frag nach, bevor du am Server
etwas machst.

## VPS waschsalon
- Zugang: `ssh waschsalon` als root, nur mit Schlüssel. Die Adresse steht nicht im Repo, sondern
  im Eintrag `Host waschsalon` der eigenen `~/.ssh/config`. Der Anbieter hat **keine Konsole**, nur
  einen Neustart-Knopf. Wer SSH kaputt macht, sperrt alle aus.
- **Ersteinrichtung leitet claude-gamunex.** Bis Fabio oder Navonex sagen, dass sie abgeschlossen
  ist, schaut claude-navonex am Server nur nach und ändert nichts.
- **Vor jeder Änderung die Sperre holen**, danach protokollieren und freigeben:
  ```
  ssh waschsalon waschsalon-lock status
  ssh waschsalon waschsalon-lock holen claude-… "<wofür>"
  ssh waschsalon waschsalon-lock log claude-… "<was gemacht>"
  ssh waschsalon waschsalon-lock freigeben claude-…
  ```
  Ist die Sperre belegt: nichts ändern, warten oder über Fabio/Navonex nachfragen. Eine fremde
  Sperre mit `--erzwingen` lösen nur auf ausdrückliche Anweisung von Fabio oder Navonex.
- **Konfiguration gehört ins Repo.** Dateien liegen unter `infra/server/` (Pfade relativ zu `/`)
  und kommen mit `infra/deploy.sh <wer> --anwenden` auf den Server – erst committen, dann
  ausrollen. Was du von Hand am Server änderst, überschreibt beim nächsten Deploy jemand anderes.
- **SSH, Firewall, Netzwerk nur mit Rücknahme-Timer** (`systemd-run --on-active=5min …`, siehe
  `infra/deploy.sh`), Login danach in einer neuen Verbindung prüfen, erst dann den Timer stoppen.
- Nichts löschen, abschalten oder umbauen, was die andere Seite eingerichtet hat, ohne zu fragen.

## Repo
- Öffentlich, GPL-3. **Keine Geheimnisse und keine personenbezogenen Daten** in Code, Doku oder
  Commits: keine Tokens, keine privaten Mailadressen (Commits mit der GitHub-noreply-Adresse),
  keine echten Hostnamen, internen IPs oder Discord-IDs von Personen. Beispielwerte:
  `bot.example.com`, `unraid-server`, `192.168.1.10`.
- Aufbau: `nexboard/` (Touch-Leiste, Daemon, Overlay), `bot/` (TheWashBot), `hub/` (Kern + Module, auch die Log-Ansicht), `proto/`,
  `packages/nexcore` (Kern für Module, siehe dort),
  `planner/`, `infra/` (VPS). Jeder Teil hat eine eigene README mit Tests.
- Tests vor dem Push: Daemon `cd nexboard/daemon && uv run python -m pytest -q`, Radar
  `cd nexboard/radar && ../daemon/.venv/bin/python -m pytest -q tests`, Bot
  `cd bot && python -m pytest -q tests && ruff check . && mypy`, Hub `cd hub/api && uv run pytest -q` und
  `cd hub/web && npm run check`, Mitschnitt `cd nexboard/capture && ./build.sh && cargo test --release &&
  cargo clippy --release -- -D warnings && cargo fmt --check`, Formate `cd proto && uv run pytest -q`, Kern
  `cd packages/nexcore && uv run pytest -q && uv run ruff check . && uv run mypy`.
- **Ein Arbeitszweig: `main`** (seit 21.10.2026; `monorepo` ist darin aufgegangen und gelöscht).
  Laufende NexBoard-Installationen aktualisieren per `update.sh` von `main`. `modular` läuft aus:
  `update.sh` stellt Checkouts darauf von selbst auf `main` um (beim zweiten Update-Klick, der
  erste holt erst das neue Skript); gelöscht wird der Zweig, sobald keine Installation mehr darauf
  steht. Auf `main` keine Force-Pushes und keine Pfadänderungen ohne Absprache, sonst bricht das
  Update beim nächsten Klick ab oder der Daemon findet seine Dateien nicht. Hub ausrollen:
  `nexhub-update <wer> main`.
- Die Symlinks `daemon`, `capture`, `overlay` und `update.sh` an der Wurzel sind Übergänge für
  NexBoard-Checkouts aus der Zeit vor dem Monorepo (systemd-Unit, uv-Installation und Tray-Knopf
  zeigen dorthin). Nicht entfernen, solange es solche Installationen gibt.

## Code-Stil (gilt für jede Aufgabe rund um den Waschsalon)
Wunsch von Navonex und Fabio, ohne dass man es jedes Mal dazusagen muss:
- **So wenig Code wie möglich.** Erst schauen, ob es das im Repo schon gibt, und das benutzen.
  Nichts auf Vorrat bauen, keine Abstraktion für einen einzigen Fall.
- **Keine Dopplungen.** Jede Sache steht genau einmal im Code: Konstanten, Typen, Texte, Abrufe,
  Komponenten. Braucht ein zweiter Teil dasselbe, wird das Vorhandene geteilt oder erweitert, nicht
  kopiert (Beispiele: `models.Snapshot`, `characters.fill`, `CharacterProfile.svelte`).
- **Objektorientiert, wo es passt.** Was zusammengehört (Daten und das, was damit passiert), kommt
  in eine Klasse; Gemeinsames in eine Basisklasse. Einfache Hilfen bleiben Funktionen, keine
  Klassen-Hierarchien auf Vorrat.
- **Nach Coding-Standards, ohne zu übertreiben.** Python nach PEP 8 mit Typangaben, Web ohne
  Fehler und Warnungen von `npm run check`, Schreibweise wie im übrigen Code des Teils.
- **Sauber gegliedert.** Eine Datei, eine Funktion = eine Aufgabe. Kurze Funktionen, klare Namen,
  dem Aufbau folgen, der im jeweiligen Teil schon da ist.
- **Für Laien lesbar.** Lieber einfach als clever: keine verschachtelten Einzeiler, keine Tricks.
  Ein kurzer Kommentar auf Deutsch erklärt, *warum* etwas so ist, wo es nicht offensichtlich ist.
- Das gilt auch für Tests, Skripte und `infra/`.

## Neubau NexBoard: verbindliche Regeln
Gilt seit dem Neubau-Konzept (Claude Doc „NexBoard/NexHub lokal – Umbau auf kleine Module“) für jede
Zeile in NexBoard, danach für Hub und Bot. Ergänzt „Code-Stil“ und geht bei Widerspruch vor. Jede Zeile
folgt SOLID, DRY und „Lesbarkeit vor Cleverness“.

| Prinzip | Regel im Repo | Prüffrage beim Review |
|---|---|---|
| Single Responsibility | Eine Datei = eine Aufgabe, eine Klasse = ein Grund, sich zu ändern. Paket lesen, Zustand führen, Regeln auswerten, ausgeben und anzeigen sind immer getrennte Teile. | Lässt sich die Aufgabe der Datei in einem Satz ohne „und“ sagen? |
| Open/Closed | Neue Bossmechanik, neue Kachel, neues Widget, neues Modul = neue Datei oder neuer Daten-Eintrag; der Kern wird dafür nicht angefasst. Erweiterung über Registrierung, nicht über if-Ketten. | Musste für das neue Feature eine bestehende Verzweigung ergänzt werden? |
| Liskov Substitution | Alle Umsetzungen einer Schnittstelle sind austauschbar: echte Paketquelle und Aufnahme-Wiedergabe, echtes Gerät und Simulator, Piper und Piepton. Keine Sonderfälle per isinstance. | Laufen die Tests mit jeder Umsetzung unverändert? |
| Interface Segregation | Schmale Schnittstellen nach Bedarf: ein Widget sieht nur seine Daten, ein Modul nur die Dienste, die es anfordert (Ereignisse, Einstellungen, Routen), nicht den ganzen Daemon. | Bekommt der Teil Methoden, die er nie aufruft? |
| Dependency Inversion | Module hängen an Schnittstellen im Kern (typing.Protocol), nie an konkreten Klassen anderer Module. Der Kern kennt keine Module, er lädt sie über die Registrierung. Abhängigkeiten werden im Konstruktor übergeben, nicht importiert und global geholt. | Importiert ein Modul etwas aus einem anderen Modul statt aus core? |

**DRY:** Jede Fachregel, Konstante, Opcode-Nummer, Übersetzung und Formatierung steht genau einmal.
Braucht JS oder C dieselbe Zahl, wird sie aus einer gemeinsamen Quelle erzeugt (Schema oder JSON), nicht
abgeschrieben. Paketdekodierung gibt es genau einmal (eine Paketquelle für DPS, Radar und PvP). Gemeinsame
Web-Bausteine (Formularfeld, Schalter, Liste, Tabs, Abruf mit Fehleranzeige) und gemeinsame
Overlay-Bausteine (Widget-Rahmen, Ziehen, Größe) gibt es genau einmal. Grenze: Zwei Stellen, die nur
zufällig gleich aussehen, aber aus verschiedenen Gründen geändert werden, bleiben getrennt.

**Lesbarkeit vor Cleverness:** Kurze Funktionen (Richtwert unter 40 Zeilen), sprechende Namen, eine Ebene
Verschachtelung bevorzugt; frühe Rückkehr statt tiefer if-Blöcke. Keine verschachtelten Einzeiler, keine
Metaprogrammierung, keine Magie über getattr-Ketten oder dynamisch gebaute Namen. Magische Zahlen werden
benannt (`CUBE_RANGE_M = 60`), Opcodes stehen als benannte Konstanten in einer Tabelle. Ein kurzer
deutscher Kommentar erklärt das Warum, wo es nicht offensichtlich ist.

**Einheitlicher Stil über alle Sprachen:**

| Thema | Regel |
|---|---|
| Sprache der Namen | Bezeichner Englisch (Code-Standard, passt zu A2Tools, Rust, LVGL), Kommentare, Doku, Oberflächentexte Deutsch und über Übersetzungsdateien. Alte Konfig-Schlüssel werden beim Laden übersetzt. |
| Python | PEP 8, Typangaben überall, ruff + mypy --strict im Test-Lauf, Datenklassen für Daten, asyncio statt eigener Threads, außer für blockierende Hardware. |
| JavaScript | ES-Module ohne Build, JSDoc-Typen, eslint; ein Modul = eine Datei unter web/modules/<name>/. |
| Rust | cargo fmt, clippy -D warnings, Ausgabe nur über ein dokumentiertes Nachrichtenformat. |
| C (Firmware, UI) | Präfix je Teil (ui_tile_, net_), clang-format, Hardware nur über hal.h. |
| Konfiguration | Eine Ablage ~/.config/deckbar/, eine Datei je Modul, Schema je Modul; ~/.config/aion2-radar.json geht darin auf. |
| Logging | Ein Logger je Modul (logging.getLogger("nexboard.<modul>")), keine print. |
| Tests | Jedes Modul bringt eigene Tests mit; Fachlogik ohne Netz, Gerät oder Spiel testbar (aufgezeichnete Pakete als Eingabe). |

**Entscheidungen (09.11.2026, Fabio und Navonex):** Monorepo mit `packages/` (nexcore, nexproto) und
`apps/` als uv-Workspace; Radar nur noch für Gruppe und eigenes Ziel, keine Namen Fremder (0x3645 wird
nicht gelesen); nur das A2Tools-Meter als Widget; Vertraute-Tabelle fällt weg (Verweis auf den Pet Soul
Tracker); Runs nach Discord nur Daemon → Hub → Bot, das Webhook-Bild bleibt als Option.

**Arbeitsregeln für den Umbau:** Jeder Schritt ist ein PR nach main mit grünen Tests (auch Goldtest und
Referenzbilder, siehe `nexboard/README.md`, „Tests“); Pfadänderungen nur mit Weiterleitung in update.sh,
die Wurzel-Symlinks bleiben, solange alte Installationen existieren. Den Daemon nie neu starten, solange
AION 2 läuft (Ziel: update.sh merkt den Neustart dann nur vor). Testinstanzen nie mit echtem systemd oder echtem Mitschnitt. Jede Fachregel, die
beim Umbau berührt wird, wandert in Daten oder nexproto. Pro Modul ein Review gegen die Prüffragen oben.
