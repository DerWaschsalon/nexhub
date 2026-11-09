import pytest
from pydantic import BaseModel, Field, ValidationError

from nexcore import EventBus
from nexcore.errors import invalid
from nexcore.gamewatch import GameWatch
from nexcore.proc import MISSING, run
from nexcore.sse import SseHub


async def test_gamewatch_mit_nachlauf(monkeypatch):
    bus, events, laeuft = EventBus(), [], [True]
    bus.on("game.started", lambda n: events.append(("an", n)))
    bus.on("game.stopped", lambda n: events.append(("aus", n)))
    jetzt = [100.0]
    monkeypatch.setattr("nexcore.gamewatch.time.monotonic", lambda: jetzt[0])
    w = GameWatch(bus, "aion2", lambda: laeuft[0], grace_s=20)
    await w.check()
    laeuft[0], jetzt[0] = False, 110.0
    await w.check()  # kurz weg: zählt noch als laufend
    jetzt[0] = 125.0
    await w.check()
    assert events == [("an", "aion2"), ("aus", "aion2")]


async def test_sse_anfang_meldung_und_schluss():
    hub = SseHub(queue_max=2)
    stream = hub.stream(first=["event: start\ndata: 1\n\n"])
    assert await anext(stream) == b": hallo\n\n"
    assert await anext(stream) == b"event: start\ndata: 1\n\n"
    for n in range(3):  # Warteschlange voll: die älteste Meldung fällt weg
        hub.publish("dps", {"n": n})
    assert await anext(stream) == b'event: dps\ndata: {"n": 1}\n\n'
    hub.close_all()
    assert await anext(stream) == b'event: dps\ndata: {"n": 2}\n\n'
    assert [x async for x in stream] == []
    assert hub.listeners == 0


async def test_proc():
    assert (await run("sh", "-c", "echo hallo")).out == "hallo\n"
    assert (await run("cat", stdin=b"x")).out == "x"
    assert (await run("gibt-es-nicht-xyz")).code == MISSING
    assert not (await run("sleep", "5", timeout=0.1)).ok


def test_fehlerformat():
    class Eingabe(BaseModel):
        port: int = Field(ge=1)

    with pytest.raises(ValidationError) as info:
        Eingabe(port=0)
    e = invalid(info.value)
    assert e.status == 422 and e.body() == {"error": "port: Input should be greater than or equal to 1"}
