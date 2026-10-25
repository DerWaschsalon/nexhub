# Build-Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Knopf „Build-Check“ an einem Armory-Charakter vergleicht ihn Feld für Feld mit den 15 besten Spielern seiner Klasse (EU, ähnliche Kampfkraft, aus Abyss Logs) und zeigt Ampel, Empfehlungen und „Zuerst:“ auf einer teilbaren Seite.

**Architecture:** Der Klick startet einen Lauf im Hintergrund (Muster `Armory.refresh`): Abyss-Logs-Rangliste → Gruppe wählen → Server über die NC-Suche → Profile mit Gegenständen (`NC.snapshot(..., items=True)`) → reine Auswertung (`evaluation.py`) → Ergebnis-JSON in `build_checks`. Die Web-Seite fragt den Stand ab, bis er fertig ist; Teilen wie beim Vergleich (`/c/<token>`).

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, httpx, pytest (`hub/api`); SvelteKit 2 / Svelte 5, TypeScript (`hub/web`).

**Spec:** `docs/superpowers/specs/2026-10-22-build-check-design.md`

## Global Constraints

- Code-Stil aus `CLAUDE.md`: so wenig Code wie möglich, keine Dopplungen, Kommentare auf Deutsch (warum, nicht was), PEP 8 mit Typangaben, `npm run check` ohne Fehler und Warnungen.
- Kein Abruf im Hintergrund ohne Klick; kein PNG.
- Keine Namen der Top-Spieler in Datenbank, API-Antwort oder Seite; nur Zählungen.
- Gruppe: Region `eu`, eigene Klasse, Kämpfe ab 30 s, Kampfkraft ±15 % um die eigene, je Name die beste Platzierung, die besten **15**.
- Ein neuer Check höchstens alle 10 Minuten je Charakter; pro Charakter wird nur der letzte gespeichert.
- Abyss Logs: `https://api.abysslogs.com/v1`, `leaderboards?region=eu&class=<Anzeigename>&boss=<mobCode>&limit=100`, `bosses?region=eu`.
- Commits mit `301618926+Navonex@users.noreply.github.com`, Tests vor jedem Commit: `cd hub/api && uv run pytest -q`, `cd hub/web && npm run check`.

## Review Focus

- Eigener Charakter ohne Momentaufnahme (nie abgerufen, `fehler`): Start mit 422 und klarer Meldung, kein Lauf.
- Weniger als 15 passende Spieler (seltene Klasse, sehr niedrige oder hohe Kampfkraft): ab 5 auswerten und „Vergleich mit N Spielern“ zeigen, darunter Status `fehler` mit „Zu wenige Vergleichsspieler“.
- Abyss Logs nicht erreichbar oder Format geändert: Status `fehler` mit Meldung, das vorige Ergebnis bleibt sichtbar.
- Neustart des Hubs mitten im Lauf: ein Check, der länger als 15 Minuten `läuft`, gilt als abgebrochen und darf neu gestartet werden.
- Name in mehreren EU-Servern oder gar nicht auffindbar: über Klasse und nächstliegende Kampfkraft auflösen, sonst überspringen; der nächste Name rückt nach.

---

### Task 1: Auswertung (rein, ohne Netz und Datenbank)

**Files:**
- Create: `hub/api/nexhub_api/evaluation.py`
- Test: `hub/api/tests/test_evaluation.py`

**Interfaces:**
- Consumes: Momentaufnahme in einer Sprache (Format aus `aion2.NC.snapshot`, Englisch).
- Produces:
  - `fields(snapshot: dict) -> dict[tuple[str, str, str], float | str]` – Schlüssel `(bereich, platz, feld)`.
  - `evaluate(own: dict, group: list[dict]) -> dict` mit `{"size": int, "fields": list[Field], "todo": list[Field]}`, wobei `Field = {"area", "slot", "key", "kind": "number"|"choice", "mine", "median": float|None, "common": [{"value", "count"}], "better": int, "light": "green"|"yellow"|"red"}`.

