"""Plugin-Dateien prüfen: Kennung, Pfade, Versionen, Signatur des Katalogs, Manifest und Prüfsummen."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Öffentlicher Schlüssel des Katalogs (src-tauri/src/plugins/catalog.rs, PUBLIC_KEY_HEX)
PUBLIC_KEY_HEX = "d71e888cd5530b57254a4f87bf8f1861d8ddd8f7ddf45ecdba0771bb8f7d54ae"
API_VERSION = 2
MAX_PLUGIN = 8 * 1024 * 1024
PLAIN_NAME = re.compile(r"[A-Za-z0-9._-]+")


class PluginError(RuntimeError):
    """Fehlertext für die Oberfläche."""


def valid_id(plugin: str) -> bool:
    return 0 < len(plugin) <= 40 and all(c.islower() and c.isascii() or c.isdigit() and c.isascii() or c == "-" for c in plugin)


def safe_path(path: str) -> bool:
    return 0 < len(path) <= 128 and all(
        p not in ("", ".", "..") and PLAIN_NAME.fullmatch(p) for p in path.split("/"))


def newer(candidate: str, current: str) -> bool:
    """Ob `candidate` eine spätere Version ist ("1.2.10" > "1.2.9")."""
    def parts(v: str) -> list[int]:
        return [int(p) if p.isdigit() else 0 for p in v.split(".")]
    a, b = parts(candidate), parts(current)
    n = max(len(a), len(b))
    return a + [0] * (n - len(a)) > b + [0] * (n - len(b))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_catalog(body: bytes, signature_hex: str, key_hex: str = PUBLIC_KEY_HEX) -> dict:
    """Signatur prüfen und den Katalog lesen."""
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
        key.verify(bytes.fromhex(signature_hex.strip()), body)
    except (ValueError, InvalidSignature) as e:
        raise PluginError("Die Signatur des Plugin-Katalogs stimmt nicht: keine Installation daraus") from e
    catalog = json.loads(body)
    if catalog.get("format") != 1:
        raise PluginError(f"Plugin-Katalog im Format {catalog.get('format')}: dieses NexBoard liest Format 1")
    return catalog


def load_manifest(folder: Path) -> dict:
    """Manifest eines Plugin-Ordners lesen und prüfen."""
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PluginError(f"manifest.json: {e}") from e
    if not isinstance(manifest, dict) or not valid_id(str(manifest.get("id", ""))):
        raise PluginError("manifest.json: Kennung ungültig")
    api = manifest.get("apiVersion")
    if not isinstance(api, int) or not 0 < api <= API_VERSION:
        raise PluginError(f"apiVersion {api} (dieses NexBoard kann bis {API_VERSION}): NexBoard aktualisieren")
    if not (folder / "index.html").is_file():
        raise PluginError("index.html fehlt")
    permissions = manifest.get("permissions") or []
    for spec in manifest.get("decoders") or []:
        if f"decoder:{spec.get('name')}" not in permissions:
            raise PluginError(f"Decoder {spec.get('name')} braucht die Berechtigung decoder:{spec.get('name')}")
    return manifest


def check_files(entry: dict, folder: Path) -> None:
    """Der Ordner enthält genau die Dateien des Katalogs."""
    files: dict[str, str] = entry.get("files") or {}
    found = set()
    total = 0
    root = folder.resolve()
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise PluginError(f"{path.name} ist ein Link")
        if path.is_dir():
            continue
        rel = path.relative_to(folder).as_posix()
        want = files.get(rel)
        if want is None or not path.resolve().is_relative_to(root):
            raise PluginError(f"{rel} gehört nicht dazu")
        data = path.read_bytes()
        total += len(data)
        if total > MAX_PLUGIN:
            raise PluginError(f"größer als {MAX_PLUGIN} Byte")
        if sha256_hex(data).lower() != want.lower():
            raise PluginError(f"{rel} weicht vom Katalog ab")
        found.add(rel)
    missing = set(files) - found
    if missing:
        raise PluginError(f"{sorted(missing)[0]} fehlt")
