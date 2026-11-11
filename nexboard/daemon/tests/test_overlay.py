"""Overlay: Layout (Validierung, Teil-Updates, Umzug von Version 1), Seite und Live-Daten auf Port+1."""
import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from deckbar_daemon.modules.dps import DpsModule
from deckbar_daemon.modules.radar import RadarModule
from deckbar_daemon.modules.schedule import ScheduleModule
from deckbar_daemon.overlay import Overlay
from deckbar_daemon.overlay_layout import OverlayLayout, WidgetSpec, merge

PVE = ["meter", "boss", "timers", "cube", "warnings"]


def overlay(config_dir: Path, manage_unit: bool = False) -> Overlay:
    """Overlay mit den Widgets, die die Module im Daemon anmelden."""
    o = Overlay(config_dir, manage_unit=manage_unit)
    for module in (DpsModule, ScheduleModule, RadarModule):
        o.register(module.info.id, module.overlay_widgets)
    return o


def events(queue: asyncio.Queue) -> list[tuple[str, object]]:
    """Was an eine Overlay-Seite ging, als (Ereignis, Inhalt)."""
    out = []
    while not queue.empty():
        message = json.loads(queue.get_nowait().removeprefix("data: "))
        out.append((message["event"], message["payload"]))
    return out


def test_widgets_come_from_the_modules(tmp_path):
    o = overlay(tmp_path)
    assert list(o.layout.widgets) == ["meter", "boss", "timers", "cube", "map", "warnings"]
    assert o.layout.widgets["meter"].enabled and not o.layout.widgets["timers"].enabled
    assert o.layout.widgets["boss"].options == {"show_ttk": True, "hide_idle": True}
    assert (o.layout.widgets["map"].width, o.layout.widgets["map"].height) == (340, 300)
    assert o.layout.profiles == {"PvE": PVE, "PvP": ["meter"]}  # neue Datei: Profile aus den Angaben der Widgets
    info = {w["id"]: w for w in o.widgets_info()}
    assert info["timers"]["module"] == "aion2.schedule" and info["map"]["resizable"]
    assert [option["key"] for option in info["boss"]["options"]] == ["show_ttk", "hide_idle"]
    o.module_on = lambda module: module != "aion2.radar"
    assert [w["id"] for w in o.widgets_info() if not w["active"]] == ["cube", "map", "warnings"]


def test_layout_validation():
    with pytest.raises(ValueError):
        OverlayLayout.model_validate({"widgets": {"meter": {"scale": 9}}})
    with pytest.raises(ValueError):
        OverlayLayout.model_validate({"widgets": {"Kein Name": {}}})
    with pytest.raises(ValueError):
        OverlayLayout.model_validate({"profile": "Raid"})  # das Profil gibt es nicht


def test_merge_is_deep_but_replaces_lists():
    a = {"widgets": {"meter": {"x": 1, "y": 2}}, "profiles": {"PvE": ["meter", "boss"]}}
    assert merge(a, {"widgets": {"meter": {"x": 5}}, "profiles": {"PvE": ["meter"]}}) == \
        {"widgets": {"meter": {"x": 5, "y": 2}}, "profiles": {"PvE": ["meter"]}}


async def test_update_saves_and_publishes(tmp_path):
    o = overlay(tmp_path)
    q: asyncio.Queue = asyncio.Queue(8)
    o.clients.add(q)
    await o.update({"fx": "frost", "widgets": {"boss": {"x": 100, "options": {"show_ttk": False}}}})
    assert json.loads((tmp_path / "overlay" / "layout.json").read_text())["fx"] == "frost"
    [(event, layout)] = events(q)
    assert event == "layout" and layout["fx"] == "frost"
    await o.on_state({"dps": {"target": "B", "hp": 50.0, "rows": []}, "out_volume": 3})
    # immer der ganze Stand, ohne Fremdes aus dem State
    assert events(q) == [("dps", {"dps": {"target": "B", "hp": 50.0, "rows": []}, "dps_active": False})]
    boss = overlay(tmp_path).layout.widgets["boss"]
    assert boss.x == 100 and boss.options == {"show_ttk": False, "hide_idle": True}


