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
  „Spieler folgen“ (Ziehen pausiert es, Doppelklick folgt wieder) und die Kartenwahl auf der Seite „Radar“.
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
- **Lernhilfe:** Jeder Cast eines Bosses, zu dem es noch keine Cast-Warnung gibt, erscheint grau mit Namen aus den A2Tools-Daten
  (Schalter „Alle Boss-Casts zeigen“).
- **Status auf dir** (`0x382A`): Ignus' Flammenbombe → „Verzögerte Explosion – DU!“ (3 s, danach Feuerpfütze).
  Weitere Effekte in `STATUS_REGELN` (`radar/warnung.py`), IDs aus A2Tools `abnormals`.
- **Boss groggy** (`0xE005`, Stagger-Leiste gebrochen): Ansage in allen Dungeons, etwa 5 s Zeit für vollen Schaden.
- **Weitere Dungeons** (`radar/mechaniken.json`, 39 Mechaniken; 11 davon aus eigenen Guides: Urugugu Raur-Zeitbombe und -Ansturm, Urahum-Flächen und Tankschlag, Auldor-Linien, -Sturzschlag, -Rundum und -Wirbel, Grimmhorn Kwapo-Donnergrollen, Duanka-Nekromantie und -Seelenrufer): Urugugu (Raur-Konter, Auldor-Sturmstreich,
  Urahum-Gift und -Pfütze), Vakron-Himmelsinsel (Tiere, Thamon-Schilde, Vakron-Male, -Ringe, -Gefängnis), Krao-Höhle
  (Berk), Draupnir (Lakshmi-Reflexion), Grimmhorn (Nuakum-Blutung), Deus (Nazmun-Bombe, Atiel-Kette), Arkanis,
  dazu Ignus' Flammenzone. Auslöser: Boss-Cast, Status auf dir, einem Mitspieler, jedem Spieler oder dem Boss,
  ein Treffer vom Boden (`0x3804`, Pfützen; mehrere Treffer zählen als einer) und die Stagger-Prüfung.
  Mit Folge-Hinweis, wenn es vorbei ist („Abstand halten“). IDs und Zeiten nach
  [xinjalin/glass-cannon](https://github.com/xinjalin/glass-cannon) `gamedata/boss-mechanics.json`
  (MIT, Copyright (c) 2026 Xinjalin), Texte eigene; dort zum Teil nur als Hinweise ungeprüft, selbst bestätigt
  sind Raur `15044501` und Urahum `16051103`. Neue Mechanik = ein Eintrag in `mechaniken.json` plus Schalter in
  `meldungen.json`.
- **Jetzt staggern** (Berk, Bakarma, Atiel): sobald die Stagger-Leiste brechbar wird, nach einer Pause oder wenn sie
  erst spät im Kampf erscheint. Endet mit „Boss groggy“, sonst nach 25 s.
- **Fläche unter dir** (`0x3848`, Boden-Markierung, Aufbau nach glass-cannon): Markiert ein Monster eine Fläche, deren Mittelpunkt höchstens `flaeche_m` (Standard 6 m, in `~/.config/aion2-radar.json`) neben dir liegt, kommt „Fläche unter dir – DU!“ mit Countdown bis zum Einschlag. Größe und Form stehen nicht im Paket, deshalb der feste Abstand. Mehrere Markierungen einer Welle = eine Warnung. Ein Makro kann darauf mit Pause oder Ausweichen reagieren (Gruppe `flaeche`, `/api/radar/kampf`).
- **Berserker-Zeit** (`0x8D21`): Countdown in der Vorschauzeile, solange der Boss im Kampf ist.
- **Wenig LP** (`0x921B`): Mitspieler unter 25 % LP, einmal bis zur Erholung über 50 %. Schalter unter „alle Dungeons“.
- **Cube-Schlüssel:** verbrauchte Schlüssel (`0x363A`, Item 630900003) in der Statuszeile.
- **Mehr Positionsquellen** (ungeprüft, Erkenntnis aus benhighlanderr/Aion2-Hidden-Cube-Radar, dort ohne Lizenz):
  eigener Cast `0x3802` (x/y/z ab Byte 17, im Kampf die häufigste Quelle), Bewegungen `0x3710`–`0x3750`, Eintritt
  `0x3621` (Position ab Byte 16, ID nur geschätzt) und Zonenwechsel `0x561E` (ab Byte 17). Sie zählen nur, wenn sie
  höchstens 30 m neben der letzten Position liegen oder die letzte älter als 10 s ist.
- **Laufrichtung oben** (Schalter auf der Seite „Radar“): dreht das Radar so, dass die Laufrichtung oben ist (aus den
  letzten Metern Weg) statt Norden. Weitere Cube-IDs (ungeprüft): 1000549–1000565, 1300081, 1300082.
- **Dungeon-Restzeit** (`0x6100`) in der Statuszeile unter dem Radar.
- **PvP der Sitzung** (`radar/pvp.py`, Widget „PvP“ im Overlay): Kills und Tode zählt `0x8D04`
  (Tod mit Täter und dessen Namen, nur bei Spielern als Täter), Kills über die eigene Entity oder den
  eigenen Namen (auch Begleiter). Assists, Abyss-Rangpunkte, Rang und Grad kommen aus der eigenen
  Saisonwertung `0x8D57` (JSON mit kill/death/assist_count); das Spiel schickt sie beim Einloggen und
  nach manchen Zonenwechseln, der Server rechnet etwa stündlich neu. Gezeigt wird der Zuwachs seit
  Spielstart bzw. „PvP neu beginnen“. Opcodes und Formate nach dem Desktop-Programm von questlog.gg,
  an eigenen Mitschnitten geprüft; PvP-Kills selbst sind noch nicht live geprüft.
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
- Für eigene Makros auf diesem PC: `GET http://127.0.0.1:8765/api/radar/kampf` gibt `{"groggy": true, "warnungen": [{"gruppe", "titel", "ich", "rest"}]}`: groggy, solange die Stagger-Leiste eines Bosses gebrochen ist (bis eine neue Leiste kommt, höchstens 8 s, hängt nicht an der Warnungsanzeige), dazu die gerade laufenden Warnungen (ohne Lernhilfe; auf der Seite abgeschaltete fehlen auch hier). Gruppen wie in `meldungen.json`. Dazu `boss_effekte` und `eigene_effekte`, je `[{"id", "seit"}]`: Effekte, die gerade auf dem aktuellen Ziel des DPS-Meters bzw. auf dir liegen, aus dem Capture statt aus dem Radar (genauer Anfang und Ende, z. B. Lakshmis Schadensreflexion `16059101`, Präzision/„Letalität“ vom Markierungsschuss `140900171`; Code `nexboard/daemon/deckbar_daemon/boss_effekte.py`). Ohne laufendes Capture leer (`eigene_effekte` dann `null` = unbekannt, ebenso solange die eigene ID fehlt), nach 10 s ohne Treffer am Ziel gilt der Stand als veraltet.
- Tests: `PYTHONPATH=../../proto python3 -m unittest discover tests` (Termine kommen aus `proto/nexproto/termine.py`, im Daemon ist nexproto installiert)
- Daten: `~/.local/share/aion2-radar/` (Spawnpunkte, Karten, Spawn-Log), Einstellungen `~/.config/aion2-radar.json`.
