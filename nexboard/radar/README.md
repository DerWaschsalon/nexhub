# AION2 Radar

Eigenständige Overlays für AION 2 unter Linux (KDE Wayland, Spiel unter Proton). Liest den
Server-Verkehr passiv per `tcpdump` mit (`cap_net_raw`), greift nicht ins Spiel ein.

- **Cube-Radar:** rundes Radar, Ton bei neuem Hidden Cube. Unter dem Radar Entfernung, Höhe und wie lange der Cube schon steht (Spawnzeit vom Server). Öffnet ihn gerade jemand, wird er orange und der Name steht unten. Ziehen = verschieben, Mausrad = Reichweite,
  Rechtsklick = Menü.
- **Karte:** Screenshot der Ingame-Karte, an 2–3 Stellen geeicht (hinlaufen, auf den eigenen Standort klicken).
  Zeigt gesehene Spawnpunkte, aktive Cubes und die eigene Position. Rechtsklick aufs Radar > Karte.
- **Cube-Route:** `python3 -m werkzeuge.cubekarte` holt Kartenbild und Cube-Fundorte von aion2hub (Altgard)
  nach `~/.local/share/aion2-radar/karten/Altgard/` und legt einen kurzen Rundweg an (nicht im Repo). Im
  Kartenfenster Karte „Altgard“ wählen, Eichen ist nicht nötig (aion2hub-Karte: 1 px = 1 m, Ursprung in
  der Mitte). Dann stehen die nächsten drei Fundorte
  gold mit 1-2-3 auf der Karte, der Rest blass. Ein Fundort gilt als erledigt, sobald man nah genug dran war
  (Abstand auf der NexBoard-Seite, Standard 60 m), auch wenn dort gerade kein Cube lag. Rechtsklick auf die
  Karte: Punkt überspringen, Route neu starten. `--neu` legt Route und Eichung neu an.
- **Boss-Warnungen (Kromedes Gier):** Todesmal, Regen des Hasses, Vorhersage nach der Flächenphase,
  Zeitfenster für den nächsten Regen. Rechtsklick aufs Radar > Boss-Warnungen.
  Unter „Meldungen auswählen …“ Dungeon wählen, dann jede Warnung einzeln an/aus und mit/ohne Ton.
  Dort auch die Sprache der Warnungen (Deutsch/Englisch).
  Der Dungeon wird beim Betreten erkannt (Zonenwechsel `0x4002`), sonst am ersten Boss. Es warnen nur Regeln dieses Dungeons.
- **Gruppe auf dem Radar:** Mitspieler als blaue Punkte mit Namen (Position etwa alle 2 s, also grob).
- **Name des Ziels:** Warnungen nennen den markierten Spieler („Todesmal auf Testspieler“).
- **Ansage:** Pro Warnung im Meldungen-Fenster wählbar: Aus, Piepton oder Ansage (Standard). Gesprochen wird
  lokal mit Piper (`~/.local/share/aion2-radar/piper`, Stimmen Thorsten/Amy), fertige Sätze im Cache
  `~/.cache/aion2-radar/ansagen`. Fehlt Piper, kommt der Piepton.
- **Lernhilfe:** In Dungeons ohne Warnungen erscheint jeder Boss-Cast grau mit Namen aus den A2Tools-Daten.
- **Status auf dir** (`0x382A`): Ignus' Flammenbombe → „Verzögerte Explosion – DU!“ (3 s, danach Feuerpfütze).
  Weitere Effekte in `STATUS_REGELN` (`radar/warnung.py`), IDs aus A2Tools `abnormals`.
