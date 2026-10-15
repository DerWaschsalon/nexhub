"""Overlay: Layout (Validierung, Teil-Updates), Seite und Live-Daten auf Port+1."""
import asyncio
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from deckbar_daemon.overlay import DEFAULT_EVENTS, Overlay, OverlayLayout, merge


def test_layout_defaults_and_validation():
    L = OverlayLayout()
    assert L.start_mode == "click" and L.widgets.meter.enabled and not L.widgets.timers.enabled
    assert [e.name for e in L.widgets.timers.events] == [e.name for e in DEFAULT_EVENTS]
    with pytest.raises(ValueError):
        OverlayLayout.model_validate({"widgets": {"meter": {"scale": 9}}})
    with pytest.raises(ValueError):
        OverlayLayout.model_validate({"widgets": {"name": {}}})  # gibt es nicht (mehr)


def test_merge_is_deep_but_replaces_lists():
    a = {"widgets": {"meter": {"x": 1, "y": 2}, "timers": {"events": [1, 2]}}}
    assert merge(a, {"widgets": {"meter": {"x": 5}, "timers": {"events": [3]}}}) == \
        {"widgets": {"meter": {"x": 5, "y": 2}, "timers": {"events": [3]}}}


async def test_update_saves_and_publishes(tmp_path):
    o = Overlay(tmp_path, manage_unit=False)
    q: asyncio.Queue = asyncio.Queue(8)
    o.clients.add(q)
    await o.update({"fx": "frost", "widgets": {"boss": {"x": 100}}})
    assert json.loads((tmp_path / "overlay" / "layout.json").read_text())["fx"] == "frost"
    msg = q.get_nowait()
    assert msg.startswith("event: layout\n") and '"frost"' in msg
    await o.on_state({"dps": {"target": "B", "hp": 50.0, "rows": []}, "out_volume": 3})
    msg = q.get_nowait()
    assert msg.startswith("event: dps\n") and "out_volume" not in msg
    assert Overlay(tmp_path).layout.widgets.boss.x == 100


async def test_unit_untouched_for_test_instances(tmp_path):
    o = Overlay(tmp_path, manage_unit=False)
    code, out = await o._systemctl("enable", "--now", "deckbar-overlay.service")
    assert code == 1 and "Testinstanz" in out


async def test_page_and_api(tmp_path):
    o = Overlay(tmp_path, manage_unit=False)
    app = web.Application()
    o.add_routes(app)
    async with TestClient(TestServer(app)) as c:
        r = await c.get("/__deckbar__/overlay/")
        assert r.status == 200 and "DeckBar Overlay" in await r.text()
        assert (await c.get("/__deckbar__/overlay/overlay.js")).status == 200
        assert (await c.get("/__deckbar__/overlay/../a2ui.py")).status == 404
        r = await c.put("/api/overlay/layout", json={"widgets": {"meter": {"x": 7, "y": 8, "scale": 1.5}}})
        assert r.status == 200 and (await r.json())["widgets"]["meter"]["scale"] == 1.5
        assert (await c.put("/api/overlay/layout", json={"start_mode": "edit"})).status == 422
        r = await c.get("/api/overlay/events")
        first = await r.content.readuntil(b"\n\n")
        assert first.startswith(b"event: layout")
        r.close()
