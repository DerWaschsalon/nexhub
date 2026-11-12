# Path of Exile im NexHub – Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merkliste mit Verlauf und Preisalarm im NexHub, `/poe preis` und Tagespost im Bot, Preise von poe.ninja für PoE 1 und PoE 2.

**Architecture:** Nur der Hub fragt poe.ninja ab (stündlich, ETag), speichert den aktuellen Preis je Item und einen Tagespreis, berechnet Alarme und den Tagespost und schickt fertige Daten über die vorhandene Steuer-API an den Bot. Der Bot zeigt nur an und fragt für `/poe preis` einen internen, per Schlüssel geschützten Hub-Endpunkt.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, httpx (Hub) · SvelteKit 5, eigenes SVG (Web) · discord.py, aiohttp, nexcore (Bot).

**Spec:** `docs/superpowers/specs/2026-11-12-poe-preise-design.md`

## Global Constraints

- Regeln aus `CLAUDE.md` gelten: so wenig Code wie möglich, nichts doppelt, englische Bezeichner, deutsche Kommentare, Oberflächentexte Deutsch + Englisch über `texts.ts`, Typangaben, Bot unter `mypy --strict` und `ruff`.
- Keine allgemeine Preisliste zum Stöbern; Suche liefert höchstens 20 Treffer.
- poe.ninja: höchstens ein Abruf je Spiel und Stunde, Kategorien nacheinander, `If-None-Match` mit gespeichertem ETag, User-Agent `NexHub/<hub_version> (+https://github.com/DerWaschsalon/nexhub)`.
- Spiele heißen im Code `"poe1"` und `"poe2"` (wie die poe.ninja-Pfade).
- Merkliste wandert beim Ligawechsel mit; Referenzpreis wird auf den ersten Preis der neuen Liga gesetzt, kein Alarm dabei.
- Höchstens ein Alarm je Merklisten-Eintrag und Tag; Standard-Schwelle 20 %.
- Tagespost 18:00 Europe/Berlin, je Spiel 5 Gewinner und 5 Verlierer.
- `/api/internal/*` nur mit `Authorization: Bearer <BOT_CONTROL_KEY>` und von außen per Caddy 404.
- `hub_poe_enabled` Standard `False`.
- Keine Geheimnisse, Discord-IDs von Personen oder privaten Adressen im Repo.

## Review Focus

1. **Einheit von PoE-2-Uniques:** Die Stash-Übersicht von PoE 2 liefert `primaryValue` (z. B. 3470 für ein Unique), `core.primary` sagt `divine`. Erwartung: der angezeigte Preis stimmt mit poe.ninja überein. Test in Task 2 mit echter Beispielantwort; vor dem Merge einmal von Hand gegen die Website prüfen.
2. **Item fehlt im nächsten Abruf** (keine Angebote mehr): letzter Preis bleibt stehen, kein Alarm, keine Löschung. Test in Task 2.
3. **poe.ninja antwortet 304, 5xx oder mit geändertem Format:** alte Daten bleiben, andere Kategorien laufen weiter. Tests in Task 2.
4. **Namen mit Sonderzeichen** (`Winter's Bite`, `%`, `_`) in Suche und `/poe preis`: werden gefunden, keine SQL-Platzhalter-Wirkung. Test in Task 4.
5. **Item mit einem einzigen Angebot** springt um 500 %: taucht nicht im Tagespost auf. Test in Task 3.

---

### Task 1: Einstellungen, Tabellen, Migration

**Files:**
- Modify: `hub/api/nexhub_api/config.py` (nach `hub_aion2_pause`)
- Modify: `hub/api/nexhub_api/models.py` (ans Ende)
- Create: `hub/api/nexhub_api/migrations/versions/0013_poe.py`
- Modify: `infra/server/srv/nexhub/compose.yml` (Umgebungsliste des Dienstes `api`)
- Modify: `hub/api/tests/conftest.py` (`_clean`: neue Tabellen in `DROP TABLE`)
- Test: `hub/api/tests/test_poe_models.py`

**Interfaces:**
- Produces: `Settings.hub_poe_enabled: bool = False`, `Settings.hub_poe1_league: str = ""`, `Settings.hub_poe2_league: str = ""`
- Produces: Modelle `PoeItem`, `PoePrice`, `PoeWatch` (Felder unten)

