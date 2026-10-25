"""Startpunkt: deckbar-daemon [--config-dir DIR] [-v]"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import webbrowser
from pathlib import Path

from aiohttp import web
from pydantic import ValidationError

from .config import config_dir, load_settings
from .a2ui import A2Ui
from .server import NexBoard, build_app, local_only

log = logging.getLogger("deckbar")
SHUTDOWN_TIMEOUT = 2  # so lange auf noch laufende Anfragen warten (aiohttp-Standard: 60 s)


async def serve(args: argparse.Namespace) -> NexBoard:
    cdir = args.config_dir or config_dir()
    settings = load_settings(cdir)
    deck = NexBoard(settings, cdir, mdns=not args.no_mdns)
    app = build_app(deck)

    runner = web.AppRunner(app, access_log=None, shutdown_timeout=SHUTDOWN_TIMEOUT)
    await runner.setup()
    await web.TCPSite(runner, settings.host, settings.port).start()
    url = f"http://localhost:{settings.port}/"
    # Overlay-Seite und Oberfläche des A2Tools-Meters, eigener Port wegen ihrer absoluten Pfade
    a2 = A2Ui(deck.dps.capture, cdir / "a2-settings.json")

    @web.middleware
    async def overlay_on(request: web.Request, handler):
        if not deck.modules.on("aion2.overlay"):
            raise web.HTTPServiceUnavailable(text="Modul Overlay ist ausgeschaltet.")
        return await handler(request)

    a2_runner = web.AppRunner(a2.app(local_only, overlay_on, routes=deck.overlay_routes), access_log=None,
                              shutdown_timeout=SHUTDOWN_TIMEOUT)
    await a2_runner.setup()
    try:
        await web.TCPSite(a2_runner, "127.0.0.1", settings.port + 1).start()
    except OSError as e:
        log.warning("Overlay-Oberfläche nicht verfügbar (Port %d): %s", settings.port + 1, e)
    log.info("NexBoard-Daemon läuft auf %s:%d – Web-UI: %s", settings.host, settings.port, url)

    await deck.modules.start()
    log.info("Module: %s", ", ".join(sorted(deck.modules.enabled)) or "keine")
    if args.open or settings.open_browser:
        webbrowser.open(url)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    log.info("starte neu …" if deck.restart_requested else "beende …")
    a2.close_clients()
    await deck.close_clients()
    await deck.modules.stop_all()
    await a2_runner.cleanup()
    await runner.cleanup()
    return deck


def main() -> int:
    ap = argparse.ArgumentParser(prog="deckbar-daemon", description="PC-Daemon für die NexBoard")
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
        deck = asyncio.run(serve(args))
    except ValidationError as e:
        print(f"Konfiguration ungültig:\n{e}", file=sys.stderr)
        return 2
    if deck.restart_requested:
        # Neustart aus der Web-UI: dasselbe Programm mit denselben Argumenten (auch ohne systemd)
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(sys.executable, [sys.executable, "-m", "deckbar_daemon", *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