async def test_widget_of_a_later_module_keeps_its_place(tmp_path):
    """Die Datei kennt ein Widget schon, bevor sein Modul es anmeldet (Reihenfolge beim Start)."""
    await overlay(tmp_path).update({"widgets": {"cube": {"x": 5, "y": 6}}})
    o = Overlay(tmp_path, manage_unit=False)
    o.register("aion2.dps", DpsModule.overlay_widgets)
    assert "cube" not in o.layout.widgets
    o.register("aion2.radar", RadarModule.overlay_widgets)
    assert (o.layout.widgets["cube"].x, o.layout.widgets["cube"].y) == (5, 6)
    # ein Widget, das es nicht mehr gibt, fällt aus Layout und Profilen
    o = Overlay(tmp_path, manage_unit=False)
    o.register("x", [WidgetSpec("meter", "Meter", "")])
    assert list(o.layout.widgets) == ["meter"] and o.layout.profiles["PvE"] == ["meter"]


async def test_profiles_switch_widgets_and_remember_changes(tmp_path):
    o = overlay(tmp_path)
    await o.update({"profile": "PvP"})
    assert o.layout.visible() == ["meter"]
    await o.update({"widgets": {"timers": {"enabled": True}}})  # z.B. Tastenkürzel --widget timers
    assert o.layout.profiles["PvP"] == ["meter", "timers"]
    await o.update({"profile": "PvE"})
    assert o.layout.visible() == PVE
    with pytest.raises(ValueError):
        await o.update({"profile": "Tippfehler"})  # z.B. im Tastenkürzel: Ansicht bleibt, wie sie ist
    assert o.layout.profile == "PvE"
    # die Profilliste kommt immer ganz, sonst ließe sich keins löschen; das aktive nur zusammen mit profile
    with pytest.raises(ValueError):
        await o.update({"profiles": {"PvP": ["meter"]}})
    await o.update({"profiles": {"PvP": ["meter"]}, "profile": ""})
    assert list(o.layout.profiles) == ["PvP"] and o.layout.visible() == PVE
    with pytest.raises(ValueError):
        await o.update({"profiles": {"Mit Leerzeichen": []}})
    await o.update({"profiles": {"X": ["meter", "gibtsnicht"]}})  # Unbekanntes fällt weg
    assert o.layout.profiles == {"X": ["meter"]}


async def test_launcher_gets_an_action_per_profile_and_widget(tmp_path):
    from deckbar_daemon.overlay import LAUNCHER, launcher_path
    o = overlay(tmp_path, manage_unit=True)
    o.write_launcher()
    assert not launcher_path().exists()  # Overlay nicht eingerichtet: nichts anlegen
    launcher_path().parent.mkdir(parents=True)
    launcher_path().write_text(LAUNCHER.read_text())
    await o.update({"profiles": {"PvP": ["meter"], "Raid": ["meter", "boss"]}})
    text = launcher_path().read_text()
    assert text.startswith(LAUNCHER.read_text())
    assert "Actions=profile-PvP;profile-Raid;widget-meter;" in text
    assert "[Desktop Action profile-Raid]\nName=Profil Raid\nExec=deckbar-overlay --profile Raid\n" in text
    assert "Name=Cube-Radar ein/aus\nExec=deckbar-overlay --widget cube\n" in text
    await overlay(tmp_path / "test").update({"profiles": {"Anders": []}})
    assert launcher_path().read_text() == text  # Testinstanzen fassen den Starter nie an