```
PoeItem   poe_items   id, game String(8), league String(64), key String(128), name String(128),
                      category String(48), icon String(512)|None, price Float, unit String(16),
                      listings Integer|None, trade_volume Float|None, updated_at DateTime(tz)
                      UniqueConstraint(game, league, key)
PoePrice  poe_prices  id, game, league, key, day Date, price Float
                      UniqueConstraint(game, league, key, day)
PoeWatch  poe_watches id, user_id FK users.id ondelete CASCADE, game, key, name String(128),
                      threshold Float default 20, ref_price Float|None, ref_league String(64)|None,
                      alerted_on Date|None, created_at DateTime(tz) server_default now
                      UniqueConstraint(user_id, game, key)
```

- [ ] **Step 1: Test schreiben** `test_poe_tables_exist(database_url)`: nach `migrate` lassen sich je ein `PoeItem`, `PoePrice`, `PoeWatch` anlegen und lesen; ein zweiter `PoeItem` mit gleichem `(game, league, key)` wirft `IntegrityError`.
- [ ] **Step 2: Test laufen lassen** `cd hub/api && uv run pytest -q tests/test_poe_models.py` → FAIL (Import fehlt).
- [ ] **Step 3: Einstellungen, Modelle und Migration `0013` (Vorgänger `0012`) anlegen.** Migration im Stil von `0012_bis.py` mit `BigID`. In `compose.yml` `HUB_POE_ENABLED`, `HUB_POE1_LEAGUE`, `HUB_POE2_LEAGUE` wie die übrigen `HUB_*` durchreichen.
- [ ] **Step 4: Tests** `uv run pytest -q` → alle grün.
- [ ] **Step 5: Commit** `git commit -m "Hub: Tabellen und Einstellungen für Path of Exile"`

### Task 2: Abruf von poe.ninja

**Files:**
- Create: `hub/api/nexhub_api/poe_ninja.py` (Zugriff + Umwandeln der Antworten)
- Create: `hub/api/nexhub_api/poe_prices.py` (Speichern, Liga bestimmen, stündlicher Lauf)
- Create: `hub/api/tests/fake_poe_ninja.py`, `hub/api/tests/data/poe_ninja/*.json` (gekürzte echte Antworten: je Spiel eine Exchange- und eine Stash-Übersicht und die Ligen)
- Modify: `hub/api/tests/conftest.py` (`FakeDiscord.__call__`: Host `poe.ninja` an `self.poe_ninja`)
- Modify: `hub/api/nexhub_api/main.py` (Hintergrundauftrag, nur bei `hub_poe_enabled`)
- Test: `hub/api/tests/test_poe_ninja.py`

**Interfaces:**
- Produces in `poe_ninja.py`:
  - `Game = Literal["poe1", "poe2"]`, `GAMES: tuple[Game, ...] = ("poe1", "poe2")`
  - `EXCHANGE_TYPES: dict[Game, tuple[str, ...]]`, `STASH_TYPES: dict[Game, tuple[str, ...]]` – Werte aus der poe.ninja-Doku (Stand 12.11.2026), genau einmal im Code
  - `@dataclass(frozen=True) class PriceLine: game: Game; league: str; key: str; name: str; category: str; icon: str | None; price: float; unit: str; listings: int | None; trade_volume: float | None`
  - `def parse_exchange(game: Game, league: str, category: str, data: dict[str, Any]) -> list[PriceLine]` – `key` = `detailsId` aus `items[]` (über `id` zugeordnet), `price` = `primaryValue`, `unit` = `core.primary`, `trade_volume` = `volumePrimaryValue`, Symbol-URL absolut (`https://poe.ninja` + `image`)
  - `def parse_stash(game: Game, league: str, category: str, data: dict[str, Any]) -> list[PriceLine]` – `key` = `detailsId`; PoE 1: `price` = `chaosValue`, `unit` = `"chaos"`; PoE 2: `price` = `primaryValue`, `unit` = `core.primary`; `listings` = `listingCount`
  - `class PoeNinja: __init__(self, http: httpx.AsyncClient, user_agent: str)`; `async def leagues(self, game: Game) -> list[str]`; `async def overview(self, game: Game, kind: Literal["exchange", "stash"], league: str, category: str) -> dict[str, Any]` – merkt sich ETag und Antwort je URL im Speicher, bei 304 die gemerkte Antwort; bei anderem Fehler `PoeNinjaError`
  - `def ninja_url(game: Game, league: str, category: str, key: str) -> str` – Link zur Item-Seite auf poe.ninja (Format beim Bauen auf der Website nachsehen)