Felder, die `fields()` liefert (fehlt etwas: Zahl 0, Auswahl `"—"`):
- `("profile", "", "combat_power")`, `("profile", "", "item_level")` – Zahl
- `("stats", "", <stat type>)` – Zahl, ohne `ItemLevel`
- je Gegenstand `("equipment", <slot_name>, …)`: `grade` Auswahl, `enchant`, `exceed`, `stones` (Anzahl) Zahl; `set` Auswahl (nur wenn `detail.set` da); Vorhandensein als 0/1 je Name: `sub:<name>`, `stone:<name>`, `godstone:<name>`, `skill:<name>`
- `("daevanion", <board name>, "open_nodes")` – Zahl
- `("skills", <skill name>, "level")` – Zahl
- `("titles", <category>, "name")`, `("wing", "", "name")`, `("pet", "", "name")` – Auswahl; `("wing", "", "enchant")` – Zahl

Regeln für `evaluate` (Spec „Vergleich und Empfehlungen“, verbindlich):
- Ausgewertet werden alle Schlüssel des eigenen Charakters **plus** alle 0/1-Schlüssel (`sub:`, `stone:`, `godstone:`, `skill:`) und Skill-Stufen, die mindestens ein Drittel der Gruppe hat.
- Zahl: `median` der Gruppe, `better` = Anzahl mit größerem Wert; grün wenn `mine >= median`, rot wenn `better > 2/3 · size`, sonst gelb.
- Auswahl: `common` = die zwei häufigsten Werte mit Anzahl; grün wenn `mine` darunter, gelb wenn mindestens 2 der Gruppe denselben Wert wie `mine` haben, sonst rot; `better` = Anzahl der häufigsten Wahl.
- `todo` = die 5 nicht-grünen Felder mit dem größten `better`, bei Gleichstand Ausrüstung vor dem Rest.

- [ ] **Step 1: Write the failing tests**

```python
# Gruppe aus erfundenen Momentaufnahmen; helper snap(cp=…, enchant=…, subs=[…], grade=…) baut das Format aus aion2.py
def test_zahl_ampel_und_besser():
    group = [snap(enchant=15)] * 10 + [snap(enchant=12)] * 5
    f = field(evaluate(snap(enchant=10), group), "equipment", "MainHand", "enchant")
    assert (f["median"], f["better"], f["light"]) == (15, 15, "red")
    f = field(evaluate(snap(enchant=12), group), "equipment", "MainHand", "enchant")
    assert (f["better"], f["light"]) == (10, "yellow")
    assert field(evaluate(snap(enchant=15), group), "equipment", "MainHand", "enchant")["light"] == "green"

def test_auswahl_haeufigste_zwei():
    group = [snap(grade="Epic")] * 9 + [snap(grade="Unique")] * 4 + [snap(grade="Rare")] * 2
    f = field(evaluate(snap(grade="Rare"), group), "equipment", "MainHand", "grade")
    assert f["common"] == [{"value": "Epic", "count": 9}, {"value": "Unique", "count": 4}]
    assert (f["light"], f["better"]) == ("yellow", 9)
    assert field(evaluate(snap(grade="Unique"), group), "equipment", "MainHand", "grade")["light"] == "green"

def test_zusatzwert_fehlt_nur_wenn_ein_drittel_ihn_hat():
    group = [snap(subs=["Attack Speed"])] * 12 + [snap(subs=["Move Speed"])] * 3
    keys = {(f["slot"], f["key"]) for f in evaluate(snap(subs=[]), group)["fields"]}
    assert ("MainHand", "sub:Attack Speed") in keys and ("MainHand", "sub:Move Speed") not in keys

def test_todo_fuenf_nach_besser_ohne_gruene():
    result = evaluate(weak_snap(), strong_group())
    assert len(result["todo"]) == 5 and all(f["light"] != "green" for f in result["todo"])
    assert [f["better"] for f in result["todo"]] == sorted((f["better"] for f in result["todo"]), reverse=True)

def test_fehlende_felder_sind_null():
    assert fields({"profile": {}, "stats": [], "equipment": [], "skills": [], "daevanion": [], "titles": {}})[
        ("profile", "", "combat_power")] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hub/api && uv run pytest -q tests/test_evaluation.py`
Expected: FAIL, `ModuleNotFoundError: nexhub_api.evaluation`

- [ ] **Step 3: Implement `fields` and `evaluate` in `hub/api/nexhub_api/evaluation.py`**

