# NexHub-Website

Website mit Discord-Login. Später kommen Kopplung von NexBoard-Geräten per Code und Uploads von
Dungeon-Runs dazu, ähnlich Warcraft Logs. Läuft auf dem VPS zusammen mit dem Bot (siehe
[`infra/`](../infra/)).

**Stand:** Grundgerüst – öffentlicher Bereich, Login, Admin-Seiten für Konten und System,
Kopplung von NexBoard-Geräten, Runs hochladen und ansehen (Liste, Schaden je Boss und Spieler),
Runs per Link öffentlich teilen.

## Zwei Bereiche

| Bereich | Web | API | Wer |
|---|---|---|---|
| öffentlich | `/`, `/login`, geteilte Runs `/r/<token>` | `/api/public/…` | alle |
| Hub | `/hub/…` | `/api/…` | angemeldete Admins und Mitglieder |
| Admin | `/hub/admin/…` | `/api/admin/…` | nur Admins |

Die Web-Seiten leiten nur um; die eigentliche Prüfung macht die API bei jeder Anfrage.

## Aufbau

```
api/nexhub_api/
  config.py      Einstellungen aus Umgebungsvariablen
  db.py          Datenbankverbindung, Migrationen beim Start
  models.py      Tabellen (users, sessions); Änderungen nur mit Migration
  migrations/    Alembic, eine Datei pro Schema-Stand
  deps.py        Bausteine für Routen: DB, CurrentUser, AdminUser, …
  discord.py     Discord-OAuth2
  analysis.py    Zusammenfassung eines NexLogs (Bosse, Schaden je Spieler)
  logs.py        Logging, Zugriffslog ohne OAuth-Code
  routes/        ein Modul pro Bereich: auth, account, devices, runs, public, admin
  main.py        App zusammenbauen, Herkunftsprüfung, Web-Seiten ausliefern
web/src/
  app.css        Design („Liquid Glass“): Farben als Variablen, Bausteine .glass .btn .chip .table
  lib/           api.ts (Anfragen + Typen), nav.ts (Menü), components/
  routes/        (public)/ öffentlich, hub/ mit Login, hub/admin/ nur Admins
Dockerfile       baut web/ und packt es mit der API in ein Image (Kontext: Repo-Wurzel, wegen proto/)
```

## Einen Bereich hinzufügen

Beispiel „Geräte“:

1. **API:** `api/nexhub_api/routes/devices.py` mit `router = APIRouter(prefix="/api/devices")`,
   in `routes/__init__.py` in `ROUTERS` eintragen. Zugriff über Parameter: `user: CurrentUser`
   oder `admin: AdminUser`.
2. **Tabellen:** Modell in `models.py`, dann Migration (`uv run alembic revision -m "…"` mit
   gesetzter `DATABASE_URL`, Ergebnis von Hand prüfen).
3. **Web:** Seite unter `web/src/routes/hub/geraete/`, Typen in `lib/api.ts`, Menüeintrag in
   `lib/nav.ts`.
4. **Tests** in `api/tests/` – die Fixtures `as_user(ADMIN)` / `as_user(MEMBER)` liefern
   angemeldete Browser.

Was öffentlich sein soll, bekommt eine Route unter `/api/public/…` und eine Seite unter
`web/src/routes/(public)/`. Dort nur herausgeben, was geteilt werden darf.

## Geräte koppeln

NexBoards melden sich mit eigenem Token, nicht mit dem Discord-Login. Gekoppelt wird nach
RFC 8628 („Device Authorization Grant“, wie beim Fernseher), Code in `routes/devices.py`:

1. Daemon: `POST /api/devices/pair` → geheimer `device_code`, kurzer `user_code` (`BCDF-GHJK`,
   nur Konsonanten), Link auf `/hub/geraete?code=…`. Gilt 10 Minuten, höchstens 50 offene.
2. Mensch: auf der Seite „Geräte“ bestätigen (`POST /api/devices/pair/approve`, mit Login).
3. Daemon fragt alle 5 s nach (`POST /api/devices/pair/poll`) und bekommt nach der Bestätigung
   **einmal** sein Token. Der Hub speichert nur dessen SHA-256.

