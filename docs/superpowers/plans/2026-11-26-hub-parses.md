# Hub-Parses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In der Kampfansicht des Hubs steht bei jedem Spieler eines getöteten Bosses ein Parse gegen Abyss Logs (EU) und gegen die eigenen Runs der Gilde.

**Architecture:** Neues API-Modul `parses` (`requires=("logs", "bis")`). Eine Hintergrundaufgabe speichert die Abyss-Logs-Ranglisten als sortierte DPS-Listen in `parse_boards`. Zwei Routen rechnen den Parse beim Aufruf nur aus der Datenbank. Im Web bringt das Modul `parses` die Komponente `ParseBadge`. Die Seiten unter `routes/` reichen sie als Snippet durch `FightView` an `RankBars`, so dass `logs` nichts von `parses` importiert.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, httpx, pytest (Python, `hub/api`); SvelteKit 5 mit Runes, TypeScript (`hub/web`).

**Spec:** `docs/superpowers/specs/2026-11-25-hub-parses-design.md`

## Global Constraints

- Arbeitsort: Worktree `~/Projekte/nexhub-parses`, Zweig `hub-parses`. Nicht pushen, kein PR, kein Issue-Kommentar ohne OK von Navonex.
- Abyss Logs: höchstens eine Anfrage alle 2 Sekunden (`PAUSE_SECONDS = 2.0`), jede Rangliste höchstens einmal am Tag (`MAX_AGE = 24 h`).
- Die Routen rufen nie Abyss Logs ab, sie lesen nur die Datenbank.
- Von Abyss Logs werden keine Spielernamen gespeichert, nur DPS-Werte.
- Nur Region `eu` (`abysslogs.REGION`).
- Kämpfe unter `MIN_SECONDS = 30` zählen nicht; je Spielername zählt der beste Kampf (`best_per_name`); unverifizierte Einträge zählen mit.
- Gildenparse erst ab `GUILD_MIN = 10` Charakteren (Name + Klasse).
- Abgerufen werden nur Paare `(mob, cls)` aus getöteten Bossen in Runs der letzten `WINDOW_DAYS = 30` Tage, höchstens `PER_TICK = 5` Ranglisten je Durchlauf, Durchlauf alle `TICK_SECONDS = 600`.
- Farben (Web): unter 25 grau, 25–49 grün, 50–74 blau, 75–94 lila, 95–98 orange, 99 rosa, 100 gold.
- Texte deutsch und englisch über `defineTexts` (wie `modules/loot/texts.ts`).
- Commits enden mit `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Python-Tests: `cd hub/api && uv run pytest`. Web-Prüfung: `cd hub/web && npm run check`.

### Abweichung vom Spec (vom Planer entschieden)

Der Parse ist der Anteil der Werte, die **kleiner oder gleich** dem eigenen Wert sind (`bisect_right`), nicht nur kleiner. Grund: Im Gildenvergleich steht der eigene Bestwert selbst in der Liste; mit „kleiner als“ käme der beste Charakter der Gilde nie auf 100. Gegen Abyss Logs ändert das nur Gleichstände.

## Review Focus

- Spieler ohne Klasse (`cls` ist `null`) oder mit einer Klasse, die `CLASS_KEYS` nicht kennt: kein Abruf, Parse `null`, keine Exception.
- Rangliste mit mehr als 100 Einträgen: alle Seiten werden geholt, nicht nur die erste (Test mit 250 Einträgen in Task 1).
- Abyss Logs fällt mitten im Abruf aus (HTTP 500 auf Seite 2): der alte Stand der Rangliste bleibt unverändert (Test in Task 3).
- Boss ohne Rangliste („not ranked“): gespeichert als leere Liste, Anzeige „–“ statt „wird geladen“, neuer Versuch erst nach `EMPTY_MAX_AGE = 7 Tage` (Test in Task 3).
- Zwei Spieler gleichen Namens im selben Kampf (Relog, maskierte Namen): die Antwort ist je Name, beide bekommen denselben Wert aus der Zusammenfassung; kein Absturz (Test in Task 4).

---

### Task 1: Seitenweiser Abruf einer Rangliste

**Files:**
- Modify: `hub/api/nexhub_api/modules/bis/abysslogs.py`
- Modify: `hub/api/tests/fake_abyss.py`
- Test: `hub/api/tests/test_abysslogs.py`

**Interfaces:**
- Produces: `async def leaderboard_page(http: httpx.AsyncClient, cls: str, boss: int, page: int) -> tuple[list[dict], int]` gibt `(entries, total)` zurück; `cls` ist der Anzeigename (`abyss_class`). Bei „not ranked“ `([], 0)`. Fehler als `AbyssError`.
- `FakeAbyss.boards` bleibt `dict[int, list[str]]`; der Nachbau beachtet jetzt `page` und `limit` (Standard 100) und meldet `total` als Gesamtzahl. Neu: `FakeAbyss.fail_page: int | None` (Seite, die mit HTTP 500 antwortet).

- [ ] **Step 1: Failing test** `test_rangliste_seitenweise` in `tests/test_abysslogs.py`: `FakeAbyss` mit `boards = {8001: [f"N{i}" for i in range(250)]}`; `leaderboard_page(http, "Ranger", 8001, 3)` liefert 50 Einträge und `total == 250`; Seite 1 liefert 100. Zweiter Test `test_rangliste_nicht_gewertet`: Fake antwortet für Boss 4242 mit HTTP 400 und Text `not ranked` → `([], 0)`.
- [ ] **Step 2:** `cd hub/api && uv run pytest tests/test_abysslogs.py -v` → FAIL (`leaderboard_page` fehlt).
- [ ] **Step 3:** `fake_abyss.py` um Seiten, `fail_page` und eine Menge `not_ranked: set[int]` (HTTP 400, Text `{"error":"boss not ranked"}`) erweitern. `leaderboard_page` in `abysslogs.py` über `_get` mit `limit=100` und `page`; `total` aus der Antwort, fehlt es, `len(entries)`. `leaderboard()` bleibt unverändert.
- [ ] **Step 4:** `uv run pytest tests/test_abysslogs.py tests/test_bis.py -v` → PASS (alte Tests unverändert grün).
- [ ] **Step 5:** Commit `Abyss Logs: Rangliste seitenweise abrufen`.

### Task 2: Rechnung (reine Funktionen)

**Files:**
- Create: `hub/api/nexhub_api/modules/parses/__init__.py` (vorerst nur Docstring, `MODULE` kommt in Task 3)
- Create: `hub/api/nexhub_api/modules/parses/calc.py`
- Test: `hub/api/tests/test_parses.py`

**Interfaces:**
- Produces (alle in `calc.py`):
  - `GUILD_MIN = 10`
  - `def percentile(value: float, ranked: list[float]) -> int | None`: `ranked` aufsteigend; `None` bei leerer Liste; sonst `floor(100 * bisect_right(ranked, value) / len(ranked))`.
  - `def needed_pairs(summaries: list[dict]) -> set[tuple[int, str]]`: `(mob, cls)` aus `bosses` mit `killed`, nur `cls in CLASS_KEYS` (`nexproto.classes`).
  - `def guild_bests(summaries: list[dict]) -> dict[tuple[int, str], list[float]]`: je `(mob, cls)` die aufsteigend sortierten Bestwerte je Charakter (`name`, `cls`), nur getötete Bosse.

- [ ] **Step 1: Failing tests** in `tests/test_parses.py`:
  - `test_parse_grenzen`: `percentile(5, []) is None`; `percentile(100, [10, 20, 30]) == 100`; `percentile(1, [10, 20, 30]) == 0`; `percentile(20, [10, 20, 30, 40]) == 50`; `percentile(40, [10, 20, 30, 40]) == 100`.
  - `test_paare_nur_getoetete_bosse_mit_klasse`: Zusammenfassungen mit einem getöteten Boss (mob 1, Spieler `ranger` und `cls: None`) und einem Wipe (mob 2) → `{(1, "ranger")}`.
  - `test_gilde_bestwert_je_charakter`: zwei Runs, „A“ ranger 100 und 300, „B“ ranger 200, „A“ gladiator 50 → `{(1, "ranger"): [200.0, 300.0], (1, "gladiator"): [50.0]}`.
- [ ] **Step 2:** `uv run pytest tests/test_parses.py -v` → FAIL (Import).
- [ ] **Step 3:** `calc.py` implementieren.
- [ ] **Step 4:** `uv run pytest tests/test_parses.py -v` → PASS.
- [ ] **Step 5:** Commit `Parses: Rechnung`.

### Task 3: Tabelle, Abruf im Hintergrund, Modul anmelden

**Files:**
- Create: `hub/api/nexhub_api/modules/parses/models.py`
- Create: `hub/api/nexhub_api/migrations/versions/0016_parse_boards.py`
- Create: `hub/api/nexhub_api/modules/parses/fetcher.py`
- Modify: `hub/api/nexhub_api/modules/parses/__init__.py`
- Modify: `hub/api/nexhub_api/modules/__init__.py` (Import und `parses.MODULE` in `MODULES` nach `loot.MODULE`)
- Modify: `hub/api/tests/conftest.py` (Fixture `no_background_collector` legt auch `ParseFetcher.run` still)
- Test: `hub/api/tests/test_parses.py`

**Interfaces:**
- Consumes: `leaderboard_page` (Task 1), `best_per_name`, `abyss_class`, `REGION`, `AbyssError` aus `bis.abysslogs`; `needed_pairs` (Task 2); `logs.models.Run`.
- Produces:
  - `class ParseBoard(Base)`, `__tablename__ = "parse_boards"`: `id` (BigID, PK), `boss: int`, `cls: str(32)`, `region: str(8)`, `fetched_at: datetime (tz)`, `total: int`, `dps: JSON` (aufsteigende Liste von float); `UniqueConstraint("boss", "cls", "region")`. Migration `0016`, Vorgänger `0015`, im Stil von `0015_feedback.py`.
  - In `fetcher.py`: `TICK_SECONDS = 600`, `PER_TICK = 5`, `PAUSE_SECONDS = 2.0`, `MAX_AGE = timedelta(hours=24)`, `EMPTY_MAX_AGE = timedelta(days=7)`, `WINDOW_DAYS = 30`, `MAX_PAGES = 100`.
  - `class ParseFetcher(sessionmaker, http, pause: float = PAUSE_SECONDS)` mit `async def run(self) -> None` (Schleife wie `BisCollector.run`, Exceptions geloggt) und `async def tick(self) -> int` (Zahl der abgerufenen Ranglisten).
  - `async def fetch_board(http, cls: str, boss: int, pause: float) -> tuple[int, list[float]]`: alle Seiten bis `ceil(total / 100)`, höchstens `MAX_PAGES`, `pause` zwischen zwei Anfragen; dann `best_per_name`, DPS aufsteigend.
  - `start(state, runtime)` gibt `[ParseFetcher(runtime.sessionmaker, runtime.http).run()]` zurück; `MODULE = ApiModule("parses", (routes.router,), requires=("logs", "bis"), start=start)`. In diesem Task mit leerem `routes.router = APIRouter()` anlegen, Task 4 füllt ihn.

`tick` wählt die Paare aus `needed_pairs` über die Runs mit `start_ms` in den letzten 30 Tagen. Fällig ist ein Paar ohne Zeile, eines mit nicht leerer Liste älter als `MAX_AGE` und eines mit leerer Liste älter als `EMPTY_MAX_AGE`. Fehlende kommen zuerst, dann die ältesten. Zwischen zwei Ranglisten liegt ebenfalls `pause`. `AbyssError` wird geloggt, die Zeile bleibt unverändert und der Takt geht mit dem nächsten Paar weiter.

- [ ] **Step 1: Failing tests** in `tests/test_parses.py` (Aufbau wie `run()` in `test_bis.py`: `database_url`, `FakeAbyss`, eigener `async_sessionmaker`; Runs direkt als `Run(...)`-Zeilen mit Zusammenfassung anlegen, Hilfsfunktion `add_run(sessionmaker, summary, start_ms)` mit einem User aus `nexhub_api.models.User`):
  - `test_abruf_speichert_nur_dps_aufsteigend`: Run mit getötetem Boss 8001 und Spieler `ranger`; Fake hat 250 Namen für 8001. `tick()` mit `pause=0` → 1; Zeile `(8001, "ranger", "eu")` mit `total == 250`, 250 DPS-Werten, aufsteigend; der Text keiner Spalte enthält „N1“.
  - `test_frischer_stand_wird_nicht_neu_geholt`: zweiter `tick()` gleich danach → 0, keine neuen Aufrufe in `fake.calls`.
  - `test_alter_run_und_wipe_loesen_nichts_aus`: Run älter als 30 Tage und Run mit `killed: False` → `tick() == 0`.
  - `test_fehler_laesst_alten_stand_stehen`: Zeile mit `fetched_at` vor 2 Tagen und `dps=[1.0]`; `fake.fail_page = 2`, 250 Namen → nach `tick()` noch `[1.0]` und altes `fetched_at`.
  - `test_nicht_gewertet_als_leere_liste`: Boss in `fake.not_ranked` → Zeile mit `dps == []`, `total == 0`; nach 2 Tagen (Zeit über `fetched_at` zurückgesetzt) kein neuer Abruf, nach 8 Tagen schon.
  - `test_hoechstens_fuenf_je_takt`: Runs mit 7 Bossen → erster `tick() == 5`, zweiter `== 2`.
- [ ] **Step 2:** `uv run pytest tests/test_parses.py -v` → FAIL.
- [ ] **Step 3:** Modell, Migration, `fetcher.py`, `__init__.py`, Anmeldung in `modules/__init__.py`, `conftest.py` umsetzen.
- [ ] **Step 4:** `uv run pytest -v` (ganze Suite, auch `test_module_boundaries.py` und `test_app.py`) → PASS.
- [ ] **Step 5:** Commit `Parses: Ranglisten von Abyss Logs im Hintergrund speichern`.

### Task 4: Routen

**Files:**
- Create: `hub/api/nexhub_api/modules/parses/routes.py`
- Modify: `hub/web/src/lib/api-types.ts` (neu erzeugt)
- Test: `hub/api/tests/test_parses.py`

**Interfaces:**
- Consumes: `percentile`, `guild_bests`, `GUILD_MIN` (Task 2); `ParseBoard` (Task 3); `logs.routes._get` für den Run mit Login, für geteilte Runs dieselbe Abfrage wie `logs.shared_routes._shared` (Token höchstens 32 Zeichen, sonst 404; `not_for_search_engines`).
- Produces (Pydantic, landen in `api-types.ts`):
  - `class Parse(BaseModel)`: `eu: int | None`, `eu_n: int | None`, `eu_at: datetime | None`, `guild: int | None`, `guild_n: int`.
  - `class RunParses(BaseModel)`: `fights: dict[str, dict[str, Parse]]`, Schlüssel `fight` und Spielername; `guild_min: int`.
  - `GET /api/parses/runs/{run_id}` (CurrentUser) und `GET /api/public/parses/shared/{token}`, beide `-> RunParses`.

Bedeutung der Felder: `eu_at is None` heißt „Rangliste noch nicht geladen“; `eu_at` gesetzt und `eu_n == 0` heißt „keine Rangliste bei Abyss Logs“. `guild` ist `None`, solange `guild_n < GUILD_MIN`. Nur getötete Bosse stehen in `fights`; Spieler ohne bekannte Klasse bekommen `eu`/`eu_n`/`eu_at` `None` und `guild_n = 0`. Für den Gildenvergleich alle Runs laden (wie `loot.routes`), für die EU-Werte alle `ParseBoard`-Zeilen der Bosse des Runs in einer Abfrage.

- [ ] **Step 1: Failing tests** in `tests/test_parses.py`, über `client`/`as_user`; Runs mit `add_run`, Ranglisten direkt als `ParseBoard`-Zeilen:
  - `test_parse_im_run`: Board `(1, "ranger")` mit `dps=[100, 200, 300, 400]`; Run mit Spieler „A“ ranger 250 → `fights[fight]["A"]` hat `eu == 50`, `eu_n == 4`, `eu_at` gesetzt.
  - `test_gilde_erst_ab_zehn`: 9 Charaktere (ranger, Boss 1, eigene Runs) → `guild is None`, `guild_n == 9`; ein zehnter Run → `guild_n == 10` und `guild` ist eine Zahl; der stärkste Charakter hat `guild == 100`.
  - `test_noch_nicht_geladen_und_nicht_gewertet`: ohne Board → `eu_at is None`; Board mit `dps=[]` → `eu_n == 0`, `eu is None`, `eu_at` gesetzt.
  - `test_wipe_und_ohne_klasse`: Wipe-Boss fehlt in `fights`; Spieler mit `cls: None` hat `eu is None`.
  - `test_gleicher_name_doppelt`: zwei Einträge „A“ im selben Boss → Antwort 200, ein Eintrag „A“.
  - `test_zugriff`: ohne Login 401 auf `/api/parses/runs/{id}`; unbekannte Run-ID 404; geteilter Run über `/api/public/parses/shared/{token}` ohne Login 200 (Token über `POST /api/runs/{id}/share` als Besitzer), falscher Token 404.
- [ ] **Step 2:** `uv run pytest tests/test_parses.py -v` → FAIL.
- [ ] **Step 3:** `routes.py` umsetzen, Router in `MODULE` eintragen (zwei Router: privat und öffentlich).
- [ ] **Step 4:** `uv run python -m nexhub_api.web_types` erzeugt `api-types.ts` neu; `uv run pytest -v` → PASS (inkl. `test_web_types.py`).
- [ ] **Step 5:** Commit `Parses: Routen für Runs und geteilte Runs`.

### Task 5: Anzeige im Web

**Files:**
- Create: `hub/web/src/modules/parses/module.ts` (`id: 'parses'`, `nav: []`, `texts`)
- Create: `hub/web/src/modules/parses/api.ts` (Typen aus `api-types.ts`, `parseColor`)
- Create: `hub/web/src/modules/parses/texts.ts`
- Create: `hub/web/src/modules/parses/components/ParseBadge.svelte`
- Modify: `hub/web/src/lib/modules.ts` (nach `loot`)
- Modify: `hub/web/src/modules/logs/components/RankBars.svelte` (neuer Prop `badge?: Snippet<[Player]>`, gerendert hinter der DPS-Spalte; Raster um eine Spalte `auto` erweitern; auf schmalen Seiten in der Zeile von Name/Wert)
- Modify: `hub/web/src/modules/logs/components/FightView.svelte` (Prop `badge` an `RankBars` durchreichen)
- Modify: `hub/web/src/routes/hub/runs/[id]/kampf/[fight]/+page.ts` und `+page.svelte`, `hub/web/src/routes/(public)/r/[token]/kampf/[fight]/+page.ts` und `+page.svelte`
- Modify: `hub/web/src/routes/hub/bewertung/+page.svelte` (Abschnitt „Parses“ de/en)

**Interfaces:**
- Consumes: `RunParses`, `Parse` aus `#lib/api-types.ts` (Task 4).
- Produces:
  - `export function parseColor(value: number): 'grey' | 'green' | 'blue' | 'purple' | 'orange' | 'pink' | 'gold'` in `modules/parses/api.ts`, Grenzen wie in den Global Constraints.
  - `ParseBadge.svelte` mit Props `{ parse: Parse | undefined; cls: string | null; guildMin: number }`: zeigt `EU <zahl>` und `Gilde <zahl>` (en: `Guild`), je mit Farbe; ohne Wert „–“; `eu_at === null` → „EU …“. Tooltips über `title`, Texte de/en:
    - EU: „besser als {pct} % von {n} {Klasse} auf Abyss Logs (Stand {datum})“ / „better than {pct}% of {n} {class} on Abyss Logs (as of {date})“
    - EU nicht geladen: „wird geladen“ / „loading“; keine Rangliste: „keine Rangliste bei Abyss Logs“ / „no ranking on Abyss Logs“
    - Gilde: „besser als {pct} % von {n} Charakteren“ / „better than {pct}% of {n} characters“; zu wenig: „zu wenig Daten ({n} von {min})“ / „too little data ({n} of {min})“
  - Die Seiten laden die Parses neben dem Kampf (`apiOrNull`, Fehler → `null`, damit der Kampf auch ohne Parses erscheint) und rendern `<FightView fight={data.fight}>{#snippet badge(p)}<ParseBadge …/>{/snippet}</FightView>`; `logs` importiert nichts aus `parses`.

