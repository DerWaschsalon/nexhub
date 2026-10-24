# NexBoard-Modul `aion2.radar`

Stand: 2026-10-25, Branch `nexboard-radar`

## Worum es geht

Das AION-2-Radar von Navonex (Hidden Cubes, Karte, Boss-Warnungen, Feldbosse und Vertraute) liegt
bisher als eigenes Projekt unter `~/Projekte/aion2-radar` und wird von Hand gestartet. Es soll ins
NexBoard umziehen, als eigenes Modul wie DPS-Mitschnitt, Overlay und Runs. Über die NexBoard-Seite
(Web-UI auf `localhost:8765`) wird es ein- und ausgeschaltet, und dort lassen sich alle Einstellungen
vornehmen, die das Radar heute hat.

Vorgabe von Navonex: **so wenig Code wie möglich, so geschrieben, dass jeder ihn versteht.**

## Ziele

- Neues Modul `aion2.radar`, Name „AION 2 · Radar“, Kategorie `games`, eigener Schalter.
- Modul an = der Daemon startet das Radar, **sobald AION 2 läuft**, und beendet es 30 s nach Spielende
  (wie `aion2.overlay`: Abfrage alle 5 s über `aion2_running()`). Modul aus = der Daemon beendet es sofort.
- Eine Modulseite mit allen bestehenden Einstellungen und den Knöpfen für die bestehenden Aktionen.
- Änderungen auf der Seite wirken sofort im laufenden Radar, ohne Neustart.

## Nicht-Ziele

- **Die Fenster bleiben, wie sie sind.** Radar, Karte, Warnfenster und das Fenster „Feldbosse und
  Vertraute“ bleiben eigene PySide6-Fenster. Kein Umbau ins QML-Overlay des NexBoard, keine Ansicht
  der Feldbosse/Vertrauten auf der Webseite.
- Nichts auf der Touch-Leiste (ESP32). (Eigene Entscheidung, die Frage blieb unbeantwortet.)
- Nichts im NexHub (nex-hub.de), keine Daten verlassen den PC.
- Keine neuen Radar-Funktionen. Verhalten und Protokoll-Auswertung bleiben gleich.
- Den Mitschnitt nicht mit `deckbar-capture` zusammenlegen. Das Radar behält sein eigenes `tcpdump`.

## Woran es scheitern würde

- Mehr Code als nötig oder ein neues Framework für die Steuerung.
- Ein Radar, das nach dem Ausschalten weiterläuft, oder zwei Radare gleichzeitig (Ansagen doppelt).
- Mitschnitte (`.pcap`, enthalten Spielernamen), Spawnpunkte, Karten-Screenshots oder Piper-Stimmen
  landen im Repo.

## Was entschieden ist

### Code-Umzug

- `radar/`, `tests/` und `werkzeuge/` aus `~/Projekte/aion2-radar` ziehen nach `nexboard/radar/`
  (Paket `radar` bleibt, Start weiter mit `python3 -m radar`). Ohne Git-Historie des alten Repos.
- `mitschnitte/` kommt nicht mit. Neue Aufnahmen gehen nach `~/.local/share/aion2-radar/mitschnitte/`
  statt in den Projektordner.
- Das Radar läuft mit dem System-Python (`/usr/bin/python3`, PySide6 6.11 ist dort installiert), nicht
  im uv-Umfeld des Daemons. Der Daemon braucht kein PySide6.
- Die Sperrdatei (`schon_offen()` in `radar/__main__.py`) bleibt, damit ein von Hand gestartetes Radar
  nicht doppelt neben dem Modul läuft. `--pcap` zum Abspielen bleibt.
- Der Daemon startet `python3 -m radar --log --name <name>` (wie der bisherige Startbefehl).

### Daemon: neue Datei `deckbar_daemon/radar.py`

- Startet das Radar als Unterprozess (`asyncio.create_subprocess_exec`) mit `stdin=PIPE`, beendet es
  beim Ausschalten (erst `terminate`, nach kurzer Wartezeit `kill`). Stirbt das Radar von selbst,
  zeigt der Status das an. Ein automatischer Neustart passiert nicht.
- Registrierung wie die anderen Module: Eintrag in `MODULES` (`modules.py`), Aufgabe/Hook in
  `server.py`, Seite in `web/js/modules/`, Eintrag in `UI` in `web/js/main.js`.
- Drei Adressen:
  - `GET /api/radar`: Einstellungen (Inhalt von `~/.config/aion2-radar.json`, ergänzt um die
    Standardwerte), Liste der Warnungen je Dungeon, Status (läuft ja/nein, Aufnahme ja/nein).
  - `PUT /api/radar`: mischt die geänderten Werte in die Datei (nur bekannte Schlüssel) und schickt
    danach dem Radar `neu_laden`.
  - `POST /api/radar/befehl`: schickt einen Befehl aus einer festen Liste an das Radar.
- Befehle gehen als eine Textzeile pro Befehl über stdin an das Radar. Feste Liste:
  `neu_laden`, `ton_testen`, `warnung_testen`, `warnung_verschieben`, `karte_zeigen`,
  `karte_ausblenden`, `uebersicht_zeigen`, `aufnahme_start`, `aufnahme_stopp`.

### Radar: kleine Ergänzung