Median über `statistics.median`, Häufigkeit über `collections.Counter.most_common(2)`. Eine kleine Funktion je Bereich für `fields` (Profil, Werte, Ausrüstung, Daevanion, Skills, Titel/Flügel/Begleiter), eine je Art für `evaluate` (Zahl, Auswahl).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hub/api && uv run pytest -q tests/test_evaluation.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/api/nexhub_api/evaluation.py hub/api/tests/test_evaluation.py
git commit -m "hub: Auswertung für den Build-Check (Ampel, Empfehlungen, Zuerst)"
```

---

### Task 2: Abyss Logs und Auswahl der Gruppe

**Files:**
- Create: `hub/api/nexhub_api/abysslogs.py`
- Create: `hub/api/tests/fake_abyss.py`
- Modify: `hub/api/tests/conftest.py` (`FakeDiscord.abyss = FakeAbyss()`, Host `api.abysslogs.com` dorthin, wie `NC_HOSTS`)
- Test: `hub/api/tests/test_abysslogs.py`

**Interfaces:**
- Produces:
  - `HOST = "api.abysslogs.com"`, `class AbyssError(Exception)`
  - `abyss_class(cls: str) -> str` – Hub-Klasse → Anzeigename bei Abyss Logs: `"spiritmaster" → "Elementalist"`, sonst `cls.capitalize()`.
  - `async top_bosses(http: httpx.AsyncClient) -> list[int]` – `mobCode` der Bosse mit der höchsten Stufe (`category == "Transcendence"`, höchste Zahl in `tier`).
  - `async leaderboard(http: httpx.AsyncClient, cls: str, boss: int) -> list[dict]` – Einträge (`playerName`, `classHint`, `combatPower`, `dps`, `combatDuration`).
  - `pick_group(entries: list[dict], own_cp: int) -> list[dict]` – rein: `combatDuration >= 30`, Kampfkraft in `[0.85·own_cp, 1.15·own_cp]`, je `playerName` der Eintrag mit höchstem `dps`, absteigend nach `dps`, **ohne** Begrenzung auf 15 (Task 3 nimmt so viele, bis 15 aufgelöst sind).
  - Fehler (Netz, Status ≥ 400, kein JSON, fehlende Felder) → `AbyssError` mit kurzer deutscher Meldung.

- [ ] **Step 1: Write the failing tests**

```python
def test_auswahl():
    entries = [e("A", cp=100_000, dps=90_000), e("A", cp=100_000, dps=95_000),  # doppelt: bester zählt
               e("B", cp=140_000, dps=99_000),                                # zu stark
               e("C", cp=110_000, dps=80_000, duration=0.01),                  # Müll
               e("D", cp=90_000, dps=70_000)]
    assert [x["playerName"] for x in pick_group(entries, own_cp=100_000)] == ["A", "D"]
    assert pick_group(entries, own_cp=100_000)[0]["dps"] == 95_000

def test_klasse():
    assert (abyss_class("ranger"), abyss_class("spiritmaster")) == ("Ranger", "Elementalist")

def test_bosse_und_rangliste(fake_http):  # fake_http: httpx.AsyncClient über FakeAbyss
    assert asyncio.run(top_bosses(fake_http)) == [2350709, 2340601]   # Werte aus fake_abyss.bosses()
    rows = asyncio.run(leaderboard(fake_http, "Ranger", 2350709))
    assert rows[0]["playerName"] == "Bogenheld" and "class=Ranger" in fake_abyss.last_query

def test_fehler_wird_abysserror(fake_http):
    fake_abyss.routes["/v1/leaderboards"] = 500
    with pytest.raises(AbyssError):
        asyncio.run(leaderboard(fake_http, "Ranger", 2350709))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hub/api && uv run pytest -q tests/test_abysslogs.py`
Expected: FAIL, `ModuleNotFoundError: nexhub_api.abysslogs`

- [ ] **Step 3: Implement `abysslogs.py` and `fake_abyss.py`**

`FakeAbyss` nach dem Muster von `FakeNC` (`routes` je Test überschreibbar, `calls`), Antworten im echten Format: `bosses()` mit zwei Transcendence-Bossen „Stage 4“ und einem „Stage 2“, `leaderboard()` `{entries, total, page, limit}` mit `size` (Standard 20) erfundenen Namen „Bogenheld“, „Bogenheld2“ … und Kampfkraft um 123_000 (passend zu `fake_nc.info`). Dazu in `FakeNC` (Task 3 braucht es): `cp_for: dict[str, int]` (Kampfkraft je characterId im Profil), `snapshot_ids` und `item_ids` (abgefragte characterIds).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd hub/api && uv run pytest -q tests/test_abysslogs.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/api/nexhub_api/abysslogs.py hub/api/tests/fake_abyss.py hub/api/tests/conftest.py hub/api/tests/test_abysslogs.py
git commit -m "hub: Abyss-Logs-Rangliste und Auswahl der Vergleichsgruppe"
```

