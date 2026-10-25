# AION2 Radar

Radar für AION 2 unter Linux (KDE Wayland, Spiel unter Proton), als Modul **AION 2 · Radar** des
NexBoard. Liest den Server-Verkehr passiv per `tcpdump` mit (`cap_net_raw`), greift nicht ins Spiel ein.
Es läuft im NexBoard-Daemon und zeigt sich als Widgets im NexBoard-Overlay (Radar, Boss-Warnungen,
Karte), kein eigenes Programm und keine eigenen Fenster.

tcpdump einrichten: `sudo pacman -S tcpdump && sudo setcap cap_net_raw,cap_net_admin=eip /usr/bin/tcpdump`

- **Cube-Radar:** rundes Radar im Overlay, erscheint nur, solange ein Hidden Cube in Sicht ist; Ton bei
  neuem Cube. Unter dem Radar Entfernung, Höhe und wie lange der Cube schon steht (Spawnzeit vom Server).
  Öffnet ihn gerade jemand, wird er orange und der Name steht unten. Reichweite, Drehen und Spiegeln auf der
  NexBoard-Seite „Radar“; Position und Größe im Bearbeiten-Modus des Overlays.
- **Karte:** Widget im Overlay (unter Overlay → Widgets einschalten): Kartenbild mit gesehenen Spawnpunkten,
  aktiven Cubes und der eigenen Position. Ziehen = verschieben, Mausrad = Zoom um die eigene Position,
  „Spieler folgen“ und die Kartenwahl auf der Seite „Radar“.
- **Cube-Fundorte:** `python3 -m werkzeuge.cubekarte` holt Kartenbild und Cube-Fundorte von aion2hub (Altgard)
  nach `~/.local/share/aion2-radar/karten/Altgard/` (nicht im Repo) und setzt die Eichung (aion2hub-Karte:
  1 px = 1 m, Ursprung in der Mitte), Eichen im Spiel ist nicht nötig. Die Fundorte stehen als blasse Punkte
  auf der Karte, die Teleporter mit dem Symbol aus dem Spiel (Name beim Drüberfahren). Ist nur eine Karte
  vorhanden, zeigt das Radar sie von selbst. Altgard liegt fertig unter `karten/Altgard/` im Repo
  (Bild als WebP, 1,5 MB) und wird beim ersten Start in den eigenen Kartenordner kopiert, eine vorhandene
  Karte bleibt. Das Werkzeug braucht man nur für andere Karten oder wenn sich aion2hub ändert.
  **Herkunft:** Kartenbild, Teleporter-Symbol und Marker in `karten/` stammen von aion2hub.com bzw. aus
  AION 2 (NCSoft). Sie fallen nicht unter die GPL dieses Repos.
- **Boss-Warnungen (Kromedes Gier):** Todesmal, Regen des Hasses, Vorhersage nach der Flächenphase,
  Zeitfenster für den nächsten Regen. Widget „Boss-Warnungen“ im Overlay, sichtbar nur während einer Warnung.
  Auf der Seite „Radar“ Dungeon wählen, dann jede Warnung einzeln an/aus und mit/ohne Ton.
  Dort auch die Sprache der Warnungen (Deutsch/Englisch).
  Der Dungeon wird beim Betreten erkannt (Zonenwechsel `0x4002`), sonst am ersten Boss. Es warnen nur Regeln dieses Dungeons.
- **Gruppe auf dem Radar:** Mitspieler als blaue Punkte mit Namen (Position etwa alle 2 s, also grob).
- **Name des Ziels:** Warnungen nennen den markierten Spieler („Todesmal auf Testspieler“).
- **Ansage:** Pro Warnung auf der Seite „Radar“ wählbar: Aus, Piepton oder Ansage (Standard). Gesprochen wird
  lokal mit Piper (`~/.local/share/aion2-radar/piper`, Stimmen Thorsten/Amy), fertige Sätze im Cache
  `~/.cache/aion2-radar/ansagen`. Fehlt Piper, kommt der Piepton.
- **Lernhilfe:** In Dungeons ohne Warnungen erscheint jeder Boss-Cast grau mit Namen aus den A2Tools-Daten.
- **Status auf dir** (`0x382A`): Ignus' Flammenbombe → „Verzögerte Explosion – DU!“ (3 s, danach Feuerpfütze).
  Weitere Effekte in `STATUS_REGELN` (`radar/warnung.py`), IDs aus A2Tools `abnormals`.
