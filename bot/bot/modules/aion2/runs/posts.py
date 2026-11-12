"""AION-2: Dungeon-Läufe aus dem NexBoard zu einem Discord-Post zusammenfassen.

Das NexBoard (nexboard/daemon/deckbar_daemon/bot.py, `run_payload`) schickt nach jedem beendeten
Run `POST /api/aion/fight` mit dem Token aus `/aion` (Bearer). Melden mehrere Mitspieler denselben
Lauf (gleicher Dungeon, ähnliche Startzeit/Dauer), wartet der Bot kurz, führt die Meldungen zu
einer Rangliste zusammen und postet genau einmal: Embed mit Text, darüber als Anhang das Run-Bild des
NexBoards (dasselbe wie beim Discord-Webhook, `image_webp`). Schickt das NexBoard kein Bild (ältere
Versionen), malt der Bot selbst: Rangliste als Bild und je Boss ein Bild. Der NexHub meldet danach den
Link zum Run (`attach_hub_link`, Steuer-API `/control/run-link`), der kommt vorn ins Feld „📊 Analyse“, daneben die
Bestenliste je Boss (`/leaderboard/<guild_id>`).

Erwarteter Payload (ein POST pro abgeschlossenem Lauf, eine Zeile pro Spieler):
    {
      "dungeon": "Ferocious Horn Den", "difficulty": "Normal",
      "bosses_total": 3, "bosses_killed": 3,
      "start_ms": 1760445123000, "fight_ms": 350000,
      "players": [{"name": "ReZero", "cls": "ranger", "damage": 13290000, "dps": 38000}, …],
      "bosses": [                                          # optional, für DPS pro Boss
        {"name": "Boss 1", "players": [{"name": "ReZero", "damage": 4200000, "dps": 41000}, …]},
        …
      ]
    }

Die zwei Pfade hängen am öffentlichen Teil des WebHost (bot/core/web.py, Port 8789); Caddy gibt sie
nach außen (infra/server/srv/nexhub/Caddyfile). Öffentliche Adresse für Links: `AION_PUBLIC_URL`.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import html
import io
import logging
import os
import secrets
import time
from typing import Any, ClassVar

import discord
from aiohttp import web
from discord.ext import commands
from nexcore import ModuleInfo

from bot.core import BotContext, BotModule
from bot.core.web import RouteTable, guild_id_from, json_body
from bot.hubpages import ApiError

from .format import fmt_dps, fmt_time, records_text
from .records import RunRecords, RunResult
from .settings import RunPostSettings

log = logging.getLogger(__name__)

DEFAULT_DELAY = 15
DURATION_TOLERANCE_S = 20
API_START_TOLERANCE_MS = 30_000
ANALYSIS_FIELD = "📊 Analyse"
RECORDS_FIELD = "🏆 Rekorde"
HUB_LINK_TEXT = "Im NexHub ansehen"
MAX_IMAGE_BYTES = 4 * 1024 * 1024  # Run-Bild vom NexBoard, gemessen 200–400 KB
TOKEN_BYTES = 24
MAX_URL = 500
POSTED_KEEP_S = 6 * 3600  # so lange kann der Hub einen Link zu einem schon geposteten Lauf nachreichen


def public_url() -> str:
    return os.getenv("AION_PUBLIC_URL", "").strip().rstrip("/")


def _bad_players(players: Any, prefix: str) -> str | None:
    if not isinstance(players, list) or not players:
        return f"{prefix} fehlt oder ist leer"
    for p in players:
        if not isinstance(p, dict) or not isinstance(p.get("name"), str) or not p["name"].strip():
            return f"{prefix}[].name fehlt"
        if not isinstance(p.get("damage"), (int, float)):
            return f"{prefix}[].damage fehlt oder ist keine Zahl"
    return None


def validate_fight_payload(data: dict[str, Any]) -> str | None:
    """Gibt eine Fehlermeldung zurück, oder None wenn der Payload brauchbar ist."""
    if not isinstance(data.get("dungeon"), str) or not data["dungeon"].strip():
        return "dungeon fehlt"
    for key in ("bosses_total", "bosses_killed", "start_ms", "fight_ms"):
        if not isinstance(data.get(key), (int, float)):
            return f"{key} fehlt oder ist keine Zahl"
    if error := _bad_players(data.get("players"), "players"):
        return error
    if data.get("image_webp") is not None and not isinstance(data["image_webp"], str):
        return "image_webp muss Base64-Text sein"
    bosses = data.get("bosses")
    if bosses is not None:
        if not isinstance(bosses, list):
            return "bosses muss eine Liste sein"
        for b in bosses:
            if not isinstance(b, dict) or not isinstance(b.get("name"), str) or not b["name"].strip():
                return "bosses[].name fehlt"
            if error := _bad_players(b.get("players"), "bosses[].players"):
                return error
    return None


def decode_image(value: Any) -> bytes | None:
    """Run-Bild aus dem Payload: nur echtes WebP bis MAX_IMAGE_BYTES, sonst None (dann malt der Bot)."""
    if not isinstance(value, str) or not value or len(value) > MAX_IMAGE_BYTES * 4 // 3 + 4:
        return None
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) > MAX_IMAGE_BYTES or raw[:4] != b"RIFF" or raw[8:12] != b"WEBP":
        return None
    return raw


def pick_image(reports: list[dict[str, Any]]) -> bytes | None:
    """Von mehreren Meldungen desselben Laufs das Bild mit den meisten Spielern (dann dem meisten Schaden)."""
    with_image = [r for r in reports if r.get("image")]
    if not with_image:
        return None
    best = max(with_image, key=lambda r: (len(r["players"]), sum(p["damage"] for p in r["players"])))
    image: bytes = best["image"]
    return image


def same_api_run(a: dict[str, Any], b: dict[str, Any]) -> bool:
    same_keys = ("dungeon", "bosses_total", "bosses_killed")
    if any(a[key] != b[key] for key in same_keys):
        return False
    if abs(a["fight_ms"] - b["fight_ms"]) > DURATION_TOLERANCE_S * 1000:
        return False
    if abs(a["start_ms"] - b["start_ms"]) > API_START_TOLERANCE_MS:
        return False
    return True


def same_run_start(run: dict[str, Any], dungeon: str, start_ms: int) -> bool:
    """Meldet der Hub denselben Lauf? Gleicher Dungeon, Start in der Toleranz wie bei Mehrfachmeldungen."""
    return bool(run["dungeon"] == dungeon and abs(run["start_ms"] - start_ms) <= API_START_TOLERANCE_MS)


def merge_players(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ein Eintrag pro Spielername, über alle Meldungen desselben Laufs — bei Abweichungen
    (unterschiedliche lokale Mitschnitte) gewinnt der höhere Schadenswert."""
    best: dict[str, dict[str, Any]] = {}
    for report in reports:
        for p in report["players"]:
            name = p["name"].strip()
            cur = best.get(name)
            if cur is None or p["damage"] > cur["damage"]:
                best[name] = {"name": name, "cls": p.get("cls") or (cur or {}).get("cls"),
                              "damage": p["damage"], "dps": p.get("dps") or 0}
    return sorted(best.values(), key=lambda p: -p["damage"])


