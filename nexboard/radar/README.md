# AION2 Radar

Radar für AION 2 unter Linux (KDE Wayland, Spiel unter Proton), als drei Module des NexBoard: **AION 2 · Radar**,
**AION 2 · Boss-Warnungen** und **AION 2 · Feldbosse**. Liest den Server-Verkehr passiv per `tcpdump` mit (`cap_net_raw`), greift nicht ins Spiel ein.
Es läuft im NexBoard-Daemon und zeigt sich als Widgets im NexBoard-Overlay (Radar, Boss-Warnungen,
Karte), kein eigenes Programm und keine eigenen Fenster.

tcpdump einrichten: `sudo pacman -S tcpdump && sudo setcap cap_net_raw,cap_net_admin=eip /usr/bin/tcpdump`
Ein Update von tcpdump löscht die Capability wieder (dann kein Cube, keine Warnung, Radar-Seite zeigt „Fehler: tcpdump
beendet“). Dagegen der pacman-Hook: `sudo install -Dm644 tcpdump-cap.hook /etc/pacman.d/hooks/tcpdump-cap.hook`

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
  Auf der Seite „Warnungen“ eine Voreinstellung wählen (Aus · Nur Wichtiges · Alles); unter „Erweitert“
  Dungeon wählen, dann jede Warnung einzeln an/aus und mit/ohne Ton. Die Sprache der Warnungen
  (Deutsch/Englisch) ist die allgemeine unter System → Einstellungen.
  Der Dungeon wird beim Betreten erkannt (Zonenwechsel `0x4002`), sonst am ersten Boss. Es warnen nur Regeln dieses Dungeons.
- **Gruppe auf dem Radar:** Mitspieler als blaue Punkte mit Namen (Position etwa alle 2 s, also grob).
- **Name des Ziels:** Warnungen nennen den markierten Spieler („Todesmal auf Testspieler“).
- **Ansage:** Pro Warnung auf der Seite „Radar“ wählbar: Aus, Piepton oder Ansage (Standard). Gesprochen wird
  lokal mit Piper (`~/.local/share/aion2-radar/piper`, Stimmen Thorsten/Amy), fertige Sätze im Cache
  `~/.cache/aion2-radar/ansagen`. Fehlt Piper, kommt der Piepton.
- **Lernhilfe:** Jeder Cast eines Bosses, zu dem es noch keine Cast-Warnung gibt, erscheint grau mit Namen aus den A2Tools-Daten
  (Schalter „Alle Boss-Casts zeigen“).
- **Status auf dir** (`0x382A`): Ignus' Flammenbombe → „Verzögerte Explosion – DU!“ (3 s, danach Feuerpfütze).
  Weitere Effekte als Einträge mit `wann.art: effekt` in `mechanics.json`, IDs aus A2Tools `abnormals`.