- **Boss groggy** (`0xE005`, Stagger-Leiste gebrochen): Ansage in allen Dungeons, etwa 5 s Zeit für vollen Schaden.
- **Dungeon-Restzeit** (`0x6100`) in der Statuszeile unter dem Radar.
- **Feldbosse und Vertraute** (Rechtsklick > „Feldbosse und Vertraute …“): Respawn-Timer aller gesehenen
  Feldbosse (`0x9101`), Ansage 5 Minuten vorher und beim Respawn (nur aktuelle Karte), lebende Feldbosse
  als lila Raute auf dem Radar. Namen lernt das Radar, sobald ein Boss neben dem Platz erscheint.
  Termine (Riss, Shugo-Fest, Beritra-Luftangriff, Wächterin Kaira, Tages- und Wochen-Reset) in Ortszeit,
  gerechnet in UTC nach jackships/aion2-data. Ansage 5 Minuten vor dem Riss.
  Vertraute (`0x9000`/`0x900D`/`0x9014`): 207 Vertraute mit Art (Cogni/Fera/Natura/Varian), Stufe, Seelen,
  fehlenden Seelen bis zur nächsten Stufe (5/25/75) und den Monstern, die die Seele droppen (Katalog aus
  aion2pettracker, GPL-3.0). Filter nach Stand und Art. Stand in `~/.local/share/aion2-radar/{feldbosse,vertraute}.json`.
- **Lernmodus:** Beim Betreten eines Dungeons startet eine Aufnahme nach `~/.local/share/aion2-radar/mitschnitte/<Dungeon>-<Zeit>.pcap`,
  beim Verlassen stoppt sie (Statuszeile „● REC“), jeder Lauf eine Datei. Abschaltbar im Meldungen-Fenster
  („Dungeons automatisch aufnehmen“). Von Hand: Rechtsklick > Boss-Warnungen > Aufnahme. Auswerten mit
  `python3 -m werkzeuge.lernen mitschnitte/<datei>.pcap`: pro Boss jeder Skill mit Vorlauf bis zum Treffer,
  Toden und dem Cast, der regelmäßig davor kommt.

Start: über das NexBoard-Modul **AION 2 · Radar** (Web-UI, Seite „Radar“). Ist es an, startet der Daemon das Radar,
sobald AION 2 läuft, und beendet es 30 s nach Spielende. Auf der Seite stehen alle Einstellungen, auch der
Charaktername. Von Hand geht weiterhin `python3 -m radar --name <Charakter> [--pcap datei.pcap]` in diesem Ordner,
ein zweites Live-Radar verhindert die Sperrdatei.

Befehle vom Daemon kommen als Textzeile über stdin (`radar/befehle.py`), Standardwerte und Warnungsliste
stehen in `radar/standard.json` und `radar/meldungen.json` (liest auch der Daemon).

| Datei | Inhalt |
|---|---|
| `radar/protokoll.py` | Varint, LZ4, Frames |
| `radar/mitschnitt.py` | tcpdump, pcap lesen, TCP zusammensetzen |
| `radar/quelle.py` | verbindet Mitschnitt und Zustand |
| `radar/zustand.py` | wertet Nachrichten aus: Cubes, eigene ID, Position, Casts |
| `radar/warnung.py` | Boss-Regeln und Warnfenster |
| `radar/overlay.py` | Radar-Fenster, gemeinsame Einstellungen |
| `radar/uebersicht.py` | Fenster Feldbosse und Vertraute, Feldboss-Ansagen |
| `radar/daten.py` | Namen (A2Tools, Vertraute), gespeicherte Zustände |
| `radar/punkte.py`, `radar/karte.py` | Spawnpunkte, Eichung, Kartenfenster |
| `radar/route.py`, `werkzeuge/cubekarte.py` | Cube-Route, Import von aion2hub |
| `werkzeuge/auswertung.py` | Kämpfe auswerten: Tode, Ursachen, Vorwarnzeiten |
| `werkzeuge/analyse.py` | Opcode-Statistik eines Mitschnitts |
| `radar/befehle.py` | Befehle vom NexBoard-Daemon (stdin) |
| `werkzeuge/lernen.py` | Lernmodus: Boss-Skills einer Aufnahme auswerten |
| `werkzeuge/bosse.py` | erzeugt `radar/bosse.json` und `radar/zonen.json` (Boss/Zone -> Dungeon) aus den A2Tools-Daten |

- Kämpfe auswerten: `python3 -m werkzeuge.auswertung mitschnitte/datei.pcap`
- Tests: `python3 -m unittest discover tests`
- Daten: `~/.local/share/aion2-radar/` (Spawnpunkte, Karten, Spawn-Log), Einstellungen `~/.config/aion2-radar.json`.
