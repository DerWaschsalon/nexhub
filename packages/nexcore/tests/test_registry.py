import asyncio

import yaml

from nexcore import Context, EventBus, Module, ModuleInfo, Paths, Registry
from nexcore.registry import CHANGED

LOG: list[str] = []


class Basis(Module):
    info = ModuleInfo("basis", "Basis", "system", "cog", "", default=True)

    async def start(self):
        LOG.append("basis an")
        self.spawn(self.arbeit)

    async def stop(self):
        LOG.append("basis aus")

    async def arbeit(self):
        await asyncio.Event().wait()


class Aufbau(Module):
    info = ModuleInfo("aufbau", "Aufbau", "system", "cog", "", requires=("basis",))

    async def start(self):
        LOG.append("aufbau an")
        self.on("ping", lambda _: LOG.append("aufbau ping"))


class Oben(Module):
    info = ModuleInfo("oben", "Oben", "system", "cog", "", requires=("aufbau",))


def registry(tmp_path, initial=None):
    ctx = Context(EventBus(), Paths("test"))
    return Registry(ctx.bus, [Basis(ctx), Aufbau(ctx), Oben(ctx)], tmp_path / "modules.yaml", initial)


async def test_standard_und_speichern(tmp_path):
    r = registry(tmp_path)
    assert r.enabled == {"basis"}
    assert yaml.safe_load((tmp_path / "modules.yaml").read_text()) == {"enabled": ["basis"]}


async def test_abhaengigkeiten(tmp_path):
    r = registry(tmp_path, initial=lambda: {"oben"})  # bringt aufbau und basis mit
    assert r.enabled == {"basis", "aufbau", "oben"}
    assert r.dependents("basis") == {"aufbau", "oben"}
    assert [m["id"] for m in r.info()] == ["basis", "aufbau", "oben"]


async def test_ein_und_aus_mit_aufraeumen(tmp_path):
    LOG.clear()
    r = registry(tmp_path)
    changed = []
    r.bus.on(CHANGED, changed.append)
    await r.start()
    assert await r.set("aufbau", True) == ["aufbau"]
    await r.bus.emit("ping")
    assert await r.set("basis", False) == ["basis", "aufbau"]  # Abhängige gehen mit
    await r.bus.emit("ping")  # Abo von aufbau ist weg
    assert LOG == ["basis an", "aufbau an", "aufbau ping", "basis aus"]
    assert changed == [["aufbau"], ["basis", "aufbau"]]
    assert not r.modules["basis"]._tasks and not r.modules["basis"].active and not r.modules["oben"].active
    assert await r.set("basis", False) == []


async def test_kaputte_datei_nimmt_standard(tmp_path):
    (tmp_path / "modules.yaml").write_text("enabled: [gibtsnicht, aufbau]")
    assert registry(tmp_path).enabled == {"aufbau", "basis"}
    (tmp_path / "modules.yaml").write_text(":::")
    assert registry(tmp_path).enabled == {"basis"}
