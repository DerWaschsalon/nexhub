# DeckBar

Eine Touch-Leiste unter dem Monitor im Stil eines Stream Deck, gebaut auf dem
Waveshare **ESP32-S3-Touch-LCD-3.49 V2** (640 × 172 im Querformat): Audio- und
Media-Steuerung, Links, Hotkeys und Shell-Befehle, dazu Live-Status (Mute, Lautstärke,
Track). Die Optik ist im „Liquid Glass“-Stil gehalten.

```
┌──────────────┐  WebSocket (JSON, v1)  ┌──────────────────────────────┐
│ Gerät / Sim  │ ◄────────────────────► │ deckbar-daemon (Python)      │
│ shared-ui    │   layout, state  →     │  wpctl · pactl subscribe     │
│ (LVGL 9.3)   │   ← event              │  playerctl --follow          │
└──────────────┘                        │  xdg-open · ydotool · shell  │
                                        │  Web-UI  http://localhost:8765│
                                        └──────────────────────────────┘
```

**USB oder WLAN:** Hängt das Gerät per USB am PC, läuft alles über das Kabel (zuverlässiger,
unabhängig vom Empfang). Ohne USB-Verbindung nimmt es WLAN. Der Wechsel passiert von selbst: das
Gerät sendet über USB alle 2 s eine Kennung, der Daemon (`daemon/deckbar_daemon/usb.py`) prüft die
Espressif-Ports nur passiv und schreibt erst nach dieser Kennung. Fremde ESP32 am selben PC
(z. B. WLED) bekommen also nichts geschickt. Abschalten mit `usb: off` in `config.yaml`, oder
fester Port mit `usb: /dev/serial/by-id/…`. Fehlen 15 s lang Lebenszeichen über USB, fällt das
Gerät auf WLAN zurück.

Die Firmware hält keine eigene Logik. Das Gerät rendert, was der Daemon schickt, und
meldet nur zurück, welche Kachel angetippt wurde. Welche Aktion dahinter steckt, weiß
allein der Daemon.

| Ordner       | Inhalt |
|--------------|--------|
| `docs/`      | [Protokoll](docs/protocol.md), [JSON-Schema](docs/protocol.schema.json), [Icon-Liste](docs/icons.md) |
| `shared-ui/` | LVGL-UI-Code (C). Läuft unverändert in Firmware **und** Simulator, Hardware nur über `include/deckbar/hal.h` |
| `simulator/` | SDL2-Fenster 640 × 172, RGB565, Maus = Touch, echter WebSocket zum Daemon |
| `daemon/`    | Python-Daemon inkl. Web-Konfiguration, systemd-User-Service |
| `firmware/`  | PlatformIO / Arduino-ESP32 3.3.12, Treiber aus dem Waveshare-**V2**-Repo |
| `tools/`     | `gen_assets.py`: Schriften, Icons, Hintergrundbild erzeugen |

## Schnellinstallation (CachyOS / Arch, KDE Plasma)

```sh
git clone https://github.com/Navonex/deckbar && cd deckbar
./install.sh
```

Das Skript richtet alles ein: Pakete, den Daemon als User-Dienst, den
[A2Tools DPS Meter](https://github.com/taengu/A2Tools-DPS-Meter) (offizielles Paket vom neuesten
Release, SHA-256 gegen GitHub geprüft) mit Autostart zum Spiel und eingeschaltetem
Stream-Overlay, eine KWin-Regel, die das Meter-Fenster ausblendet (die DPS stehen nur noch auf
der Leiste), und bei aktivem `ufw` die Freigabe von Port 8765 im Heimnetz. Es lässt sich
mehrfach ausführen, z. B. für Updates. Optionen: `--no-a2tools`, `--show-meter`.
A2Tools steht unter GPLv3 und wird nicht mitgeliefert, sondern beim Installieren geladen.

Danach nur noch die Firmware flashen, siehe unten (`firmware/flash.sh`, V1-Boards: `./flash.sh deckbar-v1`).

## Voraussetzungen (CachyOS / Arch)

```sh
sudo pacman -S --needed sdl2 playerctl ydotool wireplumber libpulse
uv tool install cmake && uv tool install ninja     # oder: pacman -S cmake ninja
uv tool install platformio                         # nur für die Firmware
systemctl --user enable --now ydotool              # ydotoold für Hotkeys
```

