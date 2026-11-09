import asyncio

from nexcore import EventBus


async def test_reihenfolge_fehler_und_abmelden():
    bus, got = EventBus(), []

    async def a(x):
        got.append(("a", x))

    def kaputt(_):
        raise RuntimeError("Empfänger kaputt")

    off = bus.on("t", a)
    bus.on("t", kaputt)
    bus.on("t", lambda x: got.append(("c", x)))
    await bus.emit("t", 1)  # der kaputte Empfänger hält die anderen nicht auf
    assert got == [("a", 1), ("c", 1)]
    off()
    off()  # zweimal abmelden schadet nicht
    await bus.emit("t", 2)
    assert got[-1] == ("c", 2) and ("a", 2) not in got


async def test_publish_ohne_warten():
    bus, got = EventBus(), asyncio.Event()
    bus.on("t", lambda _: got.set())
    bus.publish("t")
    await asyncio.wait_for(got.wait(), 1)