async def test_autohide_geht_sofort_ans_laufende_programm(tmp_path):
    """Nur ein Wechsel von hide_unfocused schickt einen Befehl über den Socket (hier ein Fake im
    Test-Laufzeitordner aus conftest.py); ohne laufendes Programm wird nur gespeichert."""
    from deckbar_daemon.overlay import socket_path
    o = overlay(tmp_path)
    assert o.layout.hide_unfocused
    await o.update({"hide_unfocused": False})  # kein Socket: kein Fehler
    got: list[bytes] = []

    async def conn(reader, writer):
        got.append(await reader.read())
        writer.close()

    socket_path().parent.mkdir(parents=True, exist_ok=True)
    server = await asyncio.start_unix_server(conn, str(socket_path()))
    async with server:
        await o.update({"fx": "gold"})
        await o.update({"hide_unfocused": True})
        for _ in range(50):
            if got:
                break
            await asyncio.sleep(0.01)
    assert got == [b"autohide-on\n"]


async def test_unit_untouched_for_test_instances(tmp_path):
    o = Overlay(tmp_path, manage_unit=False)
    code, out = await o.systemctl("enable", "--now", "deckbar-overlay.service")
    assert code == 1 and "Testinstanz" in out


class FakeUnit:
    """Stellt systemctl --user nach, ohne systemd anzufassen."""

    def __init__(self, autostart=False):
        self.calls: list[str] = []
        self.active, self.autostart = False, autostart

    async def __call__(self, *args):
        self.calls.append(args[0])
        match args[0]:
            case "start":
                self.active = True
            case "stop":
                self.active = False
            case "disable":
                self.autostart = False
            case "show":
                return 0, (f"LoadState=loaded\nActiveState={'active' if self.active else 'inactive'}\n"
                           f"UnitFileState={'enabled' if self.autostart else 'disabled'}\n")
        return 0, ""


async def test_overlay_kommt_und_geht_mit_dem_spiel(tmp_path, monkeypatch):
    import deckbar_daemon.overlay as ov
    monkeypatch.setattr(ov, "GAME_POLL_S", 0.01)
    monkeypatch.setattr(ov, "GAME_GRACE_S", 0.06)
    o = Overlay(tmp_path, manage_unit=True)
    unit = FakeUnit(autostart=True)
    o.systemctl = unit
    o.refresh_screens = lambda: asyncio.sleep(0)
    game = {"on": False}

    async def check():
        return game["on"]
    o.game_check = check

    await o.on_module(True)
    assert not unit.autostart and not unit.active  # früherer Login-Autostart ist weg, nichts gestartet
    task = asyncio.ensure_future(o.watch())
    await asyncio.sleep(0.05)
    assert not unit.active and "start" not in unit.calls

    game["on"] = True
    await asyncio.sleep(0.05)
    assert unit.active and o.game and unit.calls.count("start") == 1

    unit.active = False  # Overlay mitten im Spiel von Hand beendet: bleibt aus
    await asyncio.sleep(0.05)
    assert unit.calls.count("start") == 1

    unit.active = True
    game["on"] = False
    await asyncio.sleep(0.01)
    assert unit.active  # Gnadenfrist (Ladebildschirm, Absturz mit Neustart)
    await asyncio.sleep(0.1)
    assert not unit.active and not o.game

    await o.on_module(False)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_page_and_api(tmp_path):
    o = overlay(tmp_path)
    app = web.Application()
    o.add_routes(app)
    async with TestClient(TestServer(app)) as c:
        r = await c.get("/__deckbar__/overlay/")
        assert r.status == 200 and "NexBoard Overlay" in await r.text()
        for spec in o.specs.values():  # zu jedem angemeldeten Widget gibt es das Modul der Seite
            assert (await c.get(f"/__deckbar__/overlay/widgets/{spec.id}.js")).status == 200
        assert (await c.get("/__deckbar__/overlay/../a2ui.py")).status == 404
        r = await c.put("/api/overlay/layout", json={"widgets": {"meter": {"x": 7, "y": 8, "scale": 1.5}}})
        assert r.status == 200 and (await r.json())["widgets"]["meter"]["scale"] == 1.5
        assert (await c.put("/api/overlay/layout", json={"start_mode": "edit"})).status == 422
        await o.publish("veil", {"hidden": True})  # gilt auch für eine Seite, die erst jetzt kommt
        r = await c.get("/api/overlay/events")
        greeting = [json.loads((await r.content.readuntil(b"\n\n")).removeprefix(b"data: ")) for _ in range(5)]
        assert [m["event"] for m in greeting] == ["widgets", "layout", "dps", "schedule", "veil"]
        assert greeting[0]["payload"][0]["id"] == "meter" and greeting[4]["payload"] == {"hidden": True}
        r.close()