`libpulse` bringt `pactl` mit. Der Daemon nutzt es nur für `pactl subscribe`, also
ereignisbasierte Updates statt Polling. Fehlt ein Werkzeug, läuft der Rest trotzdem,
und die Web-UI zeigt an, was fehlt.

## Daemon starten

```sh
cd daemon
uv sync
uv run deckbar-daemon          # -v für Debug-Ausgaben, --open öffnet die Web-UI
```

Beim ersten Start legt der Daemon in `~/.config/deckbar/` zwei Dateien an:

- `config.yaml`: Port, **Token** (zufällig erzeugt), Name, bevorzugter Player
- `layout.yaml`: Seiten und Kacheln mit Aktionen, kommentiertes Beispiel

Beide Dateien sind außerhalb des Repos. Handänderungen an `layout.yaml` übernimmt der
Daemon live (Prüfung einmal pro Sekunde). Ist die Datei ungültig, bleibt das alte
Layout aktiv, und die Web-UI zeigt den Fehler an.

**Web-Konfiguration:** <http://localhost:8765>. Dort lassen sich Kacheln anlegen, per
Drag & Drop sortieren und mit Icon, Farbe und Aktion versehen. Jede Änderung wird nach
0,35 s gespeichert und sofort an alle verbundenen Geräte geschickt. Im Modus „Testen“
verhält sich die Vorschau wie ein Gerät. Die Web-UI und `/api/*` antworten nur auf
localhost.

Status aus eigenen Skripten auf die Leiste bringen (für `bind` bei Toggles und Slidern):

```sh
curl -X POST localhost:8765/api/state -H 'Content-Type: application/json' -d '{"obs_rec": true}'
```

### Autostart als systemd-User-Service

```sh
uv tool install --editable ./daemon                 # legt ~/.local/bin/deckbar-daemon an
cp daemon/systemd/deckbar.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now deckbar.service
journalctl --user -u deckbar -f
```

Öffnen Links oder GUI-Programme aus dem Dienst heraus nicht, fehlt die
Grafik-Umgebung im systemd-User-Kontext:
`systemctl --user import-environment WAYLAND_DISPLAY DISPLAY XDG_CURRENT_DESKTOP`.

## AION 2: DPS-Meter

Die Kachel „AION 2 DPS-Meter“ zeigt die DPS der Gruppe in Echtzeit: Rang, Name, DPS und
wahlweise Anteil oder Gesamtschaden, Balken in Klassenfarbe, die eigene Zeile umrandet.
Darüber stehen Bossname, Rest-HP und Kampfdauer.