def merge_bosses(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pro Boss (Reihenfolge nach erster Meldung) die Spieler mergen wie bei merge_players."""
    order: list[str] = []
    per_boss: dict[str, list[dict[str, Any]]] = {}
    for report in reports:
        for b in report.get("bosses") or []:
            name = b["name"].strip()
            if name not in per_boss:
                per_boss[name] = []
                order.append(name)
            per_boss[name].append({"players": b["players"]})
    return [{"name": name, "players": merge_players(per_boss[name])} for name in order]


def leaderboard_rows(bosses: list[dict[str, Any]], players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pro Boss und Spieler eine Zeile (Schaden, DPS, Klasse falls bekannt) — Kandidaten fürs
    Upsert in `aion_leaderboard` (dort gewinnt dann nur, wer den bisherigen Bestwert übertrifft)."""
    cls_by_name = {p["name"]: p.get("cls") for p in players}
    return [
        {"boss": b["name"], "player": p["name"], "class": p.get("cls") or cls_by_name.get(p["name"]),
         "damage": p["damage"], "dps": p.get("dps") or 0}
        for b in bosses for p in b.get("players") or []
    ]


def hub_link(url: str) -> str:
    return f"[{HUB_LINK_TEXT}]({url})"


def with_hub_link(embed: discord.Embed, url: str) -> discord.Embed:
    """Link zum Run im NexHub vorn ins Analyse-Feld (oder als neues Feld), nur einmal."""
    for i, f in enumerate(embed.fields):
        if f.name == ANALYSIS_FIELD:
            if HUB_LINK_TEXT not in (f.value or ""):
                embed.set_field_at(i, name=f.name, value=f"{hub_link(url)} · {f.value}", inline=False)
            return embed
    return embed.add_field(name=ANALYSIS_FIELD, value=hub_link(url), inline=False)


def build_run_embed(
    run: dict[str, Any], reporters: int, bosses: list[dict[str, Any]] | None = None, guild_id: int | None = None,
    hub_url: str | None = None, records: RunResult | None = None,
) -> discord.Embed:
    """Nur Text. Die Bilder hängen als Anhang an der Nachricht, nicht im Embed: Bearbeitet der Bot den
    Post später (Hub-Link), zeigte Discord ein Bild im Embed sonst ein zweites Mal als Anhang."""
    title = f"⚔️ {run['dungeon']}" + (f" ({run['difficulty']})" if run.get("difficulty") else "")
    e = discord.Embed(title=title, colour=discord.Colour.gold())
    e.add_field(name="Bosse", value=f"{run['bosses_killed']}/{run['bosses_total']} besiegt")
    e.add_field(name="Kampfzeit", value=fmt_time(run["fight_ms"]))
    if records:
        e.add_field(name=RECORDS_FIELD, value=records_text(records), inline=False)
    links = [hub_link(hub_url)] if hub_url else []
    if guild_id and bosses and public_url():
        links.append(f"[Bestenliste]({public_url()}/leaderboard/{guild_id})")
    if links:
        e.add_field(name=ANALYSIS_FIELD, value=" · ".join(links), inline=False)
    e.set_footer(text=f"AION-2 · {reporters} NexBoard-Meldung(en) zusammengeführt")
    return e


LEADERBOARD_CSS = """
:root { --bg: #0b0e1a; --panel: rgba(255,255,255,.055); --line: rgba(255,255,255,.12); --text: #f2f3f7;
  --dim: rgba(242,243,247,.62); --accent: #5ac8fa; color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; color: var(--text); font: 14px/1.5 Inter, system-ui, sans-serif;
  background: radial-gradient(900px 400px at 10% -10%, rgba(88,60,220,.28), transparent 70%),
    radial-gradient(800px 400px at 100% 0%, rgba(230,110,60,.18), transparent 70%), var(--bg); }
main { padding: 20px 16px 60px; max-width: 920px; margin: 0 auto; }
h1 { font-size: 20px; font-weight: 600; margin: 0 0 6px; }
.sub { color: var(--dim); margin: 0 0 18px; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .8px; color: var(--dim); margin: 0 0 14px;
  font-weight: 600; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 18px;
  margin-bottom: 16px; }
.bar-row { display: flex; align-items: center; gap: 10px; padding: 5px 0; font-size: 13px; }
.bar-name { width: 140px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-meta { font-size: 11px; color: var(--dim); }
.bar-track { flex: 1; height: 16px; border-radius: 8px; background: rgba(0,0,0,.3); overflow: hidden; }
.bar-fill { height: 100%; border-radius: 8px; background: linear-gradient(90deg, var(--accent), #8f7cff); }
.bar-value { width: 90px; flex-shrink: 0; text-align: right; color: var(--dim); font-variant-numeric: tabular-nums; }
.rank-1 .bar-fill { background: linear-gradient(90deg, #f0c040, #ffe49a); }
.rank-2 .bar-fill { background: linear-gradient(90deg, #c0c0c0, #e8e8e8); }
.rank-3 .bar-fill { background: linear-gradient(90deg, #cd7f32, #e8a868); }
.rank-1 .bar-name, .rank-1 .bar-value { color: #f0c040; }
@media (max-width: 520px) { .bar-name { width: 90px; } .bar-value { width: 70px; font-size: 12px; } }
"""


def leaderboard_html(guild_name: str, rows: list[Any]) -> str:
    esc = html.escape
    by_boss: dict[str, list[Any]] = {}
    for r in rows:
        by_boss.setdefault(r["boss"], []).append(r)
    cards = []
    for boss, entries in by_boss.items():
        top = entries[:10]
        best = top[0]["dps"] or 0
        lines = []
        for i, r in enumerate(top, start=1):
            pct = 100 * r["dps"] / best if best else 0
            cls = f' <span class="bar-meta">{esc(r["class"])}</span>' if r["class"] else ""
            rank_class = f" rank-{i}" if i <= 3 else ""
            lines.append(
                f'<div class="bar-row{rank_class}"><span class="bar-name">#{i} {esc(r["player"])}{cls}</span>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>'
                f'<span class="bar-value">{fmt_dps(r["dps"])}</span></div>'
            )
        cards.append(f'<div class="card"><h2>{esc(boss)}</h2>{"".join(lines)}</div>')
    body = "".join(cards) or '<div class="card">Noch keine Läufe gemeldet.</div>'
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bestenliste – {esc(guild_name)}</title><style>{LEADERBOARD_CSS}</style></head><body>
<main><h1>🏆 Bestenliste</h1><p class="sub">{esc(guild_name)} · beste DPS je Boss</p>{body}</main>
</body></html>"""


class ApiCluster:
    def __init__(self, run: dict[str, Any], guild_id: int):
        self.run = run
        self.guild_id = guild_id
        self.reports: list[dict[str, Any]] = [run]
        self.task: asyncio.Task[None] | None = None
        self.hub_url: str | None = None  # vom NexHub gemeldet (attach_hub_link), sobald hochgeladen


class RunPosts(BotModule):
    info: ClassVar[ModuleInfo] = ModuleInfo(
        id="aion2.runs", name="Run-Posts", category="AION 2", icon="mdi-sword-cross",
        summary="Ein Post je Dungeon-Run aus dem NexBoard, mit Rekorden, Bestenliste und Dungeon-Rangliste.",
    )
    Settings = RunPostSettings

    def __init__(self, ctx: BotContext) -> None:
        super().__init__(ctx)
        self.records = RunRecords(ctx.db)
        self.api_pending: dict[int, list[ApiCluster]] = {}  # guild_id -> offene API-Cluster
        self.api_posted: list[tuple[float, dict[str, Any], discord.Message]] = []  # (gepostet, Lauf, Nachricht)

    def cog(self) -> commands.Cog:
        from .commands import RunsCog

        return RunsCog(self)

    def routes(self, r: RouteTable) -> None:
        r.open("POST", "/api/aion/fight", self.handle_api_fight, max_body=2 * MAX_IMAGE_BYTES)  # Base64-Bild + Rest
        r.open("GET", "/leaderboard/{guild_id}", self.page_leaderboard)
        r.control("POST", "/control/run-link", self.run_link)
        r.control("POST", "/control/run", self.run_from_hub)

    async def shutdown(self) -> None:
        for clusters in self.api_pending.values():
            for c in clusters:
                if c.task:
                    c.task.cancel()
        await super().shutdown()

    async def token(self, guild_id: int, *, renew: bool = False) -> str:
        """API-Token des Servers für das NexBoard; fehlt er oder soll er neu sein, wird er erzeugt."""
        current = self.db.get(guild_id, "aion_api_token")
        if current and not renew:
            return current
        new = secrets.token_urlsafe(TOKEN_BYTES)
        await self.db.set(guild_id, "aion_api_token", new)
        return new

    def delay(self, guild_id: int) -> int:
        """Sekunden, die der Bot auf weitere Meldungen desselben Laufs wartet."""
        return self.db.get_int(guild_id, "aion_dedup_delay") or DEFAULT_DELAY

    def api_url(self) -> str:
        return f"{public_url() or '<AION_PUBLIC_URL fehlt in .env>'}/api/aion/fight"

    async def handle_api_fight(self, request: web.Request) -> web.Response:
        auth = request.headers.get("Authorization") or ""
        guild_id = self.db.guild_for_value("aion_api_token", auth[7:]) if auth.startswith("Bearer ") else None
        if guild_id is None:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            data = await request.json()
        except ValueError:
            return web.json_response({"error": "invalid json"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "invalid json"}, status=400)
        status, body = await self.accept_report(guild_id, data)
        return web.json_response(body, status=status)

    async def accept_report(self, guild_id: int, data: dict[str, Any],
                            hub_url: str | None = None) -> tuple[int, dict[str, Any]]:
        """Ein Run-Bericht, direkt von einem NexBoard oder über den NexHub (`/control/run`, dann mit Link):
        prüfen und mit Meldungen desselben Runs zu einem Post zusammenführen. Antwort: (Status, Inhalt)."""
        channel_id = self.db.get_int(guild_id, "aion_channel")
        if not channel_id:
            return 409, {"error": "kein aion_channel eingerichtet (/aion kanal:)"}
        error = validate_fight_payload(data)
        if error:
            return 400, {"error": error}

        run = {
            "dungeon": data["dungeon"].strip(), "difficulty": (data.get("difficulty") or "").strip() or None,
            "bosses_total": int(data["bosses_total"]), "bosses_killed": int(data["bosses_killed"]),
            "start_ms": int(data["start_ms"]), "fight_ms": int(data["fight_ms"]), "players": data["players"],
            "bosses": data.get("bosses") or [],
            "image": decode_image(data.get("image_webp")),
        }
        clusters = self.api_pending.setdefault(guild_id, [])
        for c in clusters:
            if same_api_run(c.run, run):
                c.reports.append(run)
                c.hub_url = c.hub_url or hub_url
                log.info("AION-API: Lauf %s bekommt weitere Meldung (jetzt %d)", run["dungeon"], len(c.reports))
                return 200, {"ok": True, "merged": True}

        delay = self.delay(guild_id)
        cluster = ApiCluster(run, guild_id)
        cluster.hub_url = hub_url
        clusters.append(cluster)
        cluster.task = asyncio.create_task(self._finalize_api_later(cluster, delay, channel_id))
        return 200, {"ok": True, "merged": False}

    async def _finalize_api_later(self, cluster: ApiCluster, delay: int, channel_id: int) -> None:
        await asyncio.sleep(delay)
        clusters = self.api_pending.get(cluster.guild_id, [])
        if cluster in clusters:
            clusters.remove(cluster)
        channel = self.client.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            log.warning("AION-API: Zielkanal %s nicht gefunden", channel_id)
            return
        players = merge_players(cluster.reports)
        bosses = merge_bosses(cluster.reports)
        if bosses:
            await self._update_leaderboard(cluster.guild_id, bosses, players)
        records = await self.records.save(cluster.guild_id, cluster.run, players)
        embed = build_run_embed(
            cluster.run, len(cluster.reports), bosses, guild_id=cluster.guild_id,
            hub_url=cluster.hub_url, records=records,
        )
        files = await self._run_images(cluster, players, bosses)
        try:
            message = await channel.send(embed=embed, files=files)
        except discord.HTTPException as e:
            log.warning("AION-API: Posten fehlgeschlagen: %r", e)
            return
        if not cluster.hub_url:  # Link kommt vielleicht noch (attach_hub_link)
            now = time.time()
            self.api_posted = [p for p in self.api_posted if now - p[0] < POSTED_KEEP_S][-49:]
            self.api_posted.append((now, cluster.run, message))

    async def _run_images(
        self, cluster: ApiCluster, players: list[dict[str, Any]], bosses: list[dict[str, Any]]
    ) -> list[discord.File]:
        """Das Run-Bild des NexBoards (enthält schon alle Bosse). Ohne eins malt der Bot selbst: Rangliste
        und je Boss ein Bild, höchstens 10 Anhänge pro Discord-Nachricht."""
        image = pick_image(cluster.reports)
        if image:
            return [discord.File(io.BytesIO(image), filename="aion_run.webp")]
        if not players:
            return []
        from .image import render_boss_image, render_run_image

        loop = asyncio.get_running_loop()
        run = cluster.run
        run_image = await loop.run_in_executor(
            None, render_run_image, run["dungeon"], run.get("difficulty"), players,
            run["bosses_killed"], run["bosses_total"], run["fight_ms"],
        )
        files = [discord.File(run_image, filename="aion_run.png")]
        for i, b in enumerate(bosses[:9]):
            boss_image = await loop.run_in_executor(None, render_boss_image, b["name"], b["players"])
            files.append(discord.File(boss_image, filename=f"aion_boss_{i}.png"))
        return files

    async def attach_hub_link(self, dungeon: str, start_ms: int, url: str) -> str:
        """Der NexHub meldet einen hochgeladenen Run: Link an den wartenden Post hängen oder den schon
        geposteten nachträglich ergänzen. Antwort: pending, edited oder unknown."""
        for clusters in self.api_pending.values():
            for c in clusters:
                if same_run_start(c.run, dungeon, start_ms):
                    c.hub_url = c.hub_url or url
                    return "pending"
        now = time.time()
        for entry in reversed(self.api_posted):
            posted, run, message = entry
            if now - posted < POSTED_KEEP_S and same_run_start(run, dungeon, start_ms):
                self.api_posted.remove(entry)
                embeds = list(message.embeds)
                if embeds:
                    embeds[0] = with_hub_link(embeds[0], url)
                    await message.edit(embeds=embeds)
                return "edited"
        return "unknown"

    async def run_from_hub(self, request: web.Request) -> dict[str, Any]:
        """Der Hub leitet den Run-Bericht eines NexBoards weiter (nexproto RunReport, im Hub geprüft), mit Link
        zum Run im Hub: wie die Run-API, aber für den Discord-Server des Hubs."""
        data = await json_body(request)
        guild_id = guild_id_from(self.client, data)
        report, url = data.get("report"), data.get("url")
        if not isinstance(report, dict):
            raise ApiError(400, "report fehlt")
        if url is not None and not (isinstance(url, str) and url.startswith(("https://", "http://"))
                                    and len(url) <= MAX_URL):
            raise ApiError(400, "url ungültig")
        status, body = await self.accept_report(guild_id, report, url)
        if status != 200:
            raise ApiError(status, str(body.get("error")))
        return body

    async def run_link(self, request: web.Request) -> dict[str, Any]:
        """Der Hub hat einen Run gespeichert: Link an den passenden Post (attach_hub_link)."""
        data = await json_body(request)
        dungeon, start_ms, url = data.get("dungeon"), data.get("start_ms"), data.get("url")
        if not isinstance(dungeon, str) or not dungeon.strip():
            raise ApiError(400, "dungeon fehlt")
        if not isinstance(start_ms, int) or isinstance(start_ms, bool):
            raise ApiError(400, "start_ms fehlt")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or len(url) > MAX_URL:
            raise ApiError(400, "url fehlt oder ungültig")
        return {"result": await self.attach_hub_link(dungeon.strip(), start_ms, url)}

    async def _update_leaderboard(
        self, guild_id: int, bosses: list[dict[str, Any]], players: list[dict[str, Any]]
    ) -> None:
        created = time.time()
        for row in leaderboard_rows(bosses, players):
            await self.db.execute(
                "INSERT INTO aion_leaderboard (guild_id, boss, player, class, damage, dps, run_id, created) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, ?) "
                "ON CONFLICT(guild_id, boss, player) DO UPDATE SET "
                "class=excluded.class, damage=excluded.damage, dps=excluded.dps, "
                "run_id=NULL, created=excluded.created "
                "WHERE excluded.dps > aion_leaderboard.dps",
                (guild_id, row["boss"], row["player"], row["class"], row["damage"], row["dps"], created),
            )

    async def page_leaderboard(self, request: web.Request) -> web.Response:
        """Öffentliche Bestenliste je Boss, ohne Login. Die Guild-ID ist kein Geheimnis (steht in
        jedem Invite-Link), ohne Treffer in `aion_leaderboard` ist die Seite einfach leer."""
        raw = request.match_info["guild_id"]
        guild = self.client.get_guild(int(raw)) if raw.isdigit() else None
        if not guild:
            return web.Response(text="Unbekannter Server.", status=404)
        rows = await self.db.fetchall(
            "SELECT boss, player, class, dps FROM aion_leaderboard WHERE guild_id=? ORDER BY boss, dps DESC",
            (guild.id,),
        )
        return web.Response(text=leaderboard_html(guild.name, rows), content_type="text/html")
