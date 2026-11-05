"""Effekte auf dem Boss aus dem Capture (für /api/radar/kampf)."""
from deckbar_daemon.boss_effekte import BossEffekte, aktive

START = 1_000_000  # Kampfbeginn in ms seit 1970
REFLEXION = 16059101


def kampf(*spuren: dict) -> dict:
    return {"targetId": 47891, "startTimeMs": START, "durationMs": 20_000, "buffs": list(spuren)}


def test_nur_laufende_effekte_auf_dem_ziel():
    daten = kampf({"on": 47891, "id": REFLEXION, "segs": "16000,20000,1,10"},  # läuft noch
                  {"on": 47891, "id": 113900201, "segs": "300,1300,1,4;1300,11300,1,1"},  # abgelaufen
                  {"on": 344, "id": 20100, "segs": "0,20000,1,10"})  # auf einem Spieler
    assert aktive(daten, START + 18_000) == [{"id": REFLEXION, "seit": 2.0}]


def test_lange_offen_gilt_als_veraltet():
    # trifft niemand mehr, bleibt das Fenster des Captures stehen und der Effekt „läuft“ für immer
    daten = kampf({"on": 47891, "id": REFLEXION, "segs": "16000,20000,1,10"})
    assert aktive(daten, START + 40_000) == []


def test_ohne_daten_leer():
    assert aktive(None, 0) == []


class FakeCapture:
    def __init__(self, running: bool = True) -> None:
        self.running = running
        self.cmds: list[str] = []

    async def request(self, cmd: str, timeout: float = 5, **args):
        self.cmds.append(cmd)
        if cmd == "context":
            return {"currentTargetId": 47891}
        return kampf({"on": 47891, "id": REFLEXION, "segs": "16000,20000,1,10"})


async def test_fragt_capture_hoechstens_alle_02_s():
    uhr = [START / 1000 + 18]
    cap = FakeCapture()
    effekte = BossEffekte(cap, uhr=lambda: uhr[0])
    assert await effekte.aktuell() == [{"id": REFLEXION, "seit": 2.0}]
    uhr[0] += 0.1
    await effekte.aktuell()
    assert cap.cmds == ["context", "buffs"]
    uhr[0] += 0.2
    await effekte.aktuell()
    assert cap.cmds == ["context", "buffs", "context", "buffs"]


async def test_capture_aus_oder_fehler_leer():
    assert await BossEffekte(FakeCapture(running=False)).aktuell() == []

    class Kaputt(FakeCapture):
        async def request(self, cmd, timeout=5, **args):
            raise TimeoutError

    assert await BossEffekte(Kaputt()).aktuell() == []
