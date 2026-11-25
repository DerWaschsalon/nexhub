"""Ersteinrichtung: Vorlagen schalten Module ein, Voraussetzungen werden nur angezeigt."""
import pytest

from deckbar_daemon.setup import REQUIREMENTS, TEMPLATES, Setup


class FakeModules:
    def __init__(self, enabled: set[str]) -> None:
        self.enabled = enabled

    async def set(self, mid: str, on: bool) -> list[str]:
        if mid in self.enabled:
            return []
        self.enabled.add(mid)
        return [mid]


def setup(enabled: set[str], missing: tuple[str, ...] = ()) -> tuple[Setup, list[str]]:
    profiles: list[str] = []

    async def choose(name: str) -> None:
        profiles.append(name)
    checks = {r.id: (lambda rid=r.id: rid not in missing) for r in REQUIREMENTS}
    return Setup(FakeModules(enabled), checks, choose), profiles


def test_vorlagen_nennen_nur_bekannte_module_und_voraussetzungen(tmp_path):
    from deckbar_daemon.app import NexBoard
    from deckbar_daemon.config import Settings
    known = NexBoard(Settings(token="testtoken123", mdns=False, usb="off"), tmp_path, mdns=False).modules.infos
    ids = {t.id for t in TEMPLATES}
    assert all(mid in known for t in TEMPLATES for mid in t.modules)
    assert all(set(r.templates) <= ids for r in REQUIREMENTS)


def test_info_zeigt_was_schon_an_ist_und_was_fehlt():
    s, _ = setup({"deck"}, missing=("tcpdump",))
    info = s.info()
    assert [t["id"] for t in info["templates"] if t["active"]] == ["bar"]
    assert [r["id"] for r in info["requirements"] if not r["ok"]] == ["tcpdump"]


async def test_uebernehmen_schaltet_ein_und_waehlt_das_profil():
    s, profiles = setup({"deck", "aion2.dps"})
    changed = await s.apply(["pve", "radar"])
    assert changed == ["aion2.overlay", "aion2.warnings", "aion2.schedule", "aion2.runs", "aion2.radar",
                       "aion2.field_bosses"]
    assert profiles == ["PvE"]
    assert await s.apply(["pve"]) == []  # zweites Mal: nichts mehr zu tun
    with pytest.raises(ValueError):
        await s.apply(["gibts-nicht"])
