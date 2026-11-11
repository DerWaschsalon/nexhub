# NexBoard

*Früher DeckBar. Technische Namen (Ordner, Dienste `deckbar*.service`, `~/.config/deckbar`,
mDNS `_deckbar._tcp`, Programme `deckbar-*`, Repo) bleiben vorerst gleich, damit bestehende Geräte
und Installationen weiterlaufen.*

Eine Touch-Leiste unter dem Monitor im Stil eines Stream Deck, gebaut auf dem Waveshare
**ESP32-S3-Touch-LCD-3.49** (640 × 172 im Querformat, Board V1 und V2). Die Optik ist im
„Liquid Glass“-Stil gehalten.

- **Kacheln:** Taste, Schalter und Schieberegler für Audio (Lautstärke, Mute von Ausgang und
  Mikrofon), Media-Steuerung mit Cover und Titel, Links, Hotkeys und Shell-Befehle
- **Claude-Nutzung:** Auslastung des Claude-Abos (5-Stunden-Sitzung und Woche) wie `/usage` in
  Claude Code. Der Daemon liest dafür die Anmeldung von Claude Code (`~/.claude/.credentials.json`)
  und fragt alle 5 Minuten nach, solange die Kachel im Layout ist. Der Endpunkt ist nicht
  offiziell dokumentiert; ändert er sich, zeigt die Kachel „–“.
- **Live-Status:** Mute, Lautstärke und Track folgen dem PC, auch wenn dort umgeschaltet wird.
  Eigene Werte kommen per `POST /api/state` dazu.
- **Mehrere Seiten** mit Wischgesten, Hintergrund wählbar (Standard, Desktop-Hintergrund, eigenes Bild)
- **AION 2:** DPS-Meter der Gruppe als eigene Seite, ein Overlay über dem Spiel (Meter, Boss-Leiste,
  Termine, Namenseffekt) und nach jedem Dungeon-Run ein Bild mit dem Schaden pro Boss nach Discord
- **AION-2-Radar:** Hidden Cubes, Karte und Boss-Warnungen als Widgets im Overlay, Feldbosse unter
  Termine in der Web-UI (`radar/`), läuft im Daemon mit dem Spiel, alle Einstellungen in der Web-UI
- **Runs in Discord:** über den NexHub an TheWashBot, der Meldungen mehrerer Spieler zu einem Post zusammenführt
- **Verbindung** per WLAN, bei Bedarf per USB-Kabel als Rückfall
- **Ruhemodus:** Ist 30 s lang kein PC verbunden (weder WLAN noch USB), blendet das Display aus und
  geht wieder an, sobald der Daemon da ist. Eine Berührung zeigt kurz den Verbindungsstatus
  (`DECKBAR_SLEEP_AFTER_S`, `DECKBAR_SLEEP_PEEK_S` in `firmware/include/deckbar_config.h`)
- **Web-UI** mit Dashboard und einer Seite je Modul, Leisten-Editor mit Drag & Drop und
  Live-Vorschau, dazu ein SDL-Simulator zum Testen ohne Gerät
- **Modular:** Jeder Teil (Touch-Leiste, AION-2-Mitschnitt, Overlay, Runs, Radar, NexHub, Updates)
  lässt sich in der Web-UI einzeln ein- und ausschalten, ohne Neustart

```
┌──────────────┐  WebSocket (JSON, v1)  ┌───────────────────────────────┐
│ Gerät / Sim  │ ◄────────────────────► │ deckbar-daemon (Python)       │
│ shared-ui    │   layout, state  →     │  wpctl · pactl subscribe      │
│ (LVGL 9.3)   │   ← event              │  playerctl --follow           │
└──────────────┘   WLAN oder USB        │  xdg-open · ydotool · shell   │
                                        │  Web-UI  http://localhost:8765│
                                        └───────────────────────────────┘
```

Die Firmware hält keine eigene Logik. Das Gerät rendert, was der Daemon schickt, und meldet nur
zurück, welche Kachel angetippt wurde. Welche Aktion dahinter steckt, weiß allein der Daemon.

| Ordner       | Inhalt |
|--------------|--------|
| `docs/`      | [Protokoll](docs/protocol.md), [JSON-Schema](docs/protocol.schema.json), [Icon-Liste](docs/icons.md) |
| `shared-ui/` | LVGL-UI-Code (C). Läuft unverändert in Firmware **und** Simulator, Hardware nur über `include/deckbar/hal.h` |
| `simulator/` | SDL2-Fenster 640 × 172, RGB565, Maus = Touch, echter WebSocket zum Daemon |
| `daemon/`    | Python-Daemon inkl. Web-Konfiguration, USB-Brücke, systemd-User-Service |
| `capture/`   | `deckbar-capture` (Rust): AION-2-Mitschnitt mit dem Kern des A2Tools DPS Meter (Submodul `capture/a2tools`) |
| `overlay/`   | `deckbar-overlay` (PySide6/QML): Overlay über dem Spiel als layer-shell-Fläche (Meter, Widgets), Tray und Tastenkürzel |
| `firmware/`  | PlatformIO / Arduino-ESP32 3.3.12, Umgebungen für Board V2 und V1 |
| `tools/`     | `gen_assets.py`: Schriften, Icons, Hintergrundbild erzeugen |