Danach: `Authorization: Bearer <token>` → `CurrentDevice` in einer Route. `GET /api/devices/me`
sagt dem Gerät, wem es gehört; `DELETE /api/devices/me` koppelt es ab. Im Hub: `GET /api/devices`
(eigene), `DELETE /api/devices/{id}` (eigene, Admins jedes). Gesperrte Konten sperren ihre Geräte mit.

## Runs

Gekoppelte NexBoards laden nach jedem Run ein NexLog hoch (Format: [`proto/README.md`](../proto/README.md)),
Code in `routes/runs.py`:

- `POST /api/runs` (Gerät, Body = gzip-Datei, höchstens 8 MB): prüft mit `nexproto.unpack`, legt die
  Datei unverändert unter `<HUB_DATA_DIR>/runs/<id>.nexlog.gz` ab und speichert Eckdaten plus eine
  Zusammenfassung (`analysis.py`: Bosse, Sieg, Schaden und DPS je Spieler, Namen über `names`
  aufgelöst). Dieselbe Datei vom selben Konto zählt nur einmal (`duplicate: true`).
- `GET /api/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/nexlog`: für alle Angemeldeten.
- `DELETE /api/runs/{id}`: wer hochgeladen hat, oder ein Admin.
- Teilen: `POST /api/runs/{id}/share` erzeugt einen Link `/r/<token>` (16 Zufallsbytes),
  `DELETE …/share` zieht ihn zurück; neu teilen gibt einen neuen Link. Gleiche Rechte wie Löschen.
  Die öffentliche Ansicht (`GET /api/public/runs/{token}`, `routes/public.py`) zeigt Eckdaten und
  Zusammenfassung mit Mitspielernamen, aber kein Discord-Konto und nicht die Rohdatei, und bittet
  Suchmaschinen, sie nicht aufzunehmen (`X-Robots-Tag`, `<meta name="robots">`).

- Kampf-Details: `GET /api/runs/{id}/fights/{kampf}` (geteilt: `/api/public/runs/{token}/fights/{kampf}`)
  rechnet beim Aufruf aus der abgelegten Datei (`analysis.fight_detail`): Schaden je Sekunde je
  Spieler aus den Einzeltreffern (fehlen sie, gibt es keine Kurve), Skills mit Anteil und Krit-,
  Rücken-, Perfekt- und Doppel-Quote aus der Kampfdatei, Tode.

Die ausführliche Log-Ansicht ist NexLogs (`nexlogs/`, React), die der Hub unter `/logs/` ausliefert
(`HUB_LOGS_DIR`); sie liest dieselben Routen.

Im Web teilen sich Hub und öffentliche Seite die Ansichten `RunView.svelte` und `FightView.svelte`
(`lib/components/`). Spieler haben im ganzen Run eine feste Farbe aus einer geprüften Palette
(`lib/colors.ts`), die Klasse steht als Text daneben.

Noch nicht: mehrere Uploads desselben Runs zusammenführen, Buffs, Rohdateien nach 90 Tagen löschen. Bevor geteilte Links über eine
Domain wirklich öffentlich erreichbar sind: Impressum und Datenschutzerklärung klären.

## Bot

Der Bereich „Bot“ (`/hub/admin/bot/…`, nur Admins) steuert TheWashBot und ersetzt dessen altes
Web-Dashboard. Der Bot läuft als eigener Dienst; der Hub fragt seine Steuer-API
(`bot/bot/cogs/control.py`) im internen Docker-Netz, Code in `routes/bot.py`:

- `/api/admin/bot/<pfad>` → `<BOT_CONTROL_URL>/control/<pfad>` mit `Authorization: Bearer
  <BOT_CONTROL_KEY>`. Prüfen, speichern und Discord-Rechte setzen macht der Bot; der Hub prüft nur
  die Admin-Rolle und die Herkunft (wie überall bei ändernden Anfragen). Der Name des Admins geht
  als `X-Hub-User` mit und landet im Discord-Audit-Log.