---

### Task 3: Lauf, Tabelle, API und Teilen

**Files:**
- Create: `hub/api/nexhub_api/buildcheck.py`
- Create: `hub/api/nexhub_api/migrations/versions/0009_build_checks.py`
- Modify: `hub/api/nexhub_api/models.py` (Klasse `BuildCheck` am Ende)
- Modify: `hub/api/nexhub_api/main.py` (`app.state.buildcheck = BuildCheck(app.state.sessionmaker, nc, app.state.http)` neben der Armory)
- Modify: `hub/api/nexhub_api/routes/armory.py` (Endpunkte unten; beim Austragen `BuildCheck`-Zeile mit löschen wie `Comparison`)
- Modify: `hub/api/nexhub_api/routes/public.py` (`GET /api/public/check/{token}`)
- Modify: `hub/api/tests/conftest.py` (`build_checks` in die Postgres-Aufräumliste)
- Modify: `hub/README.md` (Abschnitt Armory: Build-Check, Endpunkte, Abyss Logs inoffiziell)
- Test: `hub/api/tests/test_buildcheck.py`

**Interfaces:**
- Consumes: `evaluate`, `fields` (Task 1); `top_bosses`, `leaderboard`, `pick_group`, `abyss_class`, `AbyssError` (Task 2); `NC.search`, `NC.snapshot`, `characters.fill`, `aion2.localized`; `Shared` aus `routes/runs.py`; `ShareLink`-Muster aus dem Vergleich.
- Produces:
  - Tabelle `build_checks`: `id`, `character_id` (FK `characters`, CASCADE, unique), `status` (`läuft`/`fertig`/`fehler`), `progress` (int, Profile fertig), `error` (String 200, nullable), `result` (JSON, nullable), `share_token` (String 32, unique, nullable), `started_at`, `finished_at`.
  - `class BuildCheck(sessionmaker, nc: NC, http: httpx.AsyncClient)` mit `running: set[int]`, `async run(character_id: int) -> None` (wirft nie; Fehler landen als `status="fehler"`, `result` bleibt).
  - `GROUP = 15`, `MIN_GROUP = 5`, `STALE = timedelta(minutes=15)`.
  - `POST /api/armory/{id}/check` → 202 `{"started": true}`; 422 ohne Momentaufnahme, 409 läuft (und nicht älter als `STALE`), 429 innerhalb 10 Minuten seit `started_at`, 503 ausgeschaltet.
  - `GET /api/armory/{id}/check` → `CheckOut {status, progress, size: int|None, error, result, started_at, finished_at, share_url}`; 404 ohne Check.
  - `POST /api/armory/{id}/check/share` / `DELETE …/share` → `Shared` (wer eingetragen hat oder ein Admin, wie Austragen).
  - `GET /api/public/check/{token}` → `{name, cls, class_name, data, result, finished_at}` (eigener Charakter wie `Side` im Vergleich, ohne Besitzer), `noindex`.

Ablauf von `run` (verbindlich):
1. Armory-Momentaufnahme älter als 10 Minuten → `fill(nc, row, …, items=True)` wie `Armory.refresh`.
2. `cp = row.combat_power`; Einträge aller `top_bosses` für `abyss_class(row.cls)` sammeln, `pick_group(entries, cp)`.
3. Für jeden Kandidaten, bis `GROUP` Profile da sind: `NC.search(name, "eu", row.cls)` → genaue Namensgleichheit (casefold); bei mehreren das Profil mit `combat_power` am nächsten an der Rangliste; `NC.snapshot(server_id, character_id, "en", items=True)`; nach jedem Profil `progress` speichern. `NotFound`/`NCError` beim Kandidaten → überspringen.
4. Weniger als `MIN_GROUP` → `fehler` „Zu wenige Vergleichsspieler“. Sonst `result = evaluate(localized(row.data, "en"), profiles)`, `status="fertig"`; Profile verwerfen.

