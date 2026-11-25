"""Effekte auf dem Boss aus dem Mitschnitt (für /api/m/aion2.effects). Welche laufen, rechnet der Mitschnitt
(capture/src/effects.rs, dort auch die Tests dazu); hier nur Zwischenspeicher und Fehlerfälle."""
from deckbar_daemon.effects import EMPTY, ActiveEffects

ANTWORT = {"boss_effekte": [{"id": 16059101, "seit": 2.3}], "eigene_effekte": [{"id": 140900171, "seit": 1.3}]}


class FakeCapture:
    def __init__(self, running: bool = True) -> None:
        self.running = running
        self.cmds: list[str] = []

    async def request(self, cmd: str, timeout: float = 5, **args):
        self.cmds.append(cmd)
        return ANTWORT


async def test_fragt_capture_hoechstens_alle_02_s():
    uhr = [1000.0]
    cap = FakeCapture()
    effekte = ActiveEffects(cap, clock=lambda: uhr[0])
    assert await effekte.current() == ANTWORT
    uhr[0] += 0.1
    await effekte.current()
    assert cap.cmds == ["active_effects"]  # 0,1 s später: aus dem Zwischenspeicher
    uhr[0] += 0.2
    await effekte.current()
    assert cap.cmds == ["active_effects"] * 2


async def test_capture_aus_oder_fehler_leer():
    assert await ActiveEffects(FakeCapture(running=False)).current() == EMPTY

    class Kaputt(FakeCapture):
        async def request(self, cmd, timeout=5, **args):
            raise TimeoutError

    assert await ActiveEffects(Kaputt()).current() == EMPTY