## Einrichtung (CachyOS / Arch, KDE Plasma)

### Pakete

```sh
sudo pacman -S --needed sdl2 playerctl ydotool wireplumber libpulse uv
uv tool install cmake && uv tool install ninja     # nur für den Simulator (oder: pacman -S cmake ninja)
uv tool install platformio                         # nur für die Firmware
sudo pacman -S --needed rust libpcap               # nur für den AION-2-Mitschnitt
systemctl --user enable --now ydotool              # ydotoold für Hotkeys
```

`libpulse` bringt `pactl` mit. Der Daemon nutzt es nur für `pactl subscribe`, also
ereignisbasierte Updates statt Polling. Fehlt ein Werkzeug, läuft der Rest trotzdem, und die
Web-UI zeigt an, was fehlt.

### Daemon

```sh
cd daemon
uv sync
uv run deckbar-daemon          # -v für Debug-Ausgaben, --open öffnet die Web-UI
```

Beim ersten Start legt der Daemon in `~/.config/deckbar/` zwei Dateien an:

- `config.yaml`: Port, **Token** (zufällig erzeugt), Name, bevorzugter Player, USB-Rückfall
- `layout.yaml`: Seiten und Kacheln mit Aktionen, kommentiertes Beispiel
- `modules.yaml`: welche Module eingeschaltet sind (frische Installation: Touch-Leiste und Updates)

Beide Dateien liegen außerhalb des Repos. Handänderungen an `layout.yaml` übernimmt der Daemon
live (Prüfung einmal pro Sekunde). Ist die Datei ungültig, bleibt das alte Layout aktiv, und die
Web-UI zeigt den Fehler an.

### Autostart als systemd-User-Service

```sh
uv tool install --editable ./daemon                 # legt ~/.local/bin/deckbar-daemon an
cp daemon/systemd/deckbar.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now deckbar.service
journalctl --user -u deckbar -f
```

Öffnen Links oder GUI-Programme aus dem Dienst heraus nicht, fehlt die Grafik-Umgebung im
systemd-User-Kontext: `systemctl --user import-environment WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP`.

Das Gerät erreicht den Daemon über Port 8765. Ist eine Firewall aktiv (z. B. `ufw`), muss dieser
Port im Heimnetz offen sein. Die Web-UI und `/api/*` antworten trotzdem nur auf localhost.

## Web-UI und Module

<http://localhost:8765> (nur von diesem PC aus erreichbar). Die Startseite ist ein Dashboard mit
einer Karte je eingeschaltetem Modul. Die Seitenleiste ordnet nach Situation: **Im Spiel**,
**Leiste**, **Teilen**, **System**. Jede Einstellung steht genau an einem Ort; ein Modul kann mehrere
Seiten haben (Radar: Warnungen, Radar & Karte). Hell und dunkel folgen dem System oder lassen sich
umschalten, die Seite passt sich auch an schmale Fenster an.

| Modul | Seiten und Inhalt | braucht |
|---|---|---|
| AION 2 · Overlay | Overlay: Profile, Widgets aller eingeschalteten Module, Steuerung, Darstellung | Kampfdaten |
| AION 2 · Radar | Warnungen (Aus · Nur Wichtiges · Alles, Einzelheiten unter „Erweitert“), Radar & Karte | Termine |
| AION 2 · Termine | Termine: feste Termine der Server und eigene Ereignisse, Feldbosse des Radars | – |
| AION 2 · Kampfdaten | Live-Ansicht, Quelle, Meter-Einstellungen öffnen | – |
| AION 2 · Plugins | Plugins: installiert, Katalog, Updates mit Zustimmung, ein/aus, Fenster öffnen | Overlay |
| Touch-Leiste | Editor (Seiten, Kacheln, Aktionen, Live-Vorschau), Design, Geräte (mit „Im Kampf zur Seite“) | – |
| AION 2 · Dungeon-Runs | Discord-Webhook, Vorschau, Namen der Mitspieler | Kampfdaten |
| NexHub | Dieses NexBoard mit einem Konto im NexHub koppeln | – |
| Updates | Stand von Repo und A2Tools-Kern, Aktualisieren | – |