- [ ] **Step 1: Write the failing tests** (Fixtures wie `test_armory.py`: `login`, `NEW`, `ORIGIN`, `db_run`; Gruppe über `FakeAbyss` und `FakeNC.rows`)

```python
def test_check_laeuft_und_zeigt_ergebnis(make_client, fake):
    c = login(make_client, fake, MEMBER); cid = add(c)
    assert c.post(f"/api/armory/{cid}/check", headers=ORIGIN).status_code == 202
    d = c.get(f"/api/armory/{cid}/check").json()          # TestClient: Hintergrundlauf ist fertig
    assert d["status"] == "fertig" and d["size"] == 15 and len(d["result"]["todo"]) == 5
    assert "Bogenheld" not in json.dumps(d)                  # keine Namen der Top-Spieler

def test_sperre_und_ohne_daten(make_client, fake, database_url):
    c = login(make_client, fake, MEMBER); cid = add(c)
    c.post(f"/api/armory/{cid}/check", headers=ORIGIN)
    assert c.post(f"/api/armory/{cid}/check", headers=ORIGIN).status_code == 429
    no_data = add(c, fail=True)                              # Profil 500 → keine Momentaufnahme
    assert c.post(f"/api/armory/{no_data}/check", headers=ORIGIN).status_code == 422

def test_zu_wenige_und_abyss_weg_behalten_altes_ergebnis(make_client, fake, database_url):
    c = login(make_client, fake, MEMBER); cid = add(c)
    c.post(f"/api/armory/{cid}/check", headers=ORIGIN); age_check(database_url, cid, minutes=11)
    fake.abyss.routes["/v1/leaderboards"] = 500
    c.post(f"/api/armory/{cid}/check", headers=ORIGIN)
    d = c.get(f"/api/armory/{cid}/check").json()
    assert d["status"] == "fehler" and d["error"] and d["result"]["todo"]
    fake.abyss.routes.pop("/v1/leaderboards"); fake.abyss.size = 3; age_check(database_url, cid, minutes=11)
    c.post(f"/api/armory/{cid}/check", headers=ORIGIN)
    assert "Zu wenige" in c.get(f"/api/armory/{cid}/check").json()["error"]

def test_haengender_lauf_darf_neu(make_client, fake, database_url):
    c = login(make_client, fake, MEMBER); cid = add(c)
    set_check(database_url, cid, status="läuft", started_minutes_ago=20)
    assert c.post(f"/api/armory/{cid}/check", headers=ORIGIN).status_code == 202

def test_name_mehrdeutig_naechste_kampfkraft(make_client, fake):
    # zwei „Bogenheld“ (Rangliste: cp 123_000) auf zwei Servern; das Profil von Server 2302 hat 123_456
    # (fake_nc.info), das von 2312 antwortet mit 90_000 → genommen wird 2302
    fake.nc.rows += [search_row("Bogenheld", server=2302, cid="a%3D"), search_row("Bogenheld", server=2312, cid="b%3D")]
    fake.nc.cp_for = {"b=": 90_000}
    c = login(make_client, fake, MEMBER); cid = add(c)
    c.post(f"/api/armory/{cid}/check", headers=ORIGIN)
    assert fake.nc.snapshot_ids.count("a=") >= 1 and "b=" not in fake.nc.item_ids  # Gegenstände nur vom passenden

def test_teilen_oeffentlich(make_client, fake):
    c = login(make_client, fake, MEMBER); cid = add(c); c.post(f"/api/armory/{cid}/check", headers=ORIGIN)
    url = c.post(f"/api/armory/{cid}/check/share", headers=ORIGIN).json()["share_url"]
    assert url.startswith(f"{BASE}/c/")
    anyone = make_client(**ON); anyone.__enter__()
    body = anyone.get(f"/api/public/check/{url.rsplit('/', 1)[1]}").json()
    assert body["name"] == "Testheld" and "owner" not in body and body["result"]["size"] == 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hub/api && uv run pytest -q tests/test_buildcheck.py`
Expected: FAIL (404 auf `/check`, Modul fehlt)

- [ ] **Step 3: Implement model, migration `0009`, `buildcheck.py`, routes, public endpoint, README**