- Produces in `poe_prices.py`:
  - `class PoePrices: __init__(self, sessionmaker, ninja: PoeNinja, settings: Settings)`
  - `async def league(self, game: Game) -> str` – Einstellung `hub_poe{1,2}_league`, sonst erste von `leagues()`
  - `async def refresh(self, game: Game) -> str` – alle Kategorien abrufen, `poe_items` upserten, Tagespreis in `poe_prices` für heute (Europe/Berlin) setzen; gibt die Liga zurück. Fehler einer Kategorie: loggen, weiter
  - `async def run(self, after_refresh: Callable[[Game, str], Awaitable[None]]) -> None` – Schleife, je Spiel `refresh`, dann `after_refresh(game, league)`, `REFRESH_EVERY_S = 3600`

- [ ] **Step 1: Tests schreiben** in `test_poe_ninja.py`:
  - `test_parse_exchange_poe2` – aus der Beispieldatei: `key == "orb-of-alchemy"`, `unit == "divine"`, `price == 0.005`, Symbol beginnt mit `https://poe.ninja/`
  - `test_parse_stash_poe1` – `key == "the-searing-touch-long-staff"`, `unit == "chaos"`, `listings == 30`
  - `test_parse_stash_poe2_unit` – `unit` = `core.primary` der Datei, `price` = `primaryValue` (Review Focus 1)
  - `test_overview_uses_etag` – zweiter Abruf schickt `If-None-Match`, Fake antwortet 304, Ergebnis gleich dem ersten
  - `test_refresh_keeps_missing_item` – Item aus Abruf 1 fehlt in Abruf 2 → `poe_items`-Zeile unverändert (Review Focus 2)
  - `test_refresh_survives_broken_category` – eine Kategorie 500, eine mit unbekanntem Format → andere Kategorien gespeichert, alte Werte nicht überschrieben (Review Focus 3)
  - `test_league_setting_wins` – `hub_poe1_league="Standard"` → `league("poe1") == "Standard"` ohne Abruf der Ligen
  - `test_user_agent` – jede Anfrage trägt `NexHub/` im User-Agent
- [ ] **Step 2: Tests laufen lassen** → FAIL.
- [ ] **Step 3: `poe_ninja.py` und `poe_prices.py` umsetzen**, Fake mit Beispieldateien, Auftrag in `main.py` neben den AION-Aufträgen (`after_refresh` kommt in Task 3; hier eine Funktion, die nichts tut).
- [ ] **Step 4: Tests** `uv run pytest -q` → grün.
- [ ] **Step 5: Commit** `git commit -m "Hub: Preise von poe.ninja abrufen und speichern"`

### Task 3: Alarm und Tagespost

**Files:**
- Create: `hub/api/nexhub_api/bot_client.py` (`tell_bot` aus `routes/runs.py` hierher verschieben, `runs.py` importiert sie)
- Create: `hub/api/nexhub_api/poe_alerts.py`
- Modify: `hub/api/nexhub_api/main.py` (`after_refresh` und die Tagespost-Schleife)
- Test: `hub/api/tests/test_poe_alerts.py`

**Interfaces:**
- Consumes: `PoeWatch`, `PoeItem`, `PoePrice`, `PriceLine`, `ninja_url`, `Settings.hub_guild_id`
- Produces in `bot_client.py`: `async def tell_bot(http: httpx.AsyncClient, settings: Settings, action: str, payload: dict[str, Any]) -> None` (Verhalten unverändert)
- Produces in `poe_alerts.py`:
  - `DEFAULT_THRESHOLD = 20.0`, `DAILY_POST_AT = time(18, 0)`, `TZ = ZoneInfo("Europe/Berlin")`, `TOP_N = 5`, `MIN_LISTINGS = 10`, `MIN_TRADE_VOLUME: dict[Game, float] = {"poe1": 1000.0, "poe2": 10.0}`
  - `def change_pct(old: float | None, new: float | None) -> float | None`
  - `@dataclass(frozen=True) class Move: key: str; name: str; icon: str | None; old: float; new: float; unit: str; change: float; url: str`
  - `def check_watch(watch: PoeWatch, item: PoeItem | None, league: str, today: date) -> Move | None` – setzt bei neuer Liga `ref_price`/`ref_league` neu und gibt `None`; ohne Preis `None`; über Schwelle und `alerted_on != today` → `Move`, `ref_price = item.price`, `alerted_on = today`
  - `def movers(today: list[PoeItem], yesterday: dict[str, float], game: Game) -> tuple[list[Move], list[Move]]` – nur Items mit `listings >= MIN_LISTINGS` oder `trade_volume >= MIN_TRADE_VOLUME[game]`, je `TOP_N` nach Änderung absteigend/aufsteigend
  - `async def send_alerts(sessionmaker, http, settings, game: Game, league: str) -> None` – lädt Merkliste + Items, ruft `check_watch`, speichert, schickt je Treffer `tell_bot(..., "poe/alert", {"guild_id", "discord_id", "game", "league", **asdict(move)})`
  - `async def send_daily(sessionmaker, http, settings, game: Game, league: str) -> None` – `tell_bot(..., "poe/daily", {"guild_id", "game", "league", "up": [...], "down": [...]})`, leer → nichts senden

