# NexBoard-Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das AION-2-Radar zieht als Modul `aion2.radar` ins NexBoard, Ein/Aus und alle Einstellungen über die NexBoard-Seite.

**Architecture:** Der Daemon startet das Radar (`/usr/bin/python3 -m radar`) als Unterprozess, solange das Modul an ist und AION 2 läuft (30 s Nachlauf). Einstellungen liegen weiter in `~/.config/aion2-radar.json`. Der Daemon schreibt sie und schickt dem Radar Befehle als Textzeilen über stdin. Das Radar meldet seine Aufnahme als Zeile auf stdout.

**Tech Stack:** Python 3 (asyncio, aiohttp, pytest im Daemon; PySide6 + unittest im Radar), Vanilla-JS-Modulseite.

**Spec:** `docs/superpowers/specs/2026-10-25-nexboard-radar-design.md`

## Global Constraints

- So wenig Code wie möglich, für jeden verständlich. Deutsch benannt wie der bestehende Radar-Code, Daemon-Code im Stil des Daemons.
- Keine `.pcap`, Spawnpunkte, Karten oder Piper-Stimmen ins Repo.
- Radar läuft mit `/usr/bin/python3`, der Daemon importiert kein PySide6.
- Fenster und Rechtsklick-Menü des Radars bleiben unverändert.
- Commits mit `301618926+Navonex@users.noreply.github.com`.

## Review Focus

- Modul aus, während das Radar hängt: Prozess muss trotzdem weg (terminate, nach 3 s kill).
- Radar über Rechtsklick > Beenden geschlossen: Status zeigt „beendet“, Befehle liefern 409 statt Absturz.
- `PUT /api/radar` mit unbekanntem Schlüssel oder falschem Typ: 400, Datei bleibt unverändert.
- Kaputte oder fehlende `aion2-radar.json`: Seite zeigt Standardwerte, Speichern legt die Datei an.
- Seite speichert, während das Radar gerade selbst speichert (Ziehen): Werte der Seite bleiben erhalten (Daemon liest vor dem Schreiben neu).

---

### Task 1: Radar-Code ins Repo umziehen

**Files:**
- Create: `nexboard/radar/` (Kopie von `~/Projekte/aion2-radar/{radar,tests,werkzeuge,README.md}`, ohne `__pycache__`, ohne `mitschnitte/`)
- Create: `nexboard/radar/radar/meldungen.json`
- Create: `nexboard/radar/radar/standard.json`
- Modify: `radar/quelle.py:14`, `radar/warnung.py:102-132`, `radar/overlay.py:22-25`, `radar/karte.py`, `radar/warnung.py:232`

- [ ] Kopieren, `.gitignore`-Eintrag `nexboard/radar/mitschnitte/` ergänzen.
- [ ] `AUFNAHMEN = Path.home() / ".local" / "share" / "aion2-radar" / "mitschnitte"`.
- [ ] `STANDARD` nach `radar/standard.json` (plus `karte_deckkraft: 0.9`, `karte_folgen: false`, `warn_an: true`, `name: "Navonex"`), `overlay.py` lädt sie; `k.get("karte_deckkraft", 0.9)` usw. werden zu `k[...]`.
- [ ] `ALLE_DUNGEONS` und `DUNGEONS` nach `radar/meldungen.json` (`{"alle": {...}, "dungeons": {...}}`), in `warnung.py` per `json.loads` laden.
- [ ] `cd nexboard/radar && python3 -m unittest discover tests` → alle grün.
- [ ] Commit „radar: Code aus aion2-radar übernommen“.

### Task 2: Radar nimmt Befehle an

**Files:**
- Create: `nexboard/radar/radar/befehle.py`
- Modify: `radar/overlay.py` (`konfig_neu_laden()`), `radar/__main__.py`, `radar/quelle.py` (Aufnahme melden)
- Test: `nexboard/radar/tests/test_befehle.py`

**Interfaces:**
- Produces: Befehlszeilen `neu_laden`, `ton_testen`, `warnung_testen`, `warnung_verschieben`, `karte_zeigen`, `karte_ausblenden`, `uebersicht_zeigen`, `aufnahme_start`, `aufnahme_stopp`. Ausgabe auf stdout: `aufnahme an` / `aufnahme aus`.

- [ ] Test `test_neu_laden_aendert_dasselbe_dict`: `k = konfig_laden()`, Datei mit `{"groesse": 300}` schreiben (KONFIG auf tmp gepatcht), `konfig_neu_laden()` → `k["groesse"] == 300` und `konfig_laden() is k`.
- [ ] Test `test_unbekannter_befehl_wird_ignoriert`: `ausfuehren("quatsch", aktionen)` wirft nicht, ruft nichts auf; `ausfuehren("ton_testen", {"ton_testen": f})` ruft `f` einmal.
- [ ] Test rot laufen lassen.
- [ ] `konfig_neu_laden() -> dict` in `overlay.py`: Datei neu lesen, `_konfig.clear(); _konfig.update({**STANDARD, **neu})`.
- [ ] `befehle.py`: `ausfuehren(zeile: str, aktionen: dict[str, Callable]) -> None` und `starten(aktionen) -> None` (Thread liest `sys.stdin`, gibt jede Zeile per Qt-Signal in den GUI-Thread). Bei EOF von stdin (Daemon weg) nichts tun.
- [ ] In `__main__.py` nur ohne `--pcap` starten. `neu_laden` ruft `konfig_neu_laden()` und übernimmt danach Startwerte: Radar `setWindowOpacity`, `resize(g, g + 34)`; Karte `setWindowOpacity(k["karte_deckkraft"])`, `folgen`; `zentrale.an = k["warn_an"]`.
- [ ] `quelle.aufnahme_starten/stoppen` geben `print("aufnahme an"/"aufnahme aus", flush=True)` aus.
- [ ] Tests grün, Commit „radar: Befehle über stdin“.

