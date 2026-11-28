# Parse-Plakette im DPS-Meter: Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein bis zwei Sekunden nach einem Boss-Kill steht im A2Tools-Meter des NexBoard-Overlays an jedem Namen der EU-Parse (bei Gildenmitgliedern dazu der Gildenwert) in den Farbstufen des Hubs.

**Architecture:** Der Hub bekommt eine lesende Geräte-Route, die für einen einzelnen getöteten Boss mit derselben Rechnung wie `_parses` die Parses liefert. Der Daemon ruft sie auf, sobald der RunPublisher einen neu gespeicherten, getöteten Bosskampf einliest, und schickt das Ergebnis als Overlay-Ereignis `dps-parses`. Das Meter-Widget hängt die Plakette per DOM in die Zeilen des A2Tools-iframes, wie heute den Namenseffekt.

**Tech Stack:** FastAPI + SQLAlchemy (Hub, pytest), Python asyncio + aiohttp (Daemon, pytest), Vanilla-JS-Overlay im Daemon-Web.

**Spec:** `docs/superpowers/specs/2026-11-28-meter-parse-plakette-design.md`

## Global Constraints

- Hub-Route: `POST /api/parses/device/fight`, Auth `CurrentDevice`, nur lesend, nichts speichern.
- Eingabe höchstens 24 Spieler; Antwort `{"players": {"<name>": {"eu": int|null, "guild": int|null}}}` (Modell `BossParse`).
- Daemon: nur wenn gekoppelt (`settings.token`), nur getötete Bosskämpfe, ein Aufruf je Kampf, Zeitlimit 3 s, Fehler nur ins Log.
- Ohne Hub oder bei Fehler: Meter wie heute, keine Plakette, kein Fehler sichtbar.
- Farbstufen exakt wie `PARSE_TIERS` in `run_image.py`: 100 gold `#d4b45a`, ≥99 `#e268a8`, ≥95 `#ff8000`, ≥75 `#a750ee`, ≥50 `#3d86f0`, ≥25 `#2fbf3a`, sonst `#9aa0a6`.
- Plakette verschwindet bei Kampfbeginn (`dps_active` wird true).
- Commits mit `301618926+Navonex@users.noreply.github.com`, Trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Derselbe Name zweimal im Kampf (Relog): stärkerer Eintrag zählt, wie in `_parses`. Test in Task 1.
2. Spieler ohne Klasse oder Boss ohne Rangliste: Eintrag mit `eu: null`, kein 500. Test in Task 1.
3. Hub antwortet langsam oder mit 404 (älterer Hub): kein Ereignis, Publisher läuft weiter. Test in Task 2.
4. Kampf, der beim Einlesen schon in `done` ist (Neustart, alte History): kein Aufruf. Test in Task 2.
5. A2Tools zeichnet Zeilen neu: Plakette bleibt dran, wird nicht doppelt eingefügt. Prüfung in Task 3.

---

### Task 1: Hub-Route für einen einzelnen Kill

**Files:**
- Modify: `hub/api/nexhub_api/modules/parses/routes.py` (Rechnung aus `_parses` herausziehen, neue Route, Doku-Kopf ergänzen)
- Test: `hub/api/tests/test_parses.py`

**Interfaces:**
- Produces: `POST /api/parses/device/fight`, Body-Modell `FightIn(mob: int, players: list[FightPlayer])` mit `FightPlayer(name: str ≤64, cls: str|None, dps: float ≥0)`, `players` max 24. Antwort-Modell `FightParses(players: dict[str, BossParse])`.
- Interne Hilfe: `async def _boss_parses(request, db, mob: int, players: list[dict], cps: dict[str, int]) -> dict[str, Parse]` — von `_parses` je getötetem Boss und von der neuen Route genutzt. `_combat_power` bekommt `run: Run | None` (None: nur jüngste bekannte Kampfkraft).

- [ ] **Step 1: Failing tests schreiben**

