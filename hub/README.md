# NexHub-Website

Website mit Discord-Login. Später kommen Kopplung von NexBoard-Geräten per Code und Uploads von
Dungeon-Runs dazu, ähnlich Warcraft Logs. Läuft auf dem VPS zusammen mit dem Bot (siehe
[`infra/`](../infra/)).

**Stand:** Grundgerüst. Anmelden, Abmelden, Rollen – noch keine Inhalte.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `api/` | FastAPI, SQLAlchemy (async) + Alembic, Postgres. Paket `nexhub_api`. |
| `web/` | SvelteKit 3 als reine Browser-App (`adapter-static`, Fallback `200.html`). |
| `Dockerfile` | baut `web/` und packt es mit der API in ein Image; die API liefert die Seiten aus. |

Endpunkte: `GET /api/health`, `GET /api/me`, `GET /api/auth/login`, `GET /api/auth/callback`,
`POST /api/auth/logout`. OpenAPI unter `/api/docs`.

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
des Cookies) und laufen nach `HUB_SESSION_DAYS` (30) ab.

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

Neue Tabelle oder Spalte: Modell in `nexhub_api/models.py` ändern, dann
`DATABASE_URL=… uv run alembic revision -m "…"` und die Migration von Hand prüfen. Beim Start
migriert `python -m nexhub_api` selbst.

## Auf dem Server

```
ssh waschsalon waschsalon-lock holen claude-… "Hub aktualisieren"
ssh waschsalon nexhub-update claude-… <branch>
ssh waschsalon waschsalon-lock freigeben claude-…
```

Ohne Domain nur über einen Tunnel erreichbar: `ssh -L 8080:127.0.0.1:80 waschsalon`, dann
http://localhost:8080 öffnen.