- [ ] **Step 1: Tests schreiben** (ohne Netz, Objekte direkt gebaut):
  - `test_alert_over_threshold` – ref 100, Preis 125, Schwelle 20 → `Move.change == 25.0`, `ref_price == 125`
  - `test_alert_once_per_day` – zweiter Aufruf am selben Tag mit 160 → `None`
  - `test_no_alert_on_league_change` – `ref_league="Alt"`, Liga „Neu“, Preis 1 → `None`, `ref_price == 1`, `ref_league == "Neu"`
  - `test_no_alert_without_price` – `item=None` → `None`, Eintrag unverändert
  - `test_movers_skip_thin_items` – Item mit `listings=1` und +500 % fehlt, Item mit `listings=50` und +30 % ist dabei (Review Focus 5)
  - `test_tell_bot_payload` – über `FakeDiscord.bot`: `POST /control/poe/alert` mit `guild_id == GUILD` und Bearer-Schlüssel
  - `test_runs_still_use_tell_bot` – bestehende Run-Tests laufen unverändert (kein neuer Test, nur `uv run pytest -q tests/test_runs.py`)
- [ ] **Step 2: Tests laufen lassen** → FAIL.
- [ ] **Step 3: `bot_client.py` und `poe_alerts.py` umsetzen**, in `main.py` `after_refresh = send_alerts` und eine Schleife, die täglich um `DAILY_POST_AT` je Spiel `send_daily` ruft (Vortagespreise aus `poe_prices`).
- [ ] **Step 4: Tests** `uv run pytest -q` → grün.
- [ ] **Step 5: Commit** `git commit -m "Hub: Preisalarm und Tagespost für Path of Exile"`

### Task 4: API für Merkliste und Bot, Caddy

**Files:**
- Create: `hub/api/nexhub_api/routes/poe.py` (Router `router` für `/api/poe`, Router `internal` für `/api/internal/poe`)
- Modify: `hub/api/nexhub_api/routes/__init__.py` (beide Router in `ROUTERS`)
- Modify: `hub/api/nexhub_api/deps.py` (`require_bot_key`, `BotKey = Annotated[None, Depends(require_bot_key)]`)
- Modify: `infra/server/srv/nexhub/Caddyfile` (`/api/internal/*` → `respond 404` vor `handle`)
- Test: `hub/api/tests/test_poe_api.py`

**Interfaces:**
- Consumes: Modelle aus Task 1, `PoePrices.league`, `change_pct`, `ninja_url`, `DEFAULT_THRESHOLD`
- Produces (JSON, Felder genau so; Web und Bot nutzen sie):
  - `GET /api/poe/search?game&q` → `[{key, name, category, icon, price, unit}]`, höchstens 20, Suche ohne Groß-/Kleinschreibung, `%` und `_` im Suchtext wörtlich
  - `GET /api/poe/watches?game` → `{league, unit, watches: [{id, key, name, icon, price, change_24h, change_7d, threshold, url, days: [{day, price}]}]}`, `price`/`url` `null`, wenn es in der Liga keinen Preis gibt; `days` nur aktuelle Liga
  - `POST /api/poe/watches` `{game, key, threshold?}` → 201 mit dem Eintrag; Item muss in der aktuellen Liga existieren (sonst 404); doppelt → 409
  - `PATCH /api/poe/watches/{id}` `{threshold}` (1–1000) · `DELETE /api/poe/watches/{id}` – nur eigene, sonst 404
  - `GET /api/internal/poe/price?game&q` → `{name, price, unit, change_24h, change_7d, league, url, icon}`, bester Treffer (exakter Name vor Anfang vor enthält, dann höchster Preis), sonst 404
  - `GET /api/internal/poe/complete?game&q` → `[str]`, höchstens 25, je höchstens 100 Zeichen
  - Ist `hub_poe_enabled` aus: alle Endpunkte 404