Migration nach dem Muster von `0008_comparisons.py`. `BuildCheck.run` nach dem Muster von `Armory.refresh` (eigene Sitzung, `running`-Menge, `try/finally`). Endpunkte und öffentliche Route nach dem Muster von Vergleich/`share_comparison`; Link `f"{settings.hub_base_url}/c/{token}"`.

- [ ] **Step 4: Run all API tests**

Run: `cd hub/api && uv run pytest -q`
Expected: alle grün

- [ ] **Step 5: Commit**

```bash
git add hub/api hub/README.md
git commit -m "hub: Build-Check starten, Fortschritt, Ergebnis und Teilen-Link"
```

---

### Task 4: Seite im Hub und öffentlicher Link

**Files:**
- Create: `hub/web/src/modules/armory/check.ts` (Typen `CheckField`, `CheckResult`, `BuildCheck` zu `CheckOut`, `SharedCheck`)
- Create: `hub/web/src/modules/armory/components/CheckView.svelte`
- Create: `hub/web/src/routes/hub/armory/[id]/check/+page.ts`, `+page.svelte`
- Create: `hub/web/src/routes/(public)/c/[token]/+page.ts`, `+page.svelte`
- Modify: `hub/web/src/routes/hub/armory/[id]/+page.svelte` (Link-Knopf „Build-Check“ neben „Vergleichen“)
- Modify: `hub/web/src/modules/armory/texts.ts` (Schlüssel `armory.check.*`, en und de)
- Modify: `hub/web/src/routes/(public)/datenschutz/+page.svelte` (Build-Check: Abruf bei Abyss Logs und NC, Namen nicht gespeichert, Link bis zurückgezogen; de und en)

**Interfaces:**
- Consumes: API aus Task 3; `ShareLink.svelte`, `send`, `api`, `apiLoad`; `ItemIcon`, `PlayerName`, `LEFT`, `RIGHT`, `ARCANA` aus `modules/logs`; `localized`, `classFromName`.
- Produces: `CheckView` mit Props `{ name: string; cls: string | null; data: CharacterData; result: CheckResult }`, benutzt von beiden Seiten.

Aufbau von `CheckView` (Spec + Entwurf C, `bild-c-detail.html`): Kopf mit Name, Klasse, Datum, „gegen N Spieler, Kampfkraft a–b“; Kampfkraft und Gegenstandsstufe mit Median; Ausrüstung links (`LEFT`) und rechts (`RIGHT`) um Profilbild (`data.profile.image`), je Platz Karte mit Ampelrand (schlechteste Ampel des Platzes) und nur den nicht-grünen Feldern; darunter Kacheln Arkana (`ARCANA` + Set), Werte, Daevanion, Skills/Titel/Flügel; ganz unten „Zuerst:“ aus `result.todo`. Feldnamen über Texte: `armory.check.key.<key>`, Präfixe `sub:`/`stone:`/`godstone:`/`skill:` als `armory.check.has.<präfix>` + Name. Zahl: „du X · Top Ø Y · N von M besser“; Auswahl: „du X · meist Y (N von M)“.

Hub-Seite: ohne Check Knopf „Build-Check starten“ mit Hinweis „dauert 2–3 Minuten“; Status `läuft` → „Profil P von 15“, alle 3 s `invalidateAll()` (wie Armory-Profilseite); `fehler` → Meldung, altes Ergebnis darunter; `fertig` → `CheckView`, Knöpfe „Neu prüfen“ (deaktiviert, solange gesperrt) und „Teilen“ mit `ShareLink`.

- [ ] **Step 1: Implement types, `CheckView`, beide Seiten, Knopf, Texte, Datenschutz**

- [ ] **Step 2: Run check and build**

Run: `cd hub/web && npm run check && npm run build`
Expected: `0 ERRORS 0 WARNINGS`, `✔ done`

- [ ] **Step 3: Im Browser prüfen** (lokal wie beim Vergleich: SQLite, Sitzung in der DB, echter Charakter, echte Abyss-Logs- und NC-Abrufe)

Erwartet: Start → Fortschritt zählt hoch → Ergebnis mit Ampel und „Zuerst:“; Teilen-Link öffnet ohne Login; schmaler Bildschirm (390 px) ohne seitliches Scrollen.

- [ ] **Step 4: Commit**

```bash
git add hub/web
git commit -m "hub: Build-Check-Seite mit Ampel je Platz, Zuerst und Teilen-Link"
```