Die Daten kommen vom [A2Tools DPS Meter](https://github.com/taengu/A2Tools-DPS-Meter). Das
Meter liest die Spielpakete mit, die DeckBar liest nur seinen Stream-Overlay-Server
(`/overlay/events`, Server-Sent Events, etwa 3 × pro Sekunde, siehe `daemon/deckbar_daemon/dps.py`).

1. Im A2Tools-Meter unter Einstellungen das **Stream-Overlay** einschalten.
2. In der Web-UI (Karte „AION 2 DPS-Meter“) die Verbindung auf „Automatisch“ lassen: Port
   und Schlüssel liest der Daemon aus `~/.local/share/com.a2tools.dps-meter/settings.json`,
   auch nach „Neuer Schlüssel“ im Meter. Sonst Port und `key=…` aus der Overlay-URL von Hand.
3. Eine Seite mit der Kachel „AION 2 DPS-Meter“ anlegen (füllt die Seite). Spielerzahl
   (1–8) und Zusatzwert stehen in den Kachel-Eigenschaften.
4. Optional „Bei Kampfbeginn zeigen“: Sobald neuer Schaden kommt, springt die Leiste auf
   diese Seite und nach „Zurück nach“ Sekunden ohne Schaden wieder auf die vorige Seite
   (nicht, wenn man inzwischen selbst weggewischt hat).

Die Einstellungen liegen in `~/.config/deckbar/dps.yaml` (Modus 600, enthält ggf. den
Schlüssel). Das Meter listet nicht streng die Gruppe, sondern die Top N nach DPS am Ziel
plus einen selbst; im Dungeon ist das die Gruppe. Wie viele es höchstens sind, stellt man
im Meter ein (Spielerlimit, Standard 6).

## Simulator starten

```sh
cd simulator
cmake -S . -B build -G Ninja      # lädt LVGL 9.3.0 beim ersten Mal
cmake --build build
./build/deckbar-sim               # Token kommt automatisch aus ~/.config/deckbar/config.yaml
```

Optionen: `--url ws://host:8765/ws`, `--zoom 3`, `--no-perf` (FPS-Anzeige aus),
`--no-cache`, `-v` (gesendete Nachrichten anzeigen). Für automatische Tests gibt es
`--gesture "x,y@ms"`, `"x,y@ms+halten"` und `"x,y>x2,y2@ms"` sowie
`--screenshot bild.ppm --after 1500`. Ohne Fenster:
`SDL_VIDEODRIVER=offscreen ./build/deckbar-sim --screenshot …`.

Der Simulator speichert das letzte Layout wie das Gerät
(`~/.cache/deckbar-sim/layout.json`). Er zeigt es also sofort nach dem Start an und
blendet „Suche Daemon …“ ein, bis die Verbindung steht.

## Firmware flashen

> **V1 und V2:** Standard ist V2 (PCB-Aufdruck „Rev1.1“, QC-Label „V2“, `pio run -e deckbar`).
> Für die ältere V1 (LCD-Reset GPIO21, Backlight GPIO8) gibt es `pio run -e deckbar-v1`, läuft
> auf einem V1-Board. Im seriellen Log stehen Netzstatus, RSSI und beim Start die gefundenen WLANs.
> Pins und Treiber stammen aus
> <https://github.com/waveshareteam/ESP32-S3-Touch-LCD-3.49-V2>. Das ältere Repo ohne
> „-V2“ gilt für V1: Dort ist GPIO21 der LCD-Reset, bei V2 ist GPIO21 der TE-*Ausgang*
> des Displays.

```sh
cd firmware
cp include/secrets.example.h include/secrets.h     # WLAN + Token eintragen (gitignored)
./flash.sh                                         # V2; ./flash.sh deckbar-v1 für V1
                                                   # hält den Daemon (USB-Brücke) kurz an
pio device monitor
```

Den Daemon findet das Gerät per mDNS (`_deckbar._tcp`). Alternativ lässt sich in
`secrets.h` `DECKBAR_HOST` fest setzen. Das letzte Layout liegt im NVS, damit es nach
einem Neustart sofort erscheint. Weitere Einstellungen stehen in
`include/deckbar_config.h`:

| Define                 | Standard | Bedeutung |
|------------------------|----------|-----------|
| `DECKBAR_ROTATION`     | 270      | Steht das Bild auf dem Kopf: 90 (Touch wird mitgedreht) |
| `DECKBAR_BRIGHTNESS`   | 255      | Backlight 0–255 |
| `DECKBAR_PERF_MONITOR` | 0        | FPS-/CPU-Anzeige von LVGL |

### Auf der Hardware zu prüfen

Diese Punkte sind aus dem Waveshare-Code **abgeleitet**, aber noch nicht auf einem
echten Gerät getestet:

1. **Ausrichtung und Touch-Achsen.** Die Drehung entspricht dem Waveshare-Beispiel
   (`LV_DISPLAY_ROTATION_270`), die Touch-Umrechnung ist daraus hergeleitet. Stimmt ein
   Tap nicht mit der Kachel überein, liegt der Fehler in `touch_read_cb` in
   `firmware/src/display.c`.
2. **Backlight-Polarität.** Die Ansteuerung folgt dem V2-Beispiel (GPIO42 + EXIO1, PWM
   invertiert). Bleibt das Display dunkel oder lässt sich nicht dimmen, ist hier
   anzusetzen.
3. **Render-Pfad.** Abweichend vom Beispiel rendert LVGL im DIRECT-Modus, und
   `display.c` überträgt pro Frame das ganze Bild (der AXS15231B nimmt per QSPI nur
   ganze Frames an). Ziel sind ≥ 30 fps, messbar mit `DECKBAR_PERF_MONITOR=1`.
4. **RGB565-Banding.** In den Glasverläufen sieht man im Simulator leichte Stufen. Ob
   das auf dem IPS-Panel stört, zeigt erst die Hardware.

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
```

## Lizenzen

- Material Design Icons (Pictogrammers, Apache 2.0 / OFL)
- Inter (OFL 1.1)
- cJSON (MIT)
- Treiber in `firmware/src/drivers` und `firmware/src/touch`: Espressif, Apache 2.0