### Task 3: Daemon-Modul `aion2.radar`

**Files:**
- Create: `nexboard/daemon/deckbar_daemon/radar.py`
- Modify: `modules.py` (`MODULES`), `server.py` (`_register_modules`, Routen)
- Test: `nexboard/daemon/tests/test_radar.py`

**Interfaces:**
- Produces: `class Radar(konfig: Path = ~/.config/aion2-radar.json, ordner: Path = nexboard/radar)` mit `watch()` (Modul-Aufgabe), `info() -> dict`, `speichern(patch: dict) -> dict`, `befehl(name: str)`.
- `GET /api/radar` → `{"einstellungen": {...}, "meldungen": <meldungen.json>, "laeuft": bool, "aufnahme": bool}`
- `PUT /api/radar` → wie GET; `POST /api/radar/befehl {"befehl": "..."}` → `{"ok": true}`.

- [ ] Tests: `test_speichern_mischt_und_behaelt_fremde_schluessel` (Datei hat `x: 5`, Patch `{"groesse": 300}` → beides drin); `test_speichern_lehnt_unbekannte_schluessel_ab` (`{"quatsch": 1}` → `ValueError`, Datei unverändert; Positionen wie `x` sind auch nicht erlaubt); `test_speichern_lehnt_falschen_typ_ab` (`{"groesse": "gross"}` → `ValueError`); `test_kaputte_datei_gibt_standard` (Datei `{{` → `info()["einstellungen"]["groesse"] == 260`); `test_befehl_ohne_radar_ist_runtimeerror`; `test_unbekannter_befehl_ist_valueerror`; `test_watch_startet_und_beendet` (statt Radar `python3 -c "import sys; print('aufnahme an', flush=True); sys.stdin.read()"`, nach Start `laeuft` und `aufnahme` true, nach Abbruch der Aufgabe ist der Prozess weg).
- [ ] Rot laufen lassen.
- [ ] Standardwerte aus `nexboard/radar/radar/standard.json`. Erlaubt sind alle Schlüssel daraus außer den Fensterpositionen `x`, `y`; der Typ kommt vom Standardwert (`int` für `float` erlaubt, `bool` nicht für `int`). Keine zweite Liste. Befehl `neustart` erledigt der Daemon selbst (beenden, neu starten, wenn das Spiel läuft).
- [ ] `watch()`: alle 5 s `aion2_running()` (über `spiel_laeuft`, im Test ersetzbar); Spiel da → `_starten()`, 30 s weg → `_beenden()`. `_starten()`: Prozess starten (`/usr/bin/python3 -m radar --log` + `--name` wenn gesetzt, `cwd=ordner`, `stdin=PIPE, stdout=PIPE`), stdout-Zeilen lesen (Aufnahme-Status), in `finally` terminate, nach 3 s kill. Endet das Radar selbst: `laeuft = False`, Aufgabe endet.
- [ ] `speichern()`: prüfen, Datei neu lesen, mischen, atomar schreiben (`_atomic_write` aus `config.py`), Befehl `neu_laden` senden falls läuft.
- [ ] `MODULES`: `ModuleInfo("aion2.radar", "AION 2 · Radar", "games", "radar", "Hidden Cubes, Karte, Boss-Warnungen, Feldbosse und Vertraute in eigenen Fenstern. Liest den Server-Verkehr passiv mit (tcpdump).", tags=("AION 2", "Desktop"))`.
- [ ] `server.py`: `self.radar = Radar()`, `m.register("aion2.radar", self.radar.watch, status=lambda: {...})`, drei Routen nach dem Muster der Overlay-Routen (400 bei `ValueError`, 409 bei `RuntimeError`).
- [ ] `cd nexboard/daemon && uv run pytest -q` → alles grün. Commit „daemon: Modul aion2.radar“.

### Task 4: Modulseite

**Files:**
- Create: `nexboard/daemon/deckbar_daemon/web/js/modules/aion2-radar.js`
- Modify: `web/js/main.js` (Import + Eintrag `"aion2.radar"` in `UI`)

- [ ] Seite nach Muster `aion2-overlay.js`: Karten Status, Radar, Karte, Boss-Warnungen, Feldbosse und Vertraute, Charakter, Felder und Knöpfe genau wie in der Spec. Speichern über `saver("PUT", "/api/radar", …)`, Knöpfe über `api("POST", "/api/radar/befehl", {befehl})`. Warnungsliste aus `meldungen.dungeons[meldungen_dungeon]` + `meldungen.alle`, je Zeile Anzeigen (`meldung_aus`) und Aus/Piepton/Ansage (`warnton`).
- [ ] Daemon aus dem Worktree starten (`uv run python -m deckbar_daemon` mit eigenem Port), Seite im Browser öffnen, jede Einstellung einmal ändern und in `aion2-radar.json` nachsehen, Knöpfe gegen laufendes Radar prüfen.
- [ ] Commit „web: Seite für das Radar“.

### Task 5: Abschluss

- [ ] `nexboard/README.md`: Radar in die Modulliste. `nexboard/radar/README.md`: Start über das Modul, Pfad der Mitschnitte.
- [ ] `~/.local/bin/aion2-radar` auf `~/Projekte/nexhub/nexboard/radar` zeigen lassen (erst nach Merge), bis dahin unverändert.
- [ ] Gesamtprüfung durch einen Reviewer, dann PR an `main` (Navonex merged).