Unter **System → Module** wird jedes Modul ein- oder ausgeschaltet, sofort und ohne Neustart.
Ausgeschaltete Module laufen nicht im Hintergrund (kein Mitschnitt, keine Abfragen) und
verschwinden aus der Seitenleiste; benötigte Module werden mit eingeschaltet, abhängige mit aus.
Ist die Touch-Leiste aus, weist der Daemon Geräte mit dem Fehler `disabled` ab. **System →
Einstellungen** bearbeitet `config.yaml` (Name, Player, Adresse, Port, USB, mDNS) und startet den
Daemon bei Bedarf neu.

Ein neues Modul ist eine Klasse in `daemon/deckbar_daemon/modules/` (Beschreibung, Aufgaben, Status,
Routen; Vertrag aus `packages/nexcore`), ein Eintrag in der Modulliste in `app.py` und eine Seite in
`daemon/deckbar_daemon/web/js/modules/` (Tabs, Dashboard-Karte, Inhalt). Die Web-UI kommt ohne
Framework und ohne Build-Schritt aus (ES-Module).

**Leisten-Editor** (Touch-Leiste → Editor): Seiten und Kacheln anlegen, per Drag & Drop sortieren
und mit Icon, Farbe und Aktion versehen. Jede Änderung wird nach 0,35 s gespeichert und sofort an
alle verbundenen Geräte geschickt. Im Modus „Testen“ verhält sich die Vorschau wie ein Gerät.

**Hintergrund** (Touch-Leiste → Design): Standard (in der Firmware eingebaut), Desktop-Hintergrund (folgt
einem Wechsel in Plasma) oder ein eigenes Bild, per Upload oder als Pfad. Hochgeladene Bilder
(höchstens 20 MB) landen verkleinert in `~/.config/deckbar/backgrounds/`. Das Gerät bekommt das Bild
auf 640 × 172 zugeschnitten, weichgezeichnet und leicht abgedunkelt. Es speichert es nicht, nach
einem Neustart erscheint kurz das Standardbild.

**Eigene Werte** auf die Leiste bringen (für `bind` bei Schaltern und Reglern):

```sh
curl -X POST localhost:8765/api/state -H 'Content-Type: application/json' -d '{"obs_rec": true}'
```

## Verbindung: WLAN, USB als Rückfall

Das Gerät verbindet sich per WLAN und findet den Daemon per mDNS (`_deckbar._tcp`), alternativ
über `DECKBAR_HOST` in `secrets.h`.

Hängt es zusätzlich per USB am PC, springt das Kabel ein, wenn der WebSocket 10 s lang nicht
steht, etwa bei schlechtem Empfang oder ohne WLAN. Das WLAN sucht im Hintergrund weiter. Sobald
der WebSocket wieder steht, verlässt das Gerät USB.

Über USB läuft dasselbe JSON-Protokoll, zeilenweise mit Präfix `@@`:

| Richtung    | Zeile            | Bedeutung |
|-------------|------------------|-----------|
| Gerät → PC  | `@@DECKBAR WLAN` | Kennung alle 2 s: läuft über WLAN |
|             | `@@DECKBAR`      | Kennung alle 2 s: kein WebSocket, bitte USB |
|             | `@@{…}`          | Protokollnachricht |
| PC → Gerät  | `@@OPEN`         | Brücke steht, Gerät schickt `hello` |
|             | `@@KEEP`         | Lebenszeichen alle 5 s, ohne fällt das Gerät nach 15 s zurück |
|             | `@@CLOSE`        | Brücke getrennt |
|             | `@@{…}`          | Protokollnachricht |

Alle anderen Zeilen sind Log-Ausgaben. Die Brücke (`daemon/deckbar_daemon/usb.py`) öffnet
Espressif-Ports nur passiv (DTR/RTS unverändert, also kein Reset) und schreibt erst nach der
Kennung. Fremde ESP32 am selben PC (z. B. WLED) bekommen nichts geschickt. Einstellung in
`config.yaml`: `usb: auto` (Standard), `off` oder ein fester Port `/dev/serial/by-id/…`.

## AION 2

### DPS-Meter

Die Kachel „AION 2 DPS-Meter“ füllt eine Seite und zeigt die DPS der Gruppe in Echtzeit: Rang,
Name, DPS und wahlweise Anteil oder Gesamtschaden, Balken in Klassenfarbe, die eigene Zeile
hervorgehoben. Darüber stehen Bossname, Rest-HP und Kampfdauer.

