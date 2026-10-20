"""USB-Brücke gegen einen echten WebSocket-Server, das Gerät ist eine Attrappe ohne Serial."""
import asyncio

from aiohttp import WSMsgType, web

from deckbar_daemon.usb import BEACON, BEACON_WLAN, UsbBridge


class FakePort:
    path = "/dev/serial/by-id/fake"

    def __init__(self) -> None:
        self.lines: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.written: list[bytes] = []

    def write(self, payload: bytes) -> None:
        self.written.append(payload)

    def feed(self, *lines: bytes | None) -> None:
        for line in lines:
            self.lines.put_nowait(line)


async def _server():
    got: asyncio.Queue = asyncio.Queue()

    async def ws(request):
        sock = web.WebSocketResponse()
        await sock.prepare(request)
        await got.put("open")
        async for m in sock:
            if m.type == WSMsgType.TEXT:
                await got.put(m.data)
        await got.put("close")
        return sock

    app = web.Application()
    app.router.add_get("/ws", ws)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"ws://127.0.0.1:{port}/ws", got


async def _until(pred, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while not pred():
        assert asyncio.get_running_loop().time() < end, "Zeitüberschreitung"
        await asyncio.sleep(0.01)


async def test_wlan_hat_vorrang():
    runner, url, got = await _server()
    try:
        dev = FakePort()
        link = asyncio.ensure_future(UsbBridge("auto", url)._link(dev, BEACON_WLAN))

        # Gerät im WLAN: Brücke bleibt still
        dev.feed(b"@@" + BEACON_WLAN, b"[I] Log-Zeile")
        await asyncio.sleep(0.1)
        assert dev.written == [] and got.empty()

        # WebSocket weg, Gerät möchte USB
        dev.feed(b"@@" + BEACON)
        assert await asyncio.wait_for(got.get(), 3) == "open"
        await _until(lambda: b"OPEN" in dev.written)
        dev.feed(b'@@{"type":"hello"}')
        assert await asyncio.wait_for(got.get(), 3) == '{"type":"hello"}'

        # WLAN wieder da: Sitzung zu, kein CLOSE ans Gerät
        dev.feed(b"@@" + BEACON_WLAN)
        assert await asyncio.wait_for(got.get(), 3) == "close"
        await asyncio.sleep(0.1)
        assert b"CLOSE" not in dev.written

        # erneuter Rückfall, dann abgesteckt
        dev.feed(b"@@" + BEACON)
        assert await asyncio.wait_for(got.get(), 3) == "open"
        dev.feed(None)
        assert await asyncio.wait_for(got.get(), 3) == "close"
        await asyncio.wait_for(link, 3)
    finally:
        await runner.cleanup()


async def test_neustart_im_usb_betrieb():
    runner, url, got = await _server()
    try:
        dev = FakePort()
        link = asyncio.ensure_future(UsbBridge("auto", url)._link(dev, BEACON))
        assert await asyncio.wait_for(got.get(), 3) == "open"
        dev.feed(b"@@" + BEACON)  # Gerät neu gestartet, möchte weiter USB
        assert await asyncio.wait_for(got.get(), 3) == "close"
        assert await asyncio.wait_for(got.get(), 3) == "open"
        await _until(lambda: dev.written.count(b"OPEN") == 2)
        dev.feed(None)
        await asyncio.wait_for(link, 3)
    finally:
        await runner.cleanup()
