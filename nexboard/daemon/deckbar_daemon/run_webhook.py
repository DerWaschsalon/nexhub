"""Run-Bild per Discord-Webhook: einer der Wege eines beendeten Runs (RunPublisher).

Eingeschaltet und mit Adresse versehen wird er in den Einstellungen der Dungeon-Runs (runs.RunSettings).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime

import aiohttp

from .run_image import fmt_time, run_image
from .run_model import Run
from .runs import RunSettings

log = logging.getLogger(__name__)

POST_TIMEOUT_S = 30


def run_message(run: Run) -> str:
    bosses = run.bosses()
    fight_ms = sum(b.duration_ms for b in bosses)
    return (f"**{run.name}** – {run.kills}/{len(bosses)} {'Boss' if len(bosses) == 1 else 'Bosse'} besiegt, "
            f"Kampfzeit {fmt_time(fight_ms)} ({datetime.fromtimestamp(run.start_ms / 1000):%H:%M}–"
            f"{datetime.fromtimestamp(run.end_ms / 1000):%H:%M})")


async def post_discord(session: aiohttp.ClientSession, webhook: str, text: str, png: bytes, filename: str) -> None:
    """PNG + Text an einen Discord-Webhook; wartet einmal, falls Discord bremst (429)."""
    payload = {"content": text, "username": "NexBoard", "allowed_mentions": {"parse": []},
               "attachments": [{"id": 0, "filename": filename}]}
    for attempt in range(2):
        form = aiohttp.FormData()
        form.add_field("payload_json", json.dumps(payload), content_type="application/json")
        form.add_field("files[0]", png, filename=filename, content_type="image/webp")
        async with session.post(webhook, data=form) as resp:
            if resp.status == 429 and attempt == 0:
                retry = float((await resp.json(content_type=None) or {}).get("retry_after", 2))
                await asyncio.sleep(min(retry, 30))
                continue
            if resp.status >= 300:
                body = (await resp.text())[:200]
                raise RuntimeError(f"Discord antwortet {resp.status}: {body}")
            return


class WebhookPublisher:
    """Postet das Bild eines Runs. `result` ist der letzte Erfolg oder Fehler, für die Web-UI."""

    def __init__(self, settings: Callable[[], RunSettings]) -> None:
        self.settings = settings
        self.result = ""

    async def publish(self, run: Run) -> None:
        """Nach jedem beendeten Run, wenn der Webhook eingeschaltet ist."""
        current = self.settings()
        if current.enabled and current.webhook:
            await self.post(run)

    async def post(self, run: Run) -> bool:
        """Jetzt posten, auch für den Knopf „Letzten Run jetzt posten“. False bei einem Fehler."""
        try:
            png = await run_image(run)
            name = f"run-{datetime.fromtimestamp(run.start_ms / 1000):%Y%m%d-%H%M}.webp"
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=POST_TIMEOUT_S)) as session:
                await post_discord(session, self.settings().webhook, run_message(run), png, name)
        except (aiohttp.ClientError, TimeoutError, RuntimeError, OSError) as e:
            self.result = f"Fehler beim Posten: {e}"
            log.warning("Discord: %s", e)
            return False
        self.result = f"gepostet: {run.name}, {datetime.fromtimestamp(run.end_ms / 1000):%d.%m. %H:%M}"
        log.info("Discord: %s", self.result)
        return True