Die Daten liest die NexBoard selbst aus dem Spielverkehr mit: `deckbar-capture` (Ordner
`capture/`) setzt den Kern des [A2Tools DPS Meter](https://github.com/taengu/A2Tools-DPS-Meter)
ohne dessen Oberfläche zusammen (libpcap, Port-Erkennung, Parser, DPS-Berechnung). Der Daemon
startet das Programm, sobald AION 2 läuft, und beendet es 30 s nach dem Spiel. Gebaut wird ohne
die Online-Funktionen des Meters: kein Konto, keine Uploads, keine Update-Abfrage.

1. Bauen und installieren (einmal und nach jedem Update):

   ```sh
   capture/build.sh --install     # cargo build, Kopie nach ~/.local/bin, sudo setcap cap_net_raw
   systemctl --user restart deckbar
   ```

   Mitschneiden braucht nur `cap_net_raw`, nicht root. Ein Neubau verliert die Rechte, deshalb
   immer mit `--install` bauen.
2. In der Web-UI das Modul „AION 2 · Kampfdaten“ einschalten und unter „Quelle und Meter“
   „Eigener Mitschnitt“ wählen (Standard). Die Sprache der Boss- und Skillnamen ist die allgemeine
   unter System → Einstellungen; sie gilt auch für Meter, Ansagen und Warnungen.
3. Eine Seite mit der Kachel „AION 2 DPS-Meter“ anlegen. Spielerzahl (1–8) und Zusatzwert stehen
   in den Kachel-Eigenschaften.
4. Optional „Bei Kampfbeginn zeigen“: Sobald neuer Schaden kommt, springt die Leiste auf diese
   Seite und nach „Zurück nach“ Sekunden ohne Schaden wieder auf die vorige (nicht, wenn man
   inzwischen selbst weggewischt hat).

Die Liste zeigt die Top N nach DPS am aktuellen Ziel (Bosse zuerst) plus einen selbst; im
Dungeon ist das die Gruppe. Kampf-History im Format des Meters: `~/.local/share/deckbar/aion2/history/`,
daneben in `hits/` jeder einzelne Treffer mit eigenem Schaden und Merkmalen (für den Hub, Format in
[`proto/README.md`](../proto/README.md)). Dafür meldet ein kleiner Patch am Kern
(`capture/patches/`) jeden Treffer; `capture/build.sh` wendet ihn an, `update.sh` nimmt ihn vor
einem A2Tools-Update zurück. Passt er nach einem Update nicht mehr, bricht der Build mit Hinweis ab.

`deckbar-capture` spricht Zeilen-JSON über stdin/stdout (Überblick in `capture/src/main.rs`, Nachrichten in
`out.rs`, Befehle in `commands.rs`) und lässt sich zum Testen auch allein starten. Auf stdout schreibt nur
ein eigener Thread: Hängt der Daemon, ersetzen neue Zustände (DPS, Status) die wartenden, Ereignisse gehen
bei voller Warteschlange verloren, und der Mitschnitt läuft weiter. Die volle DpsData für die
Meter-Seiten kommt nur bei Änderung als eigene Zeile `dps_data`, die der Daemon ungeparst weiterreicht. `--save-packets DIR` zeichnet den Mitschnitt auf,
`--replay packets_….txt [--realtime]` spielt ihn ohne Spiel wieder ab:

```sh
capture/target/release/deckbar-capture --replay packets_2026-10-12.txt --history-dir /tmp/test
```

Ein Spiel-Patch ändert meist Opcodes oder Datentabellen. Upstream zieht das schnell nach, die
NexBoard meldet das neue Release (siehe „Updates“).

### Overlay am PC

`deckbar-overlay` legt unter KDE Plasma (Wayland) eine durchsichtige **layer-shell-Fläche** über
den Spielmonitor, Ebene „overlay“, also über dem Vollbildspiel. Darin liegen Widgets:

- **DPS-Meter:** die unveränderte Oberfläche des A2Tools-Meters, mit Details (Skills, Buffs,
  Zeitleiste), Kampf-History und Einstellungen als eigene Fenster. Verschieben wie gewohnt an
  Kopf- oder Fußzeile, die Position bleibt gespeichert.
- **Boss-Leiste:** HP des Ziels, Kampfzeit und Kill-Prognose aus dem HP-Verlauf, außerhalb von
  Kämpfen ausgeblendet.
- **Termine:** Countdown bis zum nächsten Termin (Riss, Shugo-Fest, Resets … und eigene Ereignisse).
  Dieselbe Liste wie auf der Seite „Termine“, gerechnet im Daemon aus `nexproto.termine`.
- **Cube-Radar** (Modul „AION 2 · Radar“): kleiner Kreis mit Richtung, Abstand und Höhe zum nächsten Hidden
  Cube; erscheint nur, solange einer in Sicht ist.
- **Karte** (Modul „AION 2 · Radar“, standardmäßig aus): Cubes, Spawnpunkte, Fundorte und Teleporter. Bilder
  und Kartenlogik kommen aus dem installierten Plugin Pet Soul Tracker.
- **Boss-Warnungen** (Modul „AION 2 · Radar“): nur während einer Warnung.
- **Namenseffekt** auf dem eigenen Namen in der Meter-Zeile: Glanz, Brennen, Gold, Frost, Holo, Leere.

PvP (Kills, Tode, Assists, Abyss-Punkte), Vertraute und Würfel zeigt das Overlay nicht selbst: dafür gibt es die
A2Tools-Plugins PvP Tracker, Pet Soul Tracker und Dice Rolls (Im Spiel → Plugins) mit eigenen Fenstern und Widgets.

**Profile** legen fest, welche Widgets sichtbar sind (Standard: PvE und PvP). Wechsel in der
Bearbeiten-Leiste, in der Web-UI (Im Spiel → Overlay) oder per `--profile NAME`; das aktive
Profil merkt sich jedes Ein- und Ausblenden. `--widget ID` blendet ein einzelnes Widget ein oder aus
(meter, boss, timers, cube, map, warnings). Beides geht ohne Qt direkt an den Daemon, wirkt
also sofort. Der Daemon trägt je Profil und Widget eine Aktion in den Starter „NexBoard Overlay
ein/aus“ ein; dort in den Systemeinstellungen (Kurzbefehle) eine Taste zuweisen.

Die Fläche bekommt nie die Tastatur und nimmt Klicks nur dort an, wo es nötig ist:

| Modus | Klicks | |
|---|---|---|
| Entsperrt (Standard) | nur das Meter, alles andere geht ans Spiel | |
| Gesperrt | nur der Schloss-Knopf des Meters | Schloss im Meter, Tray oder `--lock` |
| Bearbeiten | alles, Widgets ziehen, Mausrad = Größe, Esc = fertig | `--edit`, Tray oder Web-UI |

```sh
sudo pacman -S --needed pyside6 qt6-webengine layer-shell-qt
overlay/install.sh        # ~/.local/bin/deckbar-overlay, User-Dienst, Starter für Tastenkürzel
```

Danach startet das Modul „AION 2 · Overlay“ den Dienst, sobald AION 2 läuft, und beendet ihn 30 s
nach Spielende; beim Login startet nichts. Von Hand (ohne Spiel): Web-UI → „Neu starten“. Befehle: `--toggle`
(zeigen/verbergen), `--edit`, `--lock`, `--click`, `--details`, `--history`, `--settings`,
`--reload`, `--quit`; für Tastenkürzel die Starter „NexBoard Overlay ein/aus“ und „… bearbeiten“
in den Systemeinstellungen auf eine Taste legen. Monitor (Standard: Hauptmonitor laut KDE),
Startmodus, Namenseffekt und Widgets stehen in der Web-UI; das Layout liegt in
`~/.config/deckbar/overlay/layout.json`.

Unter KWin blendet sich die Fläche aus, solange ein anderes Fenster als AION 2 den Fokus hat, auch
eines auf einem anderen Monitor (Web-UI: „Nur bei aktivem Spiel zeigen“, Befehle `--autohide-on`/`-off`).
Dafür lädt das Programm das KWin-Skript `overlay/focus.js`, das jeden Fensterwechsel per D-Bus
(`org.deckbar.Overlay`) meldet, und entlädt es beim Beenden. Erkannt wird das Spiel an der
Fensterklasse `steam_app_3393110`. Eigene Fenster (Bearbeiten, Details) ändern nichts,
im Bearbeiten-Modus bleibt die Fläche immer sichtbar, und `--show` zeigt sie bis zum nächsten
Fensterwechsel auch ohne Spielfokus.

Ohne layer-shell (GNOME, X11 oder ohne `layer-shell-qt`) startet automatisch das frühere
Meter-Fenster unter XWayland (`--legacy`): KWin-Regel für die Ebene „Overlay“, Durchklicken per
X11-Input-Shape, ohne die zusätzlichen Widgets.

So funktioniert es: Der Daemon liefert auf Port 8766 (nur localhost) die Overlay-Seite
(`daemon/deckbar_daemon/web/overlay/`) und die Oberfläche aus `capture/a2tools` aus, mit einem
kleinen Ersatz für Tauris JavaScript-API davor (`web/a2shim.js`). Daten-Befehle gehen an
`deckbar-capture` (`a2ui.py`), Fenster-Befehle an die Overlay-Seite bzw. das Programm. Die
Einstellungen der Meter-Oberfläche liegen in `~/.config/deckbar/a2-settings.json`. Nicht dabei sind
die übrigen Online-Funktionen und die eigenen globalen Tastenkürzel des Meters.

**A2Tools-Plugins** laufen ohne das Meter-Programm: in der Web-UI unter Im Spiel → Plugins installieren
(signierter Katalog von cdn.a2tools.app, Ed25519, Zustimmung zu den Berechtigungen; die Texte dazu kommen aus
dem Meter). Die Plugin-Seite in den Meter-Einstellungen geht weiterhin. Das eigenständige A2Tools-Programm hat
einen eigenen Plugin-Ordner, den die NexBoard nicht sieht. Ist das Modul aus, laufen keine Plugins und
bekommen keine Spieldaten; installiert bleibt alles. Der
Plugin-Host ist `daemon/deckbar_daemon/plugins.py`, ein Nachbau des Hosts aus dem Submodul; die Seiten
kommen unverändert von dort. Hauptfenster sind normale Fenster des Overlay-Programms (damit die Tastatur
geht), Widgets liegen auf der Overlay-Fläche (`web/overlay/plugins.js`). Spieldaten liefern
`capture/src/decoders.rs` (Decoder je Opcode) und `capture/src/feed.rs` (Charakter, Feldboss-Karte …). Installiert wird nach `~/.local/share/deckbar/plugins/`, Plugin-Daten liegen
in `plugin-data/` daneben. Plugins laufen, solange das Overlay läuft, also mit dem Spiel. Anders als im
Meter: kein Dock, keine FPS-Anzeige (zählt nur unter Windows), keine Entwickler-Ordner, die Option
„ausblenden“ wirkt nur über das Overlay selbst, Widgets nur mit layer-shell. Plugin-API bis Version 2;
ein Plugin mit neuerer API wird abgelehnt, dann `API_VERSION` und den Host nachziehen.

**Aufbau der Overlay-Seite** (`daemon/deckbar_daemon/web/overlay/`, ES-Module ohne Build): `stage.js` hängt je
angemeldetem Widget `widgets/<id>.js` ein, `layout.js` lädt und speichert Positionen, `edit.js` ist der
Bearbeiten-Modus, `plugins.js` trägt die Widgets der A2Tools-Plugins, `host.js` spricht mit dem Overlay-Programm.
Ein Modul des Daemons meldet seine Widgets über `overlay_widgets` an (`WidgetSpec` in `overlay_layout.py`: Titel,
Hilfetext, Schalter, Startgröße); ein neues Widget ist also eine Anmeldung plus eine Datei unter `widgets/`, der
Kern bleibt unberührt. Die Seite hat eine Datenverbindung (`/api/overlay/events`), ein ausgeschaltetes Widget
bekommt nichts und beim Einschalten den letzten Stand. `layout.json` der Version 1 (deutsche Schlüssel, Radar als
ein Fenster, eigenes PvP-Widget) wird beim Laden übersetzt.

**Alternative: A2Tools-Meter selbst.** Läuft das Meter, kann die NexBoard stattdessen dessen
Stream-Overlay lesen (Quelle „A2Tools-Meter“, `/overlay/events`, Server-Sent Events). Dafür im
Meter das Stream-Overlay einschalten. Port und Schlüssel liest der Daemon aus
`~/.local/share/com.a2tools.dps-meter/settings.json`, sonst von Hand aus der Overlay-URL.

Die Einstellungen liegen in `~/.config/deckbar/aion2.dps.yaml` (Modus 600, enthält ggf. den Schlüssel).

### Dungeon-Runs nach Discord

Nach jedem Dungeon-Run postet der Daemon ein Bild mit dem Schaden pro Spieler und Boss an einen
Discord-Webhook (Modul „AION 2 · Dungeon-Runs“, gespeichert in `~/.config/deckbar/aion2.runs.yaml`).
Quelle ist die Kampf-History, je nach DPS-Quelle die von `deckbar-capture` oder die des Meters. Ein Run endet, sobald der Endboss liegt, bei einem
Dungeonwechsel oder nach einer einstellbaren Zeit ohne Bosskampf (Details in
`daemon/deckbar_daemon/runs.py`). Die Vorschau und „Letzten Run jetzt posten“ helfen beim Einrichten.

Die History maskiert fremde Namen. Die NexBoard lernt die vollen Namen aus dem Live-Stream und
speichert sie nur lokal (`runs-state.json`). In der Web-UI lassen sie sich von Hand korrigieren.

## Runs in Discord

Ein Weg für alles (Umbau-Konzept): NexBoard → NexHub → TheWashBot. Unter NexHub → „Runs teilen“ erst
„Hochladen“, dann „In Discord posten“ einschalten, beides mit Zustimmung (Namen der Mitspieler). Nach dem
Upload geht der Run-Bericht (`daemon/deckbar_daemon/report.py`, Format `nexproto.runreport.RunReport`) an den
Hub, der ihn mit Link zum Run an den Bot weiterleitet; der Bot postet im Kanal des Hub-Servers. Das frühere
Modul „Discord-Bot“ (eigene Bot-Adresse und Token je NexBoard, Gruppen-DPS) ist entfallen. Das Run-Bild per
Discord-Webhook bleibt als Option im Modul „Dungeon-Runs“.

## NexHub

Das Modul **NexHub** verbindet das NexBoard mit einem Konto auf der Hub-Website (Ordner
[`hub/`](../hub/) im Repo). Kopplung wie beim Fernseher: Hub-Adresse eintragen, „Koppeln“ zeigt
einen Code wie `BCDF-GHJK` mit Link, im Hub unter „Geräte“ bestätigen, fertig. NexBoard merkt die
Bestätigung von selbst und bekommt ein eigenes Geräte-Token (`~/.config/deckbar/hub.yaml`,
Rechte 600). Im Hub lässt sich das Gerät jederzeit entfernen, in NexBoard abkoppeln.

Ohne `https` nimmt NexBoard nur `localhost` als Adresse an, etwa über einen SSH-Tunnel
(`http://localhost:8080`), damit das Token nie unverschlüsselt durchs Netz geht.

**Runs hochladen** ist ein eigener Schalter (aus, fragt beim Einschalten nach): Nach jedem Run, den
das Modul „AION 2 · Dungeon-Runs“ erkennt, packt NexBoard Kampfdateien und Einzeltreffer als
NexLog ([`proto/`](../proto/)) in den Postausgang `~/.local/share/deckbar/outbox/` und lädt ihn
hoch, sobald der Hub erreichbar ist. Ohne Netz bleibt er liegen (höchstens 500 MB, älteste zuerst
weg) und geht beim nächsten Versuch raus. Vom Hub abgelehnte Dateien landen in `outbox/abgelehnt/`.
Der Daemon braucht dafür das Paket `nexproto` aus dem Repo: nach dem Umstieg einmal
`uv tool install --force --editable ./daemon`.

## Updates

Der Daemon sieht kurz nach dem Start und dann täglich nach, ob es neue Commits der NexBoard auf
GitHub gibt oder ein neues Release des A2Tools-Meters (nach Spiel-Patches ändern sich dort Opcodes
und Datentabellen). Dann meldet sich das Tray-Symbol des Overlays einmal mit einer Benachrichtigung,
im Tray-Menü steht „Jetzt aktualisieren“, in der Web-UI (Modul „Updates“) ein Hinweis mit Button.
Abschalten über das Modul „Updates“.

Der Button öffnet ein Konsole-Fenster mit `./update.sh`, von Hand geht es genauso:

```sh
./update.sh             # git pull, Submodul, deckbar-capture nur bei Änderungen neu bauen, Neustart
./update.sh --a2tools   # zusätzlich A2Tools auf das neueste Release heben (lokal, bis es im Repo nachgezogen ist)
```

**Umzug ins Monorepo (Installationen von vor dem 21.10.2026):** Das erste Update holt den neuen
Stand und meldet dann „Fehlgeschlagen: Submodul capture/a2tools“, weil das alte Skript noch die
alten Pfade kennt. Einfach noch einmal aktualisieren: Ab dann läuft das neue Skript
(`nexboard/update.sh`, an der Wurzel als Symlink) und richtet Daemon, Unit und Mitschnitt neu ein.

Muss `deckbar-capture` neu gebaut werden, fragt das Skript per `sudo` nach dem Passwort für die
Mitschnitt-Rechte. Bei lokalen Änderungen im Repo bricht es ab, statt etwas zu überschreiben.
Wer das Repo pflegt, zieht ein neues A2Tools-Release mit `git -C capture/a2tools checkout vX.Y.Z`
und einem Commit für alle nach.

## Firmware

Zwei Board-Versionen, erkennbar am QC-Label:

| Board | Umgebung     | Unterschiede |
|-------|--------------|--------------|
| V2 (PCB „Rev1.1“, Label „V2“) | `deckbar` (Standard) | LCD-Reset und Backlight-Freigabe über den IO-Expander TCA9554, Backlight-PWM GPIO42, GPIO21 = TE-*Ausgang* des Displays |
| V1 (ohne „V2“) | `deckbar-v1` | LCD-Reset GPIO21, Backlight-PWM GPIO8 (invertiert), kein Expander |

Pins und Treiber stammen aus <https://github.com/waveshareteam/ESP32-S3-Touch-LCD-3.49-V2> bzw.
dem älteren Repo ohne „-V2“ für V1. Die beiden nicht verwechseln: Mit V1-Pins würde die Firmware
auf V2 den TE-Ausgang des Displays treiben.

```sh
cd firmware
cp include/secrets.example.h include/secrets.h     # WLAN + Token eintragen (gitignored)
./flash.sh                                         # V2; ./flash.sh deckbar-v1 für V1
pio device monitor
```

`flash.sh` hält den Daemon während des Flashens an, weil die USB-Brücke den Port belegt, und
fragt nach dem Port, wenn mehrere ESP32 angeschlossen sind (fest: `PORT=/dev/serial/by-id/… ./flash.sh`).
Klappt der automatische Reset nicht: BOOT gedrückt halten und RESET tippen. Danach bleibt das
Board im Download-Modus, bis es ohne BOOT neu eingesteckt wird.

Das letzte Layout liegt im NVS, damit es nach einem Neustart sofort erscheint. Im seriellen Log
stehen Netzstatus, alle 5 s RSSI und Kanal sowie beim Start die gefundenen WLANs. Weitere
Einstellungen in `include/deckbar_config.h`, auch per `PLATFORMIO_BUILD_FLAGS="-D…"`:

| Define                 | Standard | Bedeutung |
|------------------------|----------|-----------|
| `DECKBAR_ROTATION`     | 270      | Steht das Bild auf dem Kopf: 90 (Touch wird mitgedreht) |
| `DECKBAR_BRIGHTNESS`   | 255      | Backlight 0–255 |
| `DECKBAR_PERF_MONITOR` | 0        | FPS-/CPU-Anzeige von LVGL |
| `DECKBAR_TOUCH_DEBUG`  | 0        | Rohdaten des Touch-Controllers und gesendete Nachrichten seriell ausgeben |
| `DECKBAR_TOUCH_GHOST_*`| aus      | Rechteck, in dem Touch-Punkte verworfen werden (für Boards mit Geisterpunkt) |

**Gut zu wissen:**

- Der AXS15231B nimmt per QSPI nur ganze Frames ab Zeile 0 an. LVGL rendert deshalb im
  DIRECT-Modus, `display.c` überträgt pro Frame das ganze Bild (etwa 14 ms).
- Der Touch-Controller liefert gelegentlich ungültige Frames. Sie werden verworfen, Sprünge
  gefiltert. Geisterklicks traten bisher nur an einer bestimmten Stromversorgung auf.
- In den Glasverläufen sind leichte RGB565-Stufen sichtbar, die Hintergrundbilder werden deshalb
  mit Dithering gewandelt.

## Simulator

```sh
cd simulator
cmake -S . -B build -G Ninja      # lädt LVGL 9.3.0 beim ersten Mal
cmake --build build
./build/deckbar-sim               # Token kommt automatisch aus ~/.config/deckbar/config.yaml
```

Optionen: `--url ws://host:8765/ws`, `--zoom 3`, `--no-perf` (FPS-Anzeige aus), `--no-cache`,
`-v` (gesendete Nachrichten anzeigen). Für automatische Tests gibt es `--gesture "x,y@ms"`,
`"x,y@ms+halten"` und `"x,y>x2,y2@ms"` sowie `--screenshot bild.ppm --after 1500`. Ohne Fenster:
`SDL_VIDEODRIVER=offscreen ./build/deckbar-sim --screenshot …`.

Der Simulator speichert das letzte Layout wie das Gerät (`~/.cache/deckbar-sim/layout.json`). Er
zeigt es also sofort nach dem Start an und blendet „Suche Daemon …“ ein, bis die Verbindung steht.

## Assets neu erzeugen

```sh
uv run --with pillow tools/gen_assets.py              # Schriften + Icons + Hintergrund
uv run --with pillow tools/gen_assets.py --bg foto.jpg --only bg   # eigenes Hintergrundbild
```

Zusätzliche Icons trägt man in `tools/icons.txt` ein (Namen aus
<https://pictogrammers.com/library/mdi/>). Das Skript lädt die Quellen einmalig nach
`tools/.cache/` und braucht `npx` für `lv_font_conv`.

## Tests

```sh
cd daemon && uv run python -m pytest -q
cd radar && ../daemon/.venv/bin/python -m pytest -q tests   # mit Goldtest, siehe radar/README.md
cd capture && ./build.sh && cargo test --release && cargo clippy --release -- -D warnings && cargo fmt --check
```

Der Goldtest der Spur „capture“ nimmt das Programm aus `capture/target/release/`; nach Änderungen am
Mitschnitt also erst `./build.sh`, dann den Goldtest.

`daemon/tests/test_simulator.py` vergleicht jede Seite aus `daemon/tests/simulator_layout.yaml` mit den
Referenzbildern in `simulator/reference/` (braucht den gebauten Simulator, sonst übersprungen). Sieht ein
Kacheltyp gewollt anders aus: `WRITE_REFERENCE=1 uv run python -m pytest -q tests/test_simulator.py` und
die neuen Bilder mit einchecken.

## Lizenz

NexBoard steht unter der **GNU General Public License v3.0 oder später** (`LICENSE`).

Teile stammen aus dem [A2Tools DPS Meter](https://github.com/taengu/A2Tools-DPS-Meter) (GPL-3.0):
der Mitschnitt-Kern und die Oberfläche des Overlays als unverändertes Submodul `capture/a2tools`,
die Zeilenaufbereitung in
`capture/src/view.rs` (nach `stream_overlay/snapshot.rs`), die Klassen-Icons in
`daemon/deckbar_daemon/assets/classes/` und das Design der Dungeon-Run-Bilder (nach `src/styles.css`). Übernommene Dateien sind an Ort und Stelle gekennzeichnet, inklusive der
Änderungen.

Weitere Fremdbestandteile:

- Material Design Icons (Pictogrammers, Apache 2.0 / OFL)
- Inter (OFL 1.1)
- cJSON (MIT)
- Treiber in `firmware/src/drivers` und `firmware/src/touch`: Espressif, Apache 2.0