- **Boss groggy** (`0xE005`, Stagger-Leiste gebrochen): Ansage in allen Dungeons, etwa 5 s Zeit für vollen Schaden.
- **Weitere Dungeons** (`aion2/data/mechanics.json`, 32 Mechaniken; 10 davon aus eigenen Guides: Urugugu Raur-Zeitbombe und -Ansturm, Urahum-Flächen und Tankschlag, Auldor-Linien, -Sturzschlag, -Rundum und -Wirbel, Grimmhorn Kwapo-Donnergrollen, Duanka-Nekromantie): Urugugu (Raur-Konter, Auldor-Sturmstreich,
  Urahum-Gift und -Pfütze), Vakron-Himmelsinsel (Tiere, Thamon-Versteinerung, Vakron-Male), Krao-Höhle
  (Berk), Draupnir (Bakarma), Grimmhorn (Nuakum-Blutung), Deus (Nazmun-Bombe, Atiel-Kette), Arkanis,
  dazu Ignus' Flammenzone. Auslöser: Boss-Cast, Status auf dir, einem Mitspieler, jedem Spieler oder dem Boss,
  ein Treffer vom Boden (`0x3804`, Pfützen; mehrere Treffer zählen als einer) und die Stagger-Prüfung.
  Thamon-Schilde, Lakshmi-Reflexion, Vakron-Ringe und -Gefängnis, Rafflesia und Seelenrufer kommen jetzt aus den
  Boss-Ansagen (unten). Mit Folge-Hinweis, wenn es vorbei ist („Abstand halten“). IDs und Zeiten nach
  [xinjalin/glass-cannon](https://github.com/xinjalin/glass-cannon) `gamedata/boss-mechanics.json`
  (MIT, Copyright (c) 2026 Xinjalin), Texte eigene; dort zum Teil nur als Hinweise ungeprüft, selbst bestätigt
  sind Raur `15044501` und Urahum `16051103`. Neue Mechanik = ein Eintrag in `mechanics.json`; ihr Schalter auf
  der Seite entsteht daraus (`meldung`). Auch die älteren Regeln (Feuertempel, Albtraum, Urugugu) stehen dort,
  mit `zugleich`/`plan` für Vorhersagen und `fenster` für Kromedes Regen.
- **Boss-Ansagen** (`aion2/callouts.py`, Daten `callouts.json`, ein Schalter je Boss): wie das Plugin
  „Boss Callouts“ von [taengu/A2Tools-Plugins](https://github.com/taengu/A2Tools-Plugins) (GPL-3.0, Zeilen
  (c) NCSOFT), 202 Ansagen von 54 Bossen, auch Ludra, Kelch von Muspel, Läuterungsstätte der Korrosion, Roter
  Spiegel und Versunkener Lebenstempel. Gesagt wird, was das Spiel zeigt: die Zeile des Bosses, bei Skills mit
  Cast-Leiste schon beim Beginn der Leiste (`0x3809`) mit Countdown. Geprüfte Mechaniken (Thamon, Lakshmi,
  Vakron, Talisra) bringen eine kurze Anweisung, einen Countdown über die echte Dauer des Buffs (`0x382A`, Ende
  `0x382C`) und danach „Wieder angreifen“; bei Vakrons Sprung piept es je Welle (`0x3803`), Talisras Speere
  erscheinen als Reihe („Dunkel → Dunkel → Licht“). Buffs, die jedes Monster bekommen kann (Raserei), zählen
  erst, wenn das Wesen einen Skill dieses Bosses eingesetzt hat. Auf der NexBoard-Seite: Art der Ansage (kurze
  Ansage und Satz des Bosses, nur kurze Ansage, nur Satz), Piepton bei jeder Welle und je Boss eine aufklappbare
  Liste seiner Rufe: Haken (ganz aus, auch der Countdown), eigene Worte (statt des Rufs gesagt und gezeigt,
  `own_words` in `aion2.warnings.yaml`), zurück zur Vorgabe und ▶ (spielt den Ruf wie im Kampf, die
  Phase auf 5 s gekürzt, Befehl `ansage_testen`). Bedientexte wie im Plugin. Gesprochen wird
  nacheinander: höchstens zwei Sätze warten, eine Warnung bricht eine noch laufende Boss-Zeile ab. Nach einem
  Spielpatch `STAND` in `werkzeuge/ansagen.py` erhöhen und `python3 -m werkzeuge.ansagen` ausführen.
- **Jetzt staggern** (Berk, Bakarma, Atiel): sobald die Stagger-Leiste brechbar wird, nach einer Pause oder wenn sie
  erst spät im Kampf erscheint. Endet mit „Boss groggy“, sonst nach 25 s.
- **Blickrichtung aus der Minikarte** (`aion2/minimap.py`): Der Server schickt die eigene Blickrichtung nie und die Position nur bei Sprint, Sprung oder Kampf. Darum liest das Radar die Minikarte direkt aus dem Spielfenster (X11, `python-xlib`): Die Blickrichtung ist die Mitte zwischen den beiden weißen Linien des Sichtfelds. Einstellung `minimap: [x, y, Breite, Höhe]` (in `aion2.radar.yaml`) in Pixeln des Spielfensters, quadratisch und mittig auf dem Pfeil (leer = aus).
- **Fläche unter dir** (`0x3848`, Boden-Markierung, Aufbau nach glass-cannon): Markiert ein Monster eine Fläche, deren Mittelpunkt höchstens `area_m` (Standard 6 m, in `aion2.warnings.yaml`) neben dir liegt, kommt „Fläche unter dir – DU!“ mit Countdown bis zum Einschlag. Größe und Form stehen nicht im Paket, deshalb der feste Abstand. Mehrere Markierungen einer Welle = eine Warnung. Gruppe `flaeche`, auch über `/api/radar/kampf`.
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
- **Tode** (`0x8D04`, CharDie; Name nach dem Desktop-Programm von questlog.gg): jeder Tod mit Skill und, bei einem
  Spieler als Täter, dessen Namen. Daraus kommt die Todesursache im Run. PvP zählt das Radar nicht mehr, das macht
  das A2Tools-Plugin PvP Tracker.
- **Feldbosse** (NexBoard-Seite „Termine“): Respawn-Timer aller gesehenen
  Feldbosse (`0x9101`), Ansage 5 Minuten vorher und beim Respawn (nur aktuelle Karte), lebende Feldbosse
  als lila Raute auf dem Radar. Namen lernt das Radar, sobald ein Boss neben dem Platz erscheint.
  Die festen Termine (Riss, Shugo-Fest, Beritra-Luftangriff, Wächterin Kaira, Tages- und Wochen-Reset)
  zeigt das Modul Termine, gerechnet in UTC nach jackships/aion2-data (`nexproto.termine`). Ansage 5
  Minuten vor dem Riss.
  Stand in `~/.local/share/aion2-radar/feldbosse.json`. Die Vertraute-Tabelle ist gestrichen, das zeigt der
  Pet Soul Tracker (eigenes Plugin-Fenster); die Opcodes liest das Radar bis Schritt 7 des Umbaus noch mit.
- **Lernmodus:** Beim Betreten eines Dungeons startet eine Aufnahme nach `~/.local/share/aion2-radar/mitschnitte/<Dungeon>-<Zeit>.pcap`,
  beim Verlassen stoppt sie (Statuszeile „● REC“), jeder Lauf eine Datei. Standardmäßig aus; einschalten unter
  Warnungen → Erweitert („Lernmodus: Dungeons aufnehmen“), dort auch von Hand starten und stoppen. Auswerten mit
  `python3 -m werkzeuge.lernen mitschnitte/<datei>.pcap`: pro Boss jeder Skill mit Vorlauf bis zum Treffer,
  Toden und dem Cast, der regelmäßig davor kommt.

Start: über die NexBoard-Module **AION 2 · Radar** (Seite „Radar & Karte“), **AION 2 · Boss-Warnungen** (Seite „Warnungen“) und **AION 2 · Feldbosse** (Seite „Termine“), einzeln schaltbar. Ist eines an, startet der Daemon das Radar
(`RadarService`), sobald AION 2 läuft, und beendet es 30 s nach Spielende. Den Stand schickt er etwa fünfmal pro
Sekunde als Overlay-Ereignis `radar`, gezeichnet von den Widgets `cube.js`, `map.js` und `warnings.js` unter `daemon/deckbar_daemon/web/overlay/widgets/`. Auf den Seiten
stehen alle Einstellungen des Radars; Charaktername und Sprache kommen aus den allgemeinen Einstellungen
(der Daemon gibt sie dem Dienst mit). Jedes der drei Module hat seine Einstellungen in
`~/.config/deckbar/aion2.<radar|warnings|field_bosses>.yaml` (Modelle mit Standardwerten in `aion2/settings.py`,
Route `/api/m/<Modul>/settings`); die frühere `~/.config/aion2-radar.json` wird beim ersten Start übernommen. Die Schalter der Warnungen ergeben sich aus `mechanics.json` und `callouts.json`
(`rules.switches()`, liest auch die Seite).

Der Code des Radars liegt im Daemon unter `daemon/deckbar_daemon/` (dieser Ordner hält nur noch Karten,
Werkzeuge und den Goldtest):

| Datei | Inhalt |
|---|---|
| `core/packets/` | Kernbaustein: Varint, LZ4, Frames (`frames.py`), pcap und TCP (`tcp.py`), Paketquellen (`source.py`: `PcapSource`, `TcpdumpSource`) und je Opcode eine Nachricht, die ihre Nutzdaten einmal dekodiert (`messages.py`). Abnehmer melden sich mit der Klasse an: `source.on(Cast, handler)` |
| `core/speech.py` | Sprachausgabe (Piper) und Töne |
| `aion2/world.py` | `World`: eigene ID, Position und Laufrichtung, Zone, Dungeon, Namen, Bosse |
| `aion2/cubes.py`, `party.py`, `field_bosses.py`, `stagger.py` | je ein Thema mit seinem Stand und seinen Signalen |
| `aion2/fight.py` | was im Kampf passiert, als Signale: Casts, Leisten, Wellen, Effekte, Treffer, Flächen, Tode |
| `aion2/rules.py`, `data/mechanics.json` | Regeln der Warnungen, Schalter der Seite, englische Texte |
| `aion2/warning_board.py` | die Warn-Anzeige: laufende Warnungen, Vorhersagen, was gesprochen wird |
| `aion2/mechanic_warnings.py`, `cast_trainer.py`, `stagger_calls.py`, `combat_aids.py` | die Auslöser: Mechaniken, Lernhilfe, „Jetzt staggern“/groggy, Kampfhilfen |
| `aion2/callouts.py`, `data/callouts.json` | Boss-Ansagen |
| `aion2/spawn_points.py`, `maps.py`, `minimap.py` | Spawnpunkte, Karten mit Eichung, Blickrichtung aus der Minikarte |
| `aion2/settings.py` | Einstellungen der drei Module mit Standardwerten, Übersetzung der früheren Datei |
| `aion2/service.py` | `RadarService`: verdrahtet alles, Takt, Stand fürs Overlay |
| `radar.py`, `modules/radar.py` | Anbindung an den Daemon: Start mit dem Spiel, Einstellungen, Routen |
| `werkzeuge/cubekarte.py`, `karten/` | Kartenbild, Cube-Fundorte und Teleporter von aion2hub |
| `werkzeuge/auswertung.py` | Kämpfe auswerten: Tode, Ursachen, Vorwarnzeiten |
| `werkzeuge/analyse.py` | Opcode-Statistik eines Mitschnitts |
| `werkzeuge/lernen.py` | Lernmodus: Boss-Skills einer Aufnahme auswerten |
| `werkzeuge/bosse.py` | erzeugt `bosses.json` und `zones.json` (Boss/Zone -> Dungeon) in `aion2/data/` aus den A2Tools-Daten |

- Kämpfe auswerten: `python3 -m werkzeuge.auswertung mitschnitte/datei.pcap`
- Für andere Programme auf diesem PC: `GET http://127.0.0.1:8765/api/radar/kampf` gibt `{"groggy": true, "warnungen": [{"gruppe", "titel", "ich", "rest"}]}`: groggy, solange die Stagger-Leiste eines Bosses gebrochen ist (bis eine neue Leiste kommt, höchstens 8 s, hängt nicht an der Warnungsanzeige), dazu die gerade laufenden Warnungen (ohne Lernhilfe; auf der Seite abgeschaltete fehlen auch hier). Gruppen wie in `mechanics.json`. Dazu `boss_effekte` und `eigene_effekte`, je `[{"id", "seit"}]`: Effekte, die gerade auf dem aktuellen Ziel des DPS-Meters bzw. auf dir liegen, aus dem Capture statt aus dem Radar (genauer Anfang und Ende, z. B. Lakshmis Schadensreflexion `16059101`, Präzision/„Letalität“ vom Markierungsschuss `140900171`; Code `nexboard/daemon/deckbar_daemon/boss_effekte.py`). Ohne laufendes Capture leer (`eigene_effekte` dann `null` = unbekannt, ebenso solange die eigene ID fehlt), nach 10 s ohne Treffer am Ziel gilt der Stand als veraltet.
- Tests: die des Radars laufen mit denen des Daemons (`cd ../daemon && uv run python -m pytest -q`). Hier liegt der
  Goldtest: `../daemon/.venv/bin/python -m pytest -q tests`. Er gehört (`tests/test_gold.py`): Er spielt jeden Mitschnitt aus
  `~/.local/share/aion2-radar/mitschnitte/` durch den RadarService und durch `deckbar-capture --replay` und vergleicht
  das Ergebnis mit den Referenzen in `~/.local/share/aion2-radar/gold/`. Referenzen schreiben:
  `python -m werkzeuge.gold --schreiben radar` bzw. `--schreiben capture`. Sie bleiben auf dem Rechner, weil sie
  Namen anderer Spieler enthalten; ohne Mitschnitte wird der Test übersprungen.
- Daten: `~/.local/share/aion2-radar/` (Spawnpunkte, Karten, Spawn-Log), Einstellungen `~/.config/deckbar/aion2.*.yaml`.