- Lehnt der Bot den Schlüssel ab, antwortet der Hub mit 502 statt 401, damit die Web-Oberfläche
  den Admin nicht für abgemeldet hält. Nicht erreichbar: 502, keine Antwort: 504, nicht
  eingestellt: 503.
- Die Formular-Bereiche (Allgemein, Automod, Verwarnungen, Tickets, Community, Levelsystem,
  DPS-Webhook, AION 2) beschreibt der Bot selbst: `GET …/sections` liefert Felder mit Typ,
  Beschriftung, Hinweis und Wert, `PUT …/sections/<id>` speichert. Im Web zeichnet
  `BotSection.svelte` daraus das Formular. Ein neues Feld braucht also nur einen Eintrag in
  `SECTIONS` im Bot.
- Eigene Seiten haben, was kein einfaches Formular ist: Verifizierung, Level-Belohnungen,
  Ankündigungen, eigene Befehle, Benachrichtigungen, Sichtbarkeit (Rolle × Kanal).
- Discord-IDs sind überall Strings, als Zahl verlöre JavaScript die letzten Stellen.

## Login und Rollen

Discord-OAuth2 mit PKCE. Der Hub fragt nur `identify` ab und, wenn eine Mitgliedsrolle eingestellt
ist, `guilds.members.read`. Den Discord-Token gibt er direkt nach dem Login zurück; er speichert
nur ID, Name und Avatar.

| Rolle | Wer |
|---|---|
| Admin | Discord-ID steht in `HUB_ADMIN_IDS` |
| Mitglied | hat auf `HUB_GUILD_ID` die Rolle `HUB_MEMBER_ROLE_ID` |

Alle anderen kommen nicht hinein; die Login-Seite zeigt ihnen ihre Discord-ID zum Weitergeben.
Die Rolle wird bei jedem Login neu bestimmt. Sitzungen liegen in der Datenbank (nur der SHA-256
des Cookies) und laufen nach `HUB_SESSION_DAYS` (30) ab. Admins können unter Konten alle
Sitzungen eines Kontos beenden und Mitglieder sperren.

Alles, was etwas ändert (POST usw.) und mit Sitzungscookie kommt, muss von der eigenen Adresse
stammen (`Origin`-Prüfung in `main.py`), damit fremde Seiten nichts im Namen eines Browsers
auslösen können.

In der Discord-Anwendung (Developer Portal → OAuth2) muss `<HUB_BASE_URL>/api/auth/callback` als
Redirect eingetragen sein, ohne Domain also `http://localhost:8080/api/auth/callback`.

## Einstellungen

Alles über Umgebungsvariablen, auf dem Server in `/srv/nexhub/.env` (Vorlage
[`infra/server/srv/nexhub/env.beispiel`](../infra/server/srv/nexhub/env.beispiel)):
`DATABASE_URL`, `HUB_BASE_URL`, `HUB_SECRET_KEY`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`,
`HUB_ADMIN_IDS`, `HUB_GUILD_ID`, `HUB_MEMBER_ROLE_ID`, `HUB_WEB_DIR`, `HUB_DATA_DIR` (Ablage der Runs),
`BOT_CONTROL_URL` und `BOT_CONTROL_KEY` (Bereich „Bot“, siehe oben).

## Entwickeln

```
cd hub/api && uv sync
uv run pytest -q                                   # Tests (SQLite)
TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest -q   # dieselben Tests gegen Postgres

cd hub/web && npm ci                               # braucht Node ≥ 22.17
npm run check && npm run build
npm run dev                                        # leitet /api an localhost:8000 weiter
```

## Auf dem Server

```
ssh waschsalon waschsalon-lock holen claude-… "Hub aktualisieren"
ssh waschsalon nexhub-update claude-… <branch>
ssh waschsalon waschsalon-lock freigeben claude-…
```

Ohne Domain nur über einen Tunnel erreichbar: `ssh -L 8080:127.0.0.1:80 waschsalon`, dann
http://localhost:8080 öffnen.