- [ ] **Step 1: Tests schreiben**:
  - `test_watch_roundtrip(as_user)` – MEMBER sucht, merkt, sieht den Eintrag mit `threshold == 20`, ändert auf 35, löscht
  - `test_watches_are_private(as_user)` – ADMIN sieht die Merkliste von MEMBER nicht, `DELETE` auf fremde ID → 404
  - `test_search_special_chars(as_user)` – `q="winter's"` findet „Winter's Bite“; `q="%"` findet nichts, was kein `%` enthält (Review Focus 4)
  - `test_search_limit` – 30 passende Items → 20 Treffer
  - `test_internal_needs_key(client)` – ohne/mit falschem Schlüssel 401, mit `Bearer <bot_control_key>` 200
  - `test_internal_price_best_match` – „Divine Orb“ schlägt „Divine Orb Shard“ bei `q="divine orb"`
  - `test_disabled_is_404` – `hub_poe_enabled=False` → 404
- [ ] **Step 2: Tests laufen lassen** → FAIL.
- [ ] **Step 3: `routes/poe.py`, `require_bot_key` (Vergleich mit `hmac.compare_digest`, leerer Schlüssel → immer 401) und die Caddy-Regel umsetzen.**
- [ ] **Step 4: Tests** `uv run pytest -q` → grün.
- [ ] **Step 5: Commit** `git commit -m "Hub: API für die PoE-Merkliste und den Bot"`

### Task 5: Web-Oberfläche

**Files:**
- Create: `hub/web/src/modules/poe/module.ts`, `texts.ts`, `api.ts`
- Create: `hub/web/src/modules/poe/components/WatchCard.svelte`, `WatchOverview.svelte` (Kachel), `PriceChart.svelte`
- Create: `hub/web/src/routes/hub/poe/+page.svelte`, `+page.ts`
- Modify: `hub/web/src/lib/modules.ts` (Modul eintragen), `hub/web/src/lib/texts.ts` (`'game.poe': 'Path of Exile'` in beiden Sprachen)

**Interfaces:**
- Consumes: JSON aus Task 4
- Produces: Modul `{ id: 'poe', nav: [{ href: '/hub/poe', label: 'poe.nav', icon: <passendes vorhandenes Icon>, game: 'game.poe', overview: WatchOverview }] }`

- [ ] **Step 1: `api.ts` mit Typen genau nach Task 4 und Abruffunktionen nach Muster `modules/armory/api.ts`.**
- [ ] **Step 2: Seite nach der Skizze im Spec:** Schalter PoE 1 / PoE 2 (in der URL als `?game=`), Liga, Suchfeld mit Treffern zum Merken, Karten, Hinweis „Preise: poe.ninja“ und Link „Alle Preise bei poe.ninja“ (`https://poe.ninja/<game>/economy`). `PriceChart` als SVG nach Muster `armory/components/History.svelte`; lässt sich `History.svelte` mit einer Datenreihe als Eigenschaft allgemein machen, das teilen statt kopieren. Kachel zeigt die drei größten Änderungen (24 h) der eigenen Merkliste.
- [ ] **Step 3: Texte DE/EN** in `texts.ts` für alles Sichtbare, auch „in dieser Liga noch kein Preis“.
- [ ] **Step 4: Prüfen** `cd hub/web && npm run check` → 0 Fehler, 0 Warnungen; lokal mit `hub_poe_enabled=true` und Fake-Daten im Browser ansehen (Desktop und 390 px).
- [ ] **Step 5: Commit** `git commit -m "Hub: Seite Path of Exile mit Merkliste"`

### Task 6: Bot-Modul `poe.prices`

**Files:**
- Create: `bot/bot/core/hub.py` (Abfragen an die Hub-API im internen Netz)
- Modify: `bot/bot/core/__init__.py` (`HubClient` exportieren)
- Create: `bot/bot/modules/poe/__init__.py`, `bot/bot/modules/poe/prices/__init__.py`, `settings.py`, `embeds.py`, `commands.py`
- Modify: `bot/bot/modules/__init__.py` (`PoePrices` in `MODULES`)
- Modify: `bot/bot.env.beispiel` (`HUB_INTERNAL_URL=http://api:8000` mit Kommentar)
- Test: `bot/tests/modules/test_poe.py`