- **Boss groggy** (`0xE005`, Stagger-Leiste gebrochen): Ansage in allen Dungeons, etwa 5 s Zeit für vollen Schaden.
- **Dungeon-Restzeit** (`0x6100`) in der Statuszeile unter dem Radar.
- **Feldbosse und Vertraute** (NexBoard-Seite „Radar“, Reiter „Feldbosse und Vertraute“): Respawn-Timer aller gesehenen
  Feldbosse (`0x9101`), Ansage 5 Minuten vorher und beim Respawn (nur aktuelle Karte), lebende Feldbosse
  als lila Raute auf dem Radar. Namen lernt das Radar, sobald ein Boss neben dem Platz erscheint.
  Termine (Riss, Shugo-Fest, Beritra-Luftangriff, Wächterin Kaira, Tages- und Wochen-Reset) in Ortszeit,
  gerechnet in UTC nach jackships/aion2-data. Ansage 5 Minuten vor dem Riss.
  Vertraute (`0x9000`/`0x900D`/`0x9014`): 207 Vertraute mit Art (Cogni/Fera/Natura/Varian), Stufe, Seelen,
  fehlenden Seelen bis zur nächsten Stufe (5/25/75) und den Monstern, die die Seele droppen (Katalog aus
  aion2pettracker, GPL-3.0). Filter nach Stand und Art. Stand in `~/.local/share/aion2-radar/{feldbosse,vertraute}.json`.
- **Lernmodus:** Beim Betreten eines Dungeons startet eine Aufnahme nach `~/.local/share/aion2-radar/mitschnitte/<Dungeon>-<Zeit>.pcap`,
  beim Verlassen stoppt sie (Statuszeile „● REC“), jeder Lauf eine Datei. Abschaltbar auf der Seite „Radar“
  („Dungeons automatisch aufnehmen“), dort auch von Hand starten und stoppen. Auswerten mit
  `python3 -m werkzeuge.lernen mitschnitte/<datei>.pcap`: pro Boss jeder Skill mit Vorlauf bis zum Treffer,
  Toden und dem Cast, der regelmäßig davor kommt.

Start: über das NexBoard-Modul **AION 2 · Radar** (Web-UI, Seite „Radar“). Ist es an, startet der Daemon das Radar
(`RadarDienst`), sobald AION 2 läuft, und beendet es 30 s nach Spielende. Den Stand schickt er etwa fünfmal pro
Sekunde als Overlay-Ereignis `radar`, gezeichnet in `daemon/deckbar_daemon/web/overlay/radar.js`. Auf der Seite
stehen alle Einstellungen, auch der Charaktername. Standardwerte und Warnungsliste stehen in
`radar/standard.json` und `radar/meldungen.json` (liest auch die Seite).

| Datei | Inhalt |
|---|---|
| `radar/protokoll.py` | Varint, LZ4, Frames |
| `radar/mitschnitt.py` | tcpdump, pcap lesen, TCP zusammensetzen |
| `radar/quelle.py` | verbindet Mitschnitt und Zustand |
| `radar/zustand.py` | wertet Nachrichten aus: Cubes, eigene ID, Position, Casts |
| `radar/dienst.py` | RadarDienst: verbindet alles, Ton, Ansagen, Aufnahme, Stand fürs Overlay |
| `radar/warnung.py` | Boss-Regeln, Warnungen, Ansagen |
| `radar/konfig.py` | gemeinsame Einstellungen, Ton bei neuem Cube |
| `radar/uebersicht.py` | Feldbosse, Termine und Vertraute für die Seite, Feldboss-Ansagen |
| `radar/daten.py` | Namen (A2Tools, Vertraute), gespeicherte Zustände |
| `radar/punkte.py` | Spawnpunkte, Eichung, Karten |
| `werkzeuge/cubekarte.py`, `karten/` | Kartenbild, Cube-Fundorte und Teleporter von aion2hub |
| `werkzeuge/auswertung.py` | Kämpfe auswerten: Tode, Ursachen, Vorwarnzeiten |
| `werkzeuge/analyse.py` | Opcode-Statistik eines Mitschnitts |
| `werkzeuge/lernen.py` | Lernmodus: Boss-Skills einer Aufnahme auswerten |
| `werkzeuge/bosse.py` | erzeugt `radar/bosse.json` und `radar/zonen.json` (Boss/Zone -> Dungeon) aus den A2Tools-Daten |

- Kämpfe auswerten: `python3 -m werkzeuge.auswertung mitschnitte/datei.pcap`
- Tests: `python3 -m unittest discover tests`
- Daten: `~/.local/share/aion2-radar/` (Spawnpunkte, Karten, Spawn-Log), Einstellungen `~/.config/aion2-radar.json`.
