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
    assert yaml.safe_load((tmp_path / "modules.yaml").read_text()) == {"enabled": ["basis"],
                                                                       "known": ["basis", "aufbau", "oben"]}


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


class Neu(Module):
    info = ModuleInfo("neu", "Neu", "system", "cog", "", requires=("aufbau",), default=True)


def mit_neuem(tmp_path, introduced=frozenset()):
    ctx = Context(EventBus(), Paths("test"))
    mods = [Basis(ctx), Aufbau(ctx), Oben(ctx), Neu(ctx)]
    return Registry(ctx.bus, mods, tmp_path / "modules.yaml", introduced=introduced)


async def test_neues_standardmodul_geht_einmal_an(tmp_path):
    (tmp_path / "modules.yaml").write_text("enabled: [aufbau]\nknown: [basis, aufbau, oben]\n")
    assert mit_neuem(tmp_path).enabled == {"basis", "aufbau", "neu"}
    r = mit_neuem(tmp_path)
    await r.set("neu", False)
    assert mit_neuem(tmp_path).enabled == {"basis", "aufbau"}  # bleibt aus, es ist jetzt bekannt


async def test_neues_standardmodul_ohne_seine_voraussetzung_bleibt_aus(tmp_path):
    (tmp_path / "modules.yaml").write_text("enabled: [basis]\nknown: [basis, aufbau, oben]\n")
    assert mit_neuem(tmp_path).enabled == {"basis"}
    assert "neu" in yaml.safe_load((tmp_path / "modules.yaml").read_text())["known"]


async def test_alte_datei_ohne_known(tmp_path):
    # Vor `known`: nur was der Host als neu nennt, gilt als neu; basis (auch Standard) bleibt aus
    (tmp_path / "modules.yaml").write_text("enabled: []\n")
    assert mit_neuem(tmp_path, introduced=frozenset({"neu"})).enabled == set()
    (tmp_path / "modules.yaml").write_text("enabled: [basis, aufbau]\n")
    assert mit_neuem(tmp_path, introduced=frozenset({"neu"})).enabled == {"basis", "aufbau", "neu"}