**Interfaces:**
- Consumes: JSON aus Task 3 (`/control/poe/alert`, `/control/poe/daily`) und Task 4 (`/api/internal/poe/*`); `control_key()` aus `bot/core/web.py`
- Produces:
  - `class HubClient: __init__(self, base_url: str, key: str)`; `@classmethod def from_env(cls) -> HubClient | None` (`HUB_INTERNAL_URL` + `control_key()`, eins fehlt → `None`); `async def get(self, path: str, params: dict[str, str]) -> Any | None` (404 → `None`, andere Fehler → `UserError("NexHub nicht erreichbar")`)
  - `PoeSettings.poe_channel: int | None = setting("channel", "Kanal für Preisalarme und Tagespost", group="Path of Exile", hint="Leer schaltet beides ab.")`
  - `embeds.py`: `def alert_embed(data: dict[str, Any]) -> discord.Embed`, `def daily_embed(data: dict[str, Any]) -> discord.Embed`, `def price_embed(data: dict[str, Any], game: str) -> discord.Embed` – Preis mit Einheit, Änderung mit Vorzeichen und `%`, Link zu poe.ninja, Fußzeile „Preise: poe.ninja“
  - `PoePrices(BotModule)` mit `info = ModuleInfo(id="poe.prices", name="Path of Exile Preise", category="Path of Exile", icon="mdi-cash", summary=…)`; `routes()`: `r.control("POST", "/control/poe/alert", …)`, `r.control("POST", "/control/poe/daily", …)` – Kanal aus den Einstellungen der `guild_id`, kein Kanal → 200 ohne Post; Alarm beginnt mit `<@discord_id>`
  - `commands.py`: `/poe preis spiel:<PoE 1|PoE 2> item:<Text>` mit Autovervollständigung über `/api/internal/poe/complete`; ohne `HubClient` → Hinweis „NexHub nicht verbunden“

- [ ] **Step 1: Tests schreiben**:
  - `test_alert_embed` – Daten mit `old=100, new=125, change=25.0, unit="divine"` → Titel enthält Namen, Text enthält `+25 %`, URL gesetzt
  - `test_daily_embed_empty_side` – `down=[]` → Embed ohne Absturz, Abschnitt „Verlierer“ zeigt „keine“
  - `test_control_alert_without_channel` – ohne `poe_channel` → 200, nichts gesendet
  - `test_control_alert_rejects_bad_guild` – unbekannte `guild_id` → `ApiError(400)`
  - `test_hub_client_from_env` – ohne `HUB_INTERNAL_URL` → `None`
  - `test_hub_client_404_is_none` – über `aiohttp`-Testserver
- [ ] **Step 2: Tests laufen lassen** `cd bot && python -m pytest -q tests/modules/test_poe.py` → FAIL.
- [ ] **Step 3: Umsetzen** nach Muster `modules/aion2/schedule` (Einstellungen, `GuildSettings`) und `modules/aion2/runs` (`routes`, `ModuleCog`, Autovervollständigung).
- [ ] **Step 4: Prüfen** `cd bot && python -m pytest -q tests && ruff check . && mypy` → grün.
- [ ] **Step 5: Commit** `git commit -m "Bot: Modul Path of Exile Preise"`

### Task 7: Abschluss

**Files:**
- Modify: `hub/README.md`, `bot/README.md` (je ein kurzer Abschnitt: was, Einstellungen, Tests), `infra/README.md` (Ausrollen: `.env`/`bot.env`-Einträge)

- [ ] **Step 1: READMEs ergänzen.**
- [ ] **Step 2: Alle betroffenen Tests** `cd hub/api && uv run pytest -q`, `cd hub/web && npm run check`, `cd bot && python -m pytest -q tests && ruff check . && mypy` → grün.
- [ ] **Step 3: Review Focus 1 von Hand:** drei Preise (je eine PoE-1-Währung, ein PoE-2-Unique, eine PoE-2-Währung) gegen poe.ninja vergleichen, Ergebnis in den PR-Text.
- [ ] **Step 4: Commit, Branch pushen, PR nach `main`** (Review nach Branch-Schutz). Ausrollen erst nach Merge, mit Sperre, Schritte aus dem Spec.