```python
def test_parse_fuer_einen_kill_des_nexboards(client, as_user, database_url):
    from .test_devices import bearer, pair
    token = pair(client, as_user(MEMBER))
    add_board(database_url, 1, "ranger", [100, 200, 300, 400])
    body = {"mob": 1, "players": [{"name": "A", "cls": "ranger", "dps": 150},
                                  {"name": "A", "cls": "ranger", "dps": 350},   # Relog: stärkerer zählt
                                  {"name": "B", "cls": None, "dps": 500},       # ohne Klasse
                                  {"name": "C", "cls": "ranger", "dps": 0}]}
    r = client.post("/api/parses/device/fight", json=body, headers=bearer(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"players": {"A": {"eu": 75, "guild": None}, "B": {"eu": None, "guild": None},
                                    "C": {"eu": 0, "guild": None}}}

def test_kill_parse_braucht_geraet_und_grenzen(client, as_user, database_url):
    from .test_devices import bearer, pair
    token = pair(client, as_user(MEMBER))
    assert client.post("/api/parses/device/fight", json={"mob": 1, "players": []}).status_code == 401
    many = [{"name": f"P{i}", "cls": "ranger", "dps": 1} for i in range(25)]
    assert client.post("/api/parses/device/fight", json={"mob": 1, "players": many},
                       headers=bearer(token)).status_code == 422

def test_kill_parse_nimmt_juengste_kampfkraft(client, as_user, database_url):
    """Kein Run: EU im CP-Bereich der zuletzt bekannten Momentaufnahme."""
    # Board wie test_eu_nur_im_cp_bereich, Momentaufnahme A mit 250_000 aus einem alten Run,
    # Erwartung eu == 50 für dps 200.
```

- [ ] **Step 2: Tests laufen lassen, sie scheitern**

Run: `cd hub/api && uv run pytest tests/test_parses.py -k "kill" -q`
Expected: 3 failed (404 auf die Route)

- [ ] **Step 3: Umsetzen**

`_boss_parses` aus dem Schleifenkörper von `_parses` bilden (Boards, Gilde, Benchmarks für genau diesen `mob` laden; bestehendes Verhalten der Run-Route unverändert). Route lädt `cps = await _combat_power(db, None, names)` und gibt nur `eu`/`guild` je Name zurück.

- [ ] **Step 4: Alle Parse-Tests grün, ruff sauber**

Run: `cd hub/api && uv run pytest tests/test_parses.py -q && uv run ruff check .`
Expected: alle grün, keine Lint-Fehler

- [ ] **Step 5: Commit** `Hub: Parses für einen einzelnen Kill des NexBoards (claude-navonex)`

---

### Task 2: Daemon fragt nach jedem Kill und meldet `dps-parses`

**Files:**
- Modify: `nexboard/daemon/deckbar_daemon/runs.py` (`RunPublisher.kill_listeners`, Aufruf in `poll`)
- Modify: `nexboard/daemon/deckbar_daemon/hub.py` (`fight_parses`)
- Modify: `nexboard/daemon/deckbar_daemon/app.py` (Verdrahtung, Ereignis)
- Modify: `nexboard/daemon/deckbar_daemon/overlay.py` (`"dps-parses"` in `RETAINED`)
- Test: `nexboard/daemon/tests/test_runs.py`, `nexboard/daemon/tests/test_hub.py`

**Interfaces:**
- Consumes: Task 1 Route.
- Produces:
  - `RunPublisher.kill_listeners: list[Callable[[Fight], Awaitable[None]]]`, aufgerufen in `poll` für jeden neu eingelesenen Kampf mit `f.killed` und `f.id not in self.done`, vor `tracker.add`. Ein Listener-Fehler wird geloggt und hält `poll` nicht auf.
  - `HubClient.fight_parses(fight: Fight) -> dict[str, tuple[int | None, int | None]]` — leer, wenn nicht gekoppelt, kein Spieler, HubError, Status ≠ 200 oder Antwort kaputt; Zeitlimit `KILL_PARSES_TIMEOUT_S = 3`. Body aus `fight.players` (`name`, `cls`, `dps = dmg / (duration_ms/1000)`), höchstens 24 nach DPS.
  - Overlay-Ereignis `dps-parses`, Payload `{"fight": fight.id, "players": {name: [eu, guild]}}`.

- [ ] **Step 1: Failing tests**