async def test_modules_changed_tells_the_page(tmp_path):
    o = overlay(tmp_path)
    q: asyncio.Queue = asyncio.Queue(8)
    o.clients.add(q)
    o.module_on = lambda module: module == "aion2.dps"
    await o.modules_changed()
    [(event, widgets)] = events(q)
    assert event == "widgets" and [w["id"] for w in widgets if w["active"]] == ["meter", "boss"]


async def test_close_clients_ends_open_streams(tmp_path):
    """Beim Beenden des Daemons darf aiohttp nicht auf offene Event-Streams warten."""
    o = overlay(tmp_path)
    app = web.Application()
    o.add_routes(app)
    async with TestClient(TestServer(app)) as c:
        r = await c.get("/api/overlay/events")
        for _ in ("widgets", "layout", "dps", "schedule"):  # Begrüßung
            await r.content.readuntil(b"\n\n")
        assert len(o.clients) == 1
        o.close_clients()
        assert await asyncio.wait_for(r.content.read(), 2) == b""  # Server hat beendet
        assert not o.clients


def test_layout_of_version_1_is_translated(tmp_path):
    """Deutsche Schlüssel, Radar als ein großes Fenster, eigenes PvP-Widget, Boss-Schalter am Widget."""
    old = {"version": 1, "fx": "holo", "profil": "PvE",
           "widgets": {"meter": {"enabled": True, "x": 4, "y": 181, "scale": 1.0, "opacity": 1.0},
                       "boss": {"enabled": False, "x": None, "y": None, "show_ttk": False, "hide_idle": True},
                       "timers": {"enabled": True, "x": 120, "y": 41, "events": [{"name": "Riss"}]},
                       "radar": {"enabled": True, "x": 0, "y": 256, "width": 400, "height": 856},
                       "warnung": {"enabled": True, "opacity": 0.73},
                       "pvp": {"enabled": False, "x": 2296, "y": 1208}},
           "profile": {"PvE": ["meter", "timers", "radar", "warnung"], "PvP": ["pvp"]}}
    (tmp_path / "overlay").mkdir()
    (tmp_path / "overlay" / "layout.json").write_text(json.dumps(old))
    layout = overlay(tmp_path).layout
    assert layout.version == 2 and layout.fx == "holo" and layout.profile == "PvE"
    assert layout.profiles == {"PvE": ["meter", "timers", "cube", "warnings"], "PvP": []}
    w = layout.widgets
    assert (w["meter"].x, w["meter"].y) == (4, 181) and w["timers"].enabled
    assert w["boss"].options == {"show_ttk": False, "hide_idle": True} and not w["boss"].enabled
    assert w["warnings"].opacity == 0.73
    # das Cube-Radar übernimmt vom alten Fenster nur an/aus, die Karte ist neu und aus
    assert w["cube"].enabled and w["cube"].x is None and not w["map"].enabled
    assert "pvp" not in w and "radar" not in w


async def test_resizable_widget_keeps_its_size(tmp_path):
    import pydantic
    o = overlay(tmp_path)
    await o.update({"widgets": {"map": {"width": 700, "height": 400}}})
    saved = overlay(tmp_path).layout.widgets["map"]
    assert (saved.width, saved.height) == (700, 400)
    with pytest.raises(pydantic.ValidationError):
        await o.update({"widgets": {"map": {"width": 10}}})
    await o.update({"widgets": {"boss": {"width": 500, "height": 300}}})  # lässt sich nicht ziehen: fällt weg
    assert o.layout.widgets["boss"].width is None
