# NexHub-Website

Website mit Discord-Login. Später kommen Kopplung von NexBoard-Geräten per Code und Uploads von
Dungeon-Runs dazu, ähnlich Warcraft Logs. Läuft auf dem VPS zusammen mit dem Bot (siehe
[`infra/`](../infra/)).

**Stand:** Grundgerüst – öffentlicher Bereich, Login, Admin-Seiten für Konten und System,
Kopplung von NexBoard-Geräten.

## Zwei Bereiche

| Bereich | Web | API | Wer |
|---|---|---|---|
| öffentlich | `/`, `/login`, später geteilte Runs | `/api/public/…` | alle |
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
  logs.py        Logging, Zugriffslog ohne OAuth-Code
  routes/        ein Modul pro Bereich: auth, account, devices, public, admin
  main.py        App zusammenbauen, Herkunftsprüfung, Web-Seiten ausliefern
web/src/
  app.css        Design („Liquid Glass“): Farben als Variablen, Bausteine .glass .btn .chip .table
  lib/           api.ts (Anfragen + Typen), nav.ts (Menü), components/
  routes/        (public)/ öffentlich, hub/ mit Login, hub/admin/ nur Admins
Dockerfile       baut web/ und packt es mit der API in ein Image
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
`HUB_ADMIN_IDS`, `HUB_GUILD_ID`, `HUB_MEMBER_ROLE_ID`, `HUB_WEB_DIR`.

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