```python
# test_runs.py
async def test_kill_meldet_sich_einmal(tmp_path):
    """Getöteter Bosskampf → kill_listeners genau einmal; nicht getötet oder schon in done → nichts."""

# test_hub.py
async def test_parses_nach_einem_kill(tmp_path):
    # fake Hub antwortet {"players": {"Morgan": {"eu": 87, "guild": 60}, "X": "kaputt"}}
    # → {"Morgan": (87, 60)}; Body hatte mob, 1–24 Spieler, Bearer-Token
async def test_kill_parses_ohne_hub_leer(tmp_path):
    # nicht gekoppelt → {} ohne Aufruf; Hub 404 → {}; Hub hängt > 3 s → {} nach dem Zeitlimit
```

- [ ] **Step 2: Laufen lassen, scheitern**

Run: `cd nexboard/daemon && uv run pytest tests/test_runs.py tests/test_hub.py -k "kill" -q`
Expected: failed

- [ ] **Step 3: Umsetzen** (Signaturen oben). In `app.py`: `self.runs.kill_listeners.append(self._kill_parses)` mit `_kill_parses(f)`: `p = await self.hub.fight_parses(f)`; nur wenn `p`: `await self.overlay.publish("dps-parses", {"fight": f.id, "players": {n: list(v) for n, v in p.items()}})`.

- [ ] **Step 4: Alle Daemon-Tests grün, ruff + mypy wie in CI**

Run: `cd nexboard/daemon && uv run pytest -q`
Expected: alle grün (bisher 300 + neue), 7 übersprungen

- [ ] **Step 5: Commit** `NexBoard: Parses direkt nach dem Kill holen (claude-navonex)`

---

### Task 3: Plakette im Meter-Widget

**Files:**
- Modify: `nexboard/daemon/deckbar_daemon/web/overlay/widgets/meter.js`
- Create: `nexboard/daemon/deckbar_daemon/web/overlay/parses.css` (Stil, wird wie `effects.css` ins iframe gelegt)

**Interfaces:**
- Consumes: Ereignis `dps-parses` aus Task 2, `dps` (`dps_active`).
- Produces: `events: ["dps", "dps-parses"]`; Funktion `markParses(doc)` neben `markOwnRow`; Element `<span class="dbx-parse dbx-tier-<stufe>">87<small>60</small></span>` direkt nach `.item .content .name`. Stufen-Klassen `gold|pink|orange|purple|blue|green|gray` nach den Grenzen der Global Constraints.

- [ ] **Step 1: Umsetzen.** Zustand `parses = null`. `onEvent("dps-parses", d)` setzt ihn und ruft `markParses`; `onEvent("dps", d)` mit `dps_active` true setzt `parses = null` und entfernt alle `.dbx-parse`. `markParses` läuft im bestehenden MutationObserver mit, prüft vorher, ob die Plakette schon passt (nicht doppelt einfügen, keine Endlosschleife durch eigene DOM-Änderung). Name in der Zeile über `textContent.trim()` gegen die Schlüssel der Antwort. Ohne EU-Wert keine Plakette; Gildenwert nur, wenn nicht null.

- [ ] **Step 2: Prüfen im Browser.** Testseite im Sitzungsordner mit einem iframe, das die A2Tools-Zeilenstruktur (`.list > .item > .content > .name`) nachbildet; Overlay-Code mit gefälschten Ereignissen füttern (Playwright). Erwartet: Plakette an „Morgan“ (87, lila; 60 klein), keine an Namen ohne Wert; nach Neuzeichnen der Liste weiter genau eine Plakette; nach `dps_active: true` keine mehr.

- [ ] **Step 3: Im echten Meter prüfen** (am PC, NexBoard auf diesem Zweig, `systemctl --user restart deckbar.service`): nach einem Boss-Kill erscheint die Plakette. Falls kein Kill möglich: Ereignis über die Overlay-Testschnittstelle schicken und Bildschirmfoto machen.

- [ ] **Step 4: Commit** `NexBoard: Parse-Plakette im DPS-Meter (claude-navonex)`

---

### Abschluss

- [ ] `README`/Doku-Kopf der Parse-Route und `nexboard/README.md` (Abschnitt Overlay) um die Plakette ergänzen, im Commit von Task 3.
- [ ] Push, PR gegen `main` mit Screenshot, Fabio in Issue #69 informieren (Hub-Route berührt sein Parse-Modul nicht, nur `routes.py` im Parse-Modul von Navonex).
