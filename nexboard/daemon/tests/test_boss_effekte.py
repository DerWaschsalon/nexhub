"""Effekte auf dem Boss aus dem Capture (für /api/radar/kampf)."""
from deckbar_daemon.boss_effekte import BossEffekte, aktive

START = 1_000_000  # Kampfbeginn in ms seit 1970
REFLEXION = 16059101
PRAEZISION = 140900171  # „Letalität“ vom Markierungsschuss


def kampf(*spuren: dict) -> dict:
    return {"targetId": 47891, "startTimeMs": START, "durationMs": 20_000, "buffs": list(spuren)}


def test_nur_laufende_effekte_auf_dem_ziel():
    daten = kampf({"on": 47891, "id": REFLEXION, "segs": "16000,20000,1,10"},  # läuft noch
                  {"on": 47891, "id": 113900201, "segs": "300,1300,1,4;1300,11300,1,1"},  # abgelaufen
                  {"on": 344, "id": 20100, "segs": "0,20000,1,10"})  # auf einem Spieler
    assert aktive(daten, START + 18_000, 47891) == [{"id": REFLEXION, "seit": 2.0}]
    assert aktive(daten, START + 18_000, 344) == [{"id": 20100, "seit": 18.0}]  # eigene Effekte


def test_lange_ohne_treffer_gilt_als_veraltet():
    # trifft niemand mehr, bleibt das Fenster des Captures stehen und der Effekt „läuft“ für immer
    daten = kampf({"on": 47891, "id": REFLEXION, "segs": "16000,20000,1,10"})
    assert aktive(daten, START + 29_000, 47891) != []  # 9 s ohne Treffer: noch gültig
    assert aktive(daten, START + 31_000, 47891) == []


def test_ohne_daten_oder_ohne_eigene_id_leer():
    assert aktive(None, 0, 47891) == []
    assert aktive(kampf({"on": 344, "id": 1, "segs": "0,1,1,10"}), START, None) == []


class FakeCapture:
    def __init__(self, running: bool = True) -> None:
        self.running = running
        self.cmds: list[str] = []
        self.data_listeners: list = []

    async def request(self, cmd: str, timeout: float = 5, **args):
        self.cmds.append(cmd)
        if cmd == "context":
            return {"currentTargetId": 47891}
        return kampf({"on": 47891, "id": REFLEXION, "segs": "16000,20000,1,10"},
                     {"on": 344, "id": PRAEZISION, "segs": "17000,20000,1,10"})


async def test_fragt_capture_hoechstens_alle_02_s():
    uhr = [START / 1000 + 18]
    cap = FakeCapture()
    effekte = BossEffekte(cap, uhr=lambda: uhr[0])
    assert (await effekte.aktuell())["eigene_effekte"] is None  # eigene ID noch unbekannt
    await cap.data_listeners[0]("dps", {"localPlayerId": 344})
    uhr[0] += 0.3
    assert await effekte.aktuell() == {"boss_effekte": [{"id": REFLEXION, "seit": 2.3}],
                                       "eigene_effekte": [{"id": PRAEZISION, "seit": 1.3}]}
    uhr[0] += 0.1
    await effekte.aktuell()
    assert cap.cmds == ["context", "buffs"] * 2  # 0,1 s später: aus dem Zwischenspeicher
    uhr[0] += 0.2
    await effekte.aktuell()
    assert cap.cmds == ["context", "buffs"] * 3


async def test_capture_aus_oder_fehler_leer():
    leer = {"boss_effekte": [], "eigene_effekte": None}
    assert await BossEffekte(FakeCapture(running=False)).aktuell() == leer

    class Kaputt(FakeCapture):
        async def request(self, cmd, timeout=5, **args):
            raise TimeoutError

    assert await BossEffekte(Kaputt()).aktuell() == leer
