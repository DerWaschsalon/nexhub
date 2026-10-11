"""Startpunkt: deckbar-daemon [--config-dir DIR] [-v]"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import webbrowser
from pathlib import Path

from aiohttp import web
from pydantic import ValidationError

from .config import config_dir, load_settings
from .mdns import Announcer
from .server import DeckBar, build_app
from .usb import UsbBridge

log = logging.getLogger("deckbar")


async def serve(args: argparse.Namespace) -> None:
    cdir = args.config_dir or config_dir()
    settings = load_settings(cdir)
    deck = DeckBar(settings, cdir)
    app = build_app(deck)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, settings.host, settings.port).start()
    url = f"http://localhost:{settings.port}/"
    log.info("DeckBar-Daemon läuft auf %s:%d – Konfiguration: %s", settings.host, settings.port, url)

    tasks = [
        asyncio.ensure_future(deck.audio.watch()),
        asyncio.ensure_future(deck.media.watch()),
        asyncio.ensure_future(deck.watch_layout_file()),
        asyncio.ensure_future(deck.watch_background()),
        asyncio.ensure_future(deck.dps.watch()),
        asyncio.ensure_future(deck.runs.watch()),
        asyncio.ensure_future(UsbBridge(settings.usb, f"ws://127.0.0.1:{settings.port}/ws").watch()),
    ]
    announcer = Announcer(settings.name, settings.port) if settings.mdns and not args.no_mdns else None
    if announcer:
        try:
            await announcer.start()
        except OSError as e:
            log.warning("mDNS nicht verfügbar: %s", e)
            announcer = None
    if args.open or settings.open_browser:
        webbrowser.open(url)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    log.info("beende …")
    for t in tasks:
        t.cancel()
    if announcer:
        await announcer.stop()
    await runner.cleanup()


def main() -> int:
    ap = argparse.ArgumentParser(prog="deckbar-daemon", description="PC-Daemon für die DeckBar")
    ap.add_argument("--config-dir", type=Path, help="Standard: ~/.config/deckbar")
    ap.add_argument("--open", action="store_true", help="Web-UI im Browser öffnen")
    ap.add_argument("--no-mdns", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    try:
        asyncio.run(serve(args))
    except ValidationError as e:
        print(f"Konfiguration ungültig:\n{e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