- Ein Leser für stdin (zum Beispiel `QSocketNotifier` auf fd 0 oder ein Thread mit Qt-Signal), der
  jede Zeile auf die bestehende Funktion abbildet (`ton_abspielen`, `warnung.test`,
  `warnung.verschieben_umschalten`, `karte.show/hide`, `_uebersicht_zeigen`,
  `quelle.aufnahme_starten/stoppen`).
- `neu_laden` liest die Datei neu und aktualisiert das gemeinsame dict aus `konfig_laden()` **an
  Ort und Stelle** (alle Fenster halten dieselbe Referenz). Danach übernehmen die Fenster Werte, die
  sie nur beim Start setzen (Größe, Deckkraft, Kartendeckkraft usw.).
- Seine Aufnahme meldet das Radar dem Daemon als Zeile auf stdout (`aufnahme an` / `aufnahme aus`).
  So kann der Status „● REC“ anzeigen.
- Die Warnungsliste `DUNGEONS` und `ALLE_DUNGEONS` aus `radar/warnung.py` wandert in
  `radar/meldungen.json`, die Standardwerte (`STANDARD` aus `radar/overlay.py` plus die verstreuten
  `k.get`-Standards `karte_deckkraft`, `karte_folgen`, `warn_an`, dazu `name: "Navonex"`) nach
  `radar/standard.json`. Radar und Daemon lesen dieselben Dateien. So muss der Daemon kein
  PySide6 importieren und die Liste steht nur an einer Stelle.

### Die Seite `web/js/modules/aion2-radar.js`

Aufbau wie `aion2-overlay.js` (Karten, `settingsRow`, `sw`, `select`, `saver`):

- **Status:** läuft/beendet, Aufnahme ● REC. Ein/Aus über den normalen Modul-Schalter.
- **Radar:** Ton bei neuem Cube (`ton`), Knopf „Ton testen“, Größe (`groesse`), Reichweite
  (`reichweite`, Stufen 50/100/150/300/600), Ausrichtung drehen (`drehung`, 0/90/180/270),
  Spiegeln (`spiegeln`), Deckkraft (`deckkraft`).
- **Karte:** Knöpfe „Zeigen“ und „Ausblenden“, Deckkraft (`karte_deckkraft`), Spieler folgen
  (`karte_folgen`).
- **Boss-Warnungen:** an/aus (`warn_an`), Sprache (`sprache`, de/en), Dungeon für die Liste
  (`meldungen_dungeon`), je Warnung Aus/Piepton/Ansage (`warnton`) und Anzeigen ja/nein
  (`meldung_aus`), Dungeons automatisch aufnehmen (`aufnahme_auto`), Knöpfe „Aufnahme starten/
  stoppen“, „Testen“, „Position ändern“.
- **Feldbosse und Vertraute:** Feldboss-Ansage (`feldboss_ansage`), Knopf „Fenster öffnen“.
- **Charaktername** (neu, `name`, vorbelegt „Navonex“, auf der Seite änderbar): ersetzt die
  Umgebungsvariable `AION2_CHAR`. Wirkt beim nächsten Start, dafür Knopf „Radar neu starten“.

### Bleibt in den Fenstern

- Das Rechtsklick-Menü des Radars bleibt unverändert. Seite und Menü schreiben dieselbe Datei. (Eigene
  Entscheidung: Das Menü zu entfernen wäre zusätzlicher Code.)
- Karte laden, Karte wählen, Eichen, Spawnpunkte löschen bleiben im Kartenfenster (brauchen Klicks
  auf der Karte oder einen Dateidialog).
- Fensterpositionen (`x`, `y`, `karte_x` …, `warn_x`, `warn_y`) stellt man weiter durch Ziehen ein. Sie
  stehen nicht auf der Seite.

### Gleichzeitiges Schreiben

Radar und Daemon schreiben dieselbe Datei. Der Daemon liest sie vor jedem Speichern neu und ändert
nur die Schlüssel, die die Seite schickt. Danach lädt das Radar sie per `neu_laden` neu. Speichert das
Radar selbst (Ziehen, Rechtsklick-Menü), schreibt es seinen Stand, der dann schon die Werte der Seite
enthält.

## Was dem Bauenden überlassen ist

- Ob der stdin-Leser per `QSocketNotifier` oder Thread läuft.
- Wie die Fenster ihre Startwerte nach `neu_laden` übernehmen (je Fenster eine kleine Funktion oder
  eine gemeinsame).
- Tests: die bestehenden Radar-Tests laufen weiter (`python3 -m unittest discover` in
  `nexboard/radar`). Dazu ein Daemon-Test für `PUT /api/radar` (nur bekannte Schlüssel, Mischen) und
  einer für die Befehlsliste.
- Text der Modulbeschreibung in `MODULES` und das Icon (Material Design, zum Beispiel `radar`).

## Rahmen

- Repo `DerWaschsalon/nexhub` gehört auch Fabio (gamunex). Die Arbeit geht als PR an `main`, Navonex
  merged selbst. Commits mit `301618926+Navonex@users.noreply.github.com`.
- Das Repo kann öffentlich werden. Das Radar liest den Server-Verkehr nur passiv mit, das
  Erkennungsrisiko bleibt aber. `radar/vertraute.json` stammt aus aion2pettracker (GPL-3.0), das passt
  zur GPL-3 des NexBoard.
- Nach dem Umzug: `~/.local/bin/aion2-radar` zeigt auf `nexboard/radar` oder wird entfernt, das alte
  Projekt `~/Projekte/aion2-radar` bleibt als Sicherung liegen, bis das Modul läuft.
