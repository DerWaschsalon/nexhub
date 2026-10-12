"""a2ui.py: Dateien der Meter-Oberfläche, Shim in index.html, Commands ohne laufendes Programm."""
import json

from deckbar_daemon import a2ui
from deckbar_daemon.a2ui import A2Ui, inject_shim, member_jobs, resolve, summaries


def test_resolve_wie_vite(tmp_path):
    (tmp_path / "public" / "src" / "js").mkdir(parents=True)
    (tmp_path / "public" / "src" / "js" / "core.js").write_text("x")
    (tmp_path / "public" / "assets").mkdir()
    (tmp_path / "public" / "assets" / "검성.png").write_bytes(b"png")
    (tmp_path / "src" / "data" / "i18n" / "ui").mkdir(parents=True)
    (tmp_path / "src" / "data" / "i18n" / "ui" / "en.json").write_text("{}")
    (tmp_path / "src" / "data" / "skill_icons.json").write_text("{}")
    (tmp_path / "index.html").write_text("<html>")
    (tmp_path.parent / "geheim.txt").write_text("nein")
    assert resolve("/src/js/core.js", tmp_path).name == "core.js"
    assert resolve("/assets/%EA%B2%80%EC%84%B1.png", tmp_path).name == "검성.png"
    assert resolve("/i18n/ui/en.json", tmp_path).name == "en.json"
    assert resolve("/data/skill_icons.json", tmp_path).name == "skill_icons.json"
    assert resolve("/", tmp_path).name == "index.html"
    assert resolve("/../geheim.txt", tmp_path) is None
    assert resolve("/data/../../geheim.txt", tmp_path) is None


def test_shim_vor_allen_skripten():
    html = '<head><meta charset="utf-8"><script src="/a.js"></script></head>'
    out = inject_shim(html)
    assert out.index(a2ui.SHIM_URL) < out.index("/a.js")


def test_history_ohne_programm(tmp_path):
    rec = {"id": "f1", "bossName": "Boss", "startTimeMs": 5, "durationMs": 60000, "totalDamage": 9,
           "jobs": ["치유성"], "actors": [{"job": "치유성", "dbid": 1, "nickname": "A"}, {"job": "검성", "dbid": 0}]}
    (tmp_path / "f1.json").write_text(json.dumps(rec))
    (tmp_path / "kaputt.json").write_text("{")
    s = summaries(tmp_path)
    assert [f["id"] for f in s] == ["f1"] and s[0]["memberJobs"] == ["치유성"] and s[0]["isLive"] is False
    assert member_jobs({"actors": [{"job": "검성", "nickname": "12345"}, {"job": "궁성", "nickname": "Bob"}]}) == ["궁성"]


class FakeCapture:
    running = False
    status: dict = {}
    data_listeners: list = []

    async def request(self, *a, **k):
        raise AssertionError("darf ohne laufendes Programm nicht gerufen werden")

    async def set_full(self, on):
        pass


async def test_commands_ohne_programm(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("DECKBAR_A2TOOLS_SETTINGS", str(tmp_path / "a2.json"))
    (tmp_path / "a2.json").write_text(json.dumps({"dpsMeter.language": "de", "dpsMeter.streamOverlayKey": "geheim",
                                                  "window.x": "5", "dpsMeter.playerLimit": "6"}))
    ui = A2Ui(FakeCapture(), tmp_path / "a2-settings.json")
    # Erster Start übernimmt die Einstellungen des Meters, ohne Schlüssel und Fensterlage
    assert await ui.call("get_settings", {}) == {"dpsMeter.language": "de", "dpsMeter.playerLimit": "6"}
    assert await ui.call("build_features", {}) == {"online": False}
    await ui.call("update_settings", {"key": "theme", "value": "dark"})
    assert json.loads((tmp_path / "a2-settings.json").read_text())["theme"] == "dark"
    assert await ui.call("get_fight_history", {}) == []
    assert (await ui.call("get_capture_status", {}))["locked"] is False
    assert await ui.call("get_aion2_window_title", {}) is None
    try:
        await ui.call("load_fight", {"id": "../x"})
        raise AssertionError("ungültige ID angenommen")
    except ValueError:
        pass
