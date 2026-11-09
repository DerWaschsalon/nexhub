"""Referenzbilder: der Simulator zeichnet jede Seite aus simulator_layout.yaml wie beim Einchecken.

Sicherheitsnetz für den Umbau von ui.c (Schritt 9): Ein Kacheltyp, der danach anders aussieht, fällt
hier auf. Ein Test-Gegenüber spricht das Geräteprotokoll mit festen Werten statt des Daemons.
Gewollte Änderung: WRITE_REFERENCE=1 setzen, Bilder neu schreiben und im PR zeigen.
"""
import asyncio
import json
import os
from pathlib import Path

import pytest
from aiohttp import WSMsgType, web
from PIL import Image

from deckbar_daemon.config import Layout, device_message, load_layout

NEXBOARD = Path(__file__).resolve().parents[2]
SIM = NEXBOARD / "simulator" / "build" / "deckbar-sim"
REFERENCE = NEXBOARD / "simulator" / "reference"
LAYOUT = load_layout(Path(__file__).with_name("simulator_layout.yaml"))
AFTER_MS = 1500  # Standard des Simulators; Layout und State sind dann längst gezeichnet

# Feste Werte für jede Kachel; Namen und Zahlen ausgedacht
STATE = {
    "out_volume": 42, "out_muted": False, "mic_volume": 80, "mic_muted": True, "hell": 30,
    "licht_aus": False, "playing": True,
    "track": {"title": "Ein Lied mit langem Titel", "artist": "Die Band", "player": "spotify"},
    "dps_active": True,
    "dps": {"target": "Testboss", "time": 83, "hp": 42.5, "rows": [
        {"name": f"Spieler{i}", "cls": cls, "dps": 20000 - i * 1500, "dmg": 1600000 - i * 120000,
         "pct": round(20 - i * 1.5, 1), "you": i == 2}
        for i, cls in enumerate(["gladiator", "brawler", "templar", "ranger", "assassin", "sorcerer",
                                 "cleric", "spiritmaster"])]},
    "claude": {"session": {"pct": 42, "reset": "in 2 h"}, "week": {"pct": 91, "reset": "Fr 02:00"}},
}


async def fake_daemon(page: Layout) -> web.AppRunner:
    """Ein Daemon, der nur Layout und State schickt und alle Anfragen des Geräts beantwortet."""
    async def ws(request: web.Request) -> web.WebSocketResponse:
        sock = web.WebSocketResponse()
        await sock.prepare(request)
        async for msg in sock:
            if msg.type != WSMsgType.TEXT:
                continue
            kind = json.loads(msg.data)["type"]
            if kind == "hello":
                await sock.send_str(device_message("welcome", server={"name": "Test", "version": "0"}, heartbeat=5))
                await sock.send_str(device_message("layout", **page.device_payload()))
                await sock.send_str(device_message("state", full=True, values=STATE))
                await sock.send_str(device_message("bg", id=""))
            elif kind == "art_request":
                await sock.send_str(device_message("art", id=""))
        return sock

    app = web.Application()
    app.router.add_get("/ws", ws)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    return runner


async def render(page: Layout, target: Path) -> None:
    runner = await fake_daemon(page)
    port = runner.addresses[0][1]
    sim = await asyncio.create_subprocess_exec(
        str(SIM), "--url", f"ws://127.0.0.1:{port}/ws", "--token", "test", "--no-cache", "--zoom", "1",
        "--screenshot", str(target), "--after", str(AFTER_MS),
        env={**os.environ, "SDL_VIDEODRIVER": "dummy"}, stdout=asyncio.subprocess.DEVNULL)
    await sim.wait()
    await runner.cleanup()
    assert sim.returncode == 0


@pytest.mark.skipif(not SIM.exists(), reason="Simulator nicht gebaut (cmake im Ordner simulator/)")
@pytest.mark.parametrize("page", LAYOUT.pages, ids=lambda p: p.id)
async def test_reference_image(page, tmp_path):
    ppm = tmp_path / f"{page.id}.ppm"
    await render(Layout(theme=LAYOUT.theme, pages=[page]), ppm)
    actual = Image.open(ppm).convert("RGB")
    reference = REFERENCE / f"{page.id}.png"
    if os.environ.get("WRITE_REFERENCE"):
        REFERENCE.mkdir(exist_ok=True)
        actual.save(reference, optimize=True)
    assert actual.tobytes() == Image.open(reference).convert("RGB").tobytes(), f"{page.id} sieht anders aus"
