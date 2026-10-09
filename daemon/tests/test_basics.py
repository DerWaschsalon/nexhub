import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from deckbar_daemon import keys
from deckbar_daemon.audio import parse_volume
from deckbar_daemon.config import Layout, default_layout_text
from deckbar_daemon.media import SEP, parse_line

SCHEMA = json.loads((Path(__file__).parents[2] / "docs" / "protocol.schema.json").read_text())


def test_default_layout_valid_and_matches_schema():
    layout = Layout.model_validate(yaml.safe_load(default_layout_text()))
    payload = layout.device_payload()
    jsonschema.validate({"v": 1, "type": "layout", **payload}, SCHEMA)
    # keine Aktionen im Geräte-Layout
    assert "action" not in json.dumps(payload)


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        Layout.model_validate({"pages": [{"id": "a", "items": [{"id": "x"}, {"id": "x"}]}]})


def test_nav_target_checked():
    with pytest.raises(ValueError):
        Layout.model_validate({"pages": [{"id": "a", "items": [{"id": "x", "nav": "nope"}]}]})


def test_parse_volume():
    assert parse_volume("Volume: 0.55") == (55, False)
    assert parse_volume("Volume: 1.20 [MUTED]") == (120, True)
    assert parse_volume("garbage") is None


def test_parse_playerctl():
    assert parse_line(SEP.join(["Playing", "Band", "Song", "spotify"]) + "\n") == {
        "playing": True, "track": {"title": "Song", "artist": "Band", "player": "spotify"}, "art_url": None}
    assert parse_line(SEP.join(["Paused", "Band", "Song", "spotify", "https://x/cover"]) + "\n")["art_url"] == "https://x/cover"
    assert parse_line("\n") == {"playing": False, "track": None, "art_url": None}


def test_art_rgb565_chunks():
    from PIL import Image

    from deckbar_daemon.art import CHUNK_BYTES, chunks, to_rgb565

    img = Image.new("RGB", (300, 200), (255, 0, 0))  # wird mittig quadratisch zugeschnitten
    data = to_rgb565(img, 88)
    assert len(data) == 88 * 88 * 2
    assert data[:2] == bytes([0x00, 0xF8])  # Rot = 0xF800, little-endian
    parts = chunks("abc", 88, 88, data)
    assert sum(p["rows"] for p in parts) == 88
    assert all(p["rows"] * 88 * 2 <= CHUNK_BYTES for p in parts)


def test_keys():
    assert keys.parse("ctrl+shift+m") == [29, 42, 50]
    assert keys.ydotool_args("alt+f4") == ["56:1", "62:1", "62:0", "56:0"]
    with pytest.raises(ValueError):
        keys.parse("ctrl+blub")


@pytest.mark.parametrize("msg", [
    {"v": 1, "type": "event", "event": "slider_change", "item": "vol", "value": 3, "final": True},
    {"v": 1, "type": "hello", "token": "x", "device": {"id": "d", "width": 640, "height": 172}},
    {"v": 1, "type": "state", "full": False, "values": {"track": None}},
])
def test_schema_examples(msg):
    jsonschema.validate(msg, SCHEMA)


def test_schema_rejects_bad_event():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"v": 1, "type": "event", "event": "slider_change", "item": "vol"}, SCHEMA)


def test_kde_wallpaper(tmp_path):
    from deckbar_daemon.background import kde_wallpaper

    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    rc = tmp_path / "rc"
    rc.write_text(
        "[Containments][2]\nlastScreen=1\n"
        f"[Containments][2][Wallpaper][org.kde.image][General]\nImage=file://{a}\n"
        "[Containments][7]\nlastScreen=0\n"
        f"[Containments][7][Wallpaper][org.kde.image][General]\nImage={b}\n"
    )
    assert kde_wallpaper(rc) == b  # Hauptbildschirm gewinnt
    assert kde_wallpaper(tmp_path / "fehlt") is None
