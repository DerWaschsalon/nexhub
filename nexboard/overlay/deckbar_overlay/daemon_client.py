"""Wege zum Daemon ohne Qt: Socket, Port, Layout holen und ändern."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path


def socket_path() -> str:
    """Gleiche Regel wie deckbar_daemon/overlay.py."""
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/deckbar-{os.getuid()}"
    os.makedirs(base, exist_ok=True)
    return str(Path(base) / "deckbar-overlay.sock")


def daemon_port() -> int:
    cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "deckbar" / "config.yaml"
    try:
        m = re.search(r"^port:\s*(\d+)", cfg.read_text(), re.M)
        return int(m.group(1)) if m else 8765
    except OSError:
        return 8765


def daemon_url() -> str:
    """Overlay- und Meter-Oberfläche = Port des Daemons + 1 (config.yaml)."""
    return f"http://127.0.0.1:{daemon_port() + 1}/"


def fetch_layout() -> dict:
    """Overlay-Einstellungen vom Daemon (Monitor, GPU, Startmodus); ohne Daemon Standardwerte."""
    try:
        with urllib.request.urlopen(daemon_url() + "api/overlay/layout", timeout=1.5) as r:
            data = json.loads(r.read())
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def change_layout(args: list[str]) -> int | None:
    """--profile NAME bzw. --widget ID (an/aus): ändert nur das Layout beim Daemon, ganz ohne Qt, damit
    das Tastenkürzel sofort wirkt. Der Daemon schickt das neue Layout an die Overlay-Seite.
    Gibt den Exit-Code zurück, None bei anderen Befehlen."""
    if len(args) != 2 or args[0] not in ("profile", "profil", "widget"):  # --profil: Schreibweise bis Version 1
        return None
    key, value = args
    if key != "widget":
        patch = {"profile": value}
    else:
        current = fetch_layout().get("widgets", {}).get(value, {})
        patch = {"widgets": {value: {"enabled": not current.get("enabled", False)}}}
    request = urllib.request.Request(daemon_url() + "api/overlay/layout", json.dumps(patch).encode(),
                                     {"Content-Type": "application/json"}, method="PUT")
    try:
        urllib.request.urlopen(request, timeout=2).close()
    except OSError as e:
        print(f"NexBoard-Daemon: {e}", file=sys.stderr)
        return 1
    return 0