Klassenname im Tooltip über `classInfo` aus `#modules/logs/classes.ts` (wie `CharacterSearch.svelte`). Farben als CSS-Variablen in `ParseBadge.svelte`, in hellem und dunklem Design lesbar.

- [ ] **Step 1:** `parseColor` umsetzen. Es gibt kein Web-Testframework im Repo; die Grenzen (24/25, 49/50, 74/75, 94/95, 98/99, 100) werden in Step 4 im Browser geprüft.
- [ ] **Step 2:** Modul, Texte, `ParseBadge`, `RankBars`/`FightView`-Snippet, beide Seiten, Abschnitt auf „Wie wir bewerten“ umsetzen.
- [ ] **Step 3:** `cd hub/web && npm run check` → 0 Fehler.
- [ ] **Step 4:** Hub lokal starten (Anleitung in `hub/README.md`), einen Run mit getötetem Boss und eine `parse_boards`-Zeile anlegen, Kampfansicht im eingebauten Browser öffnen: Abzeichen sichtbar, Tooltip stimmt, schmale Breite (375 px) ohne Überlauf, geteilter Link `/r/<token>/kampf/<fight>` zeigt dieselben Werte.
- [ ] **Step 5:** Commit `Parses: Anzeige in der Kampfansicht`.

### Task 6: Abschluss

- [ ] `cd hub/api && uv run pytest`, `uvx ruff check nexhub_api tests` (nur neue/geänderte Dateien müssen sauber sein) und `cd hub/web && npm run check` → grün.
- [ ] `git fetch origin && git rebase origin/main`, Konflikte mit Fabios Umbau lösen (vor allem Migrationsnummer: liegt auf `main` inzwischen eine `0016`, die eigene umbenennen und `down_revision` anpassen), Tests erneut grün.
- [ ] Navonex berichten. Push, PR und Bescheid an Fabio in Issue #69 nur nach seinem OK.
