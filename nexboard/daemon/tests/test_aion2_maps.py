"""Karten: Eichung Welt ↔ Bild, gesehene Spawnpunkte, mitgelieferte Karten; dazu die Blickrichtung aus der
Minikarte und der Sprecher."""
import math
import random
import threading
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from deckbar_daemon.aion2 import maps
from deckbar_daemon.aion2.maps import Calibration, GameMap
from deckbar_daemon.aion2.minimap import heading, view_direction
from deckbar_daemon.aion2.spawn_points import SpawnPoints
from deckbar_daemon.core.speech import Speaker

DATA = Path(__file__).parent / "data"


def north_up(x: float, y: float) -> tuple[float, float]:
    """Testkarte: +x = Nord (oben), +y = Ost (rechts), 1 px = 10 m, Ursprung bei (500, 400)."""
    return 500 + y / 1000, 400 - x / 1000


def mirrored(x: float, y: float) -> tuple[float, float]:
    return 500 - y / 1000, 400 - x / 1000


def test_zwei_punkte_ohne_spiegelung():
    calibration = Calibration()
    for x, y in ((0, 0), (50000, 20000)):
        calibration.add(x, y, *north_up(x, y))
    for x, y in ((-30000, 70000), (12345, -6789)):
        u, v = calibration.to_image(x, y)
        assert (u, v) == pytest.approx(north_up(x, y), abs=1e-6)
        assert calibration.to_world(u, v) == pytest.approx((x, y), abs=1e-3)


def test_drei_punkte_affin_mit_spiegelung_und_einer_reicht_nicht():
    calibration = Calibration()
    for x, y in ((0, 0), (50000, 20000), (-10000, 40000)):
        calibration.add(x, y, *mirrored(x, y))
    assert calibration.to_image(30000, -5000) == pytest.approx(mirrored(30000, -5000), abs=1e-6)
    assert calibration.error_px() < 1e-6
    assert not Calibration([(0, 0, 1, 1)]).ready


def test_gleicher_spawnpunkt_wird_zusammengefasst(tmp_path):
    points = SpawnPoints(tmp_path / "p.json")
    points.add(1000, 1000, 0, 1000295)
    points.add(1100, 1050, 0, 1000295)  # 1,1 m daneben
    points.add(9000, 1000, 0, 1000295)  # 80 m weg
    assert [p["anzahl"] for p in points.all()] == [2, 1]
    assert len(SpawnPoints(tmp_path / "p.json").all()) == 2  # gespeichert
    assert points.remove(1200, 1000, 500) and not points.remove(1200, 1000, 500)
    assert len(points.all()) == 1


def test_mitgelieferte_karten_werden_einmal_kopiert(tmp_path, monkeypatch):
    bundled, own = tmp_path / "repo", tmp_path / "eigen"
    (bundled / "Testland").mkdir(parents=True)
    (bundled / "Testland" / "bild.webp").write_bytes(b"x")
    monkeypatch.setattr(maps, "BUNDLED", bundled)
    monkeypatch.setattr(maps, "MAPS", own)
    assert [m.name for m in GameMap.all()] == ["Testland"]
    assert GameMap("Testland").image.name == "bild.webp"
    (own / "Testland" / "bild.webp").write_bytes(b"eigen")
    GameMap.all()  # vorhandene Karte wird nicht überschrieben
    assert (own / "Testland" / "bild.webp").read_bytes() == b"eigen"


def test_karten_im_repo_liegen_dort_wo_der_code_sie_sucht():
    assert (maps.BUNDLED / "Altgard").is_dir()


# ---------------------------------------------------------------- Minikarte
def minimap_image(look: float | None) -> Image.Image:
    """Minikarte wie im Spiel: fleckige Landschaft, heller Innenkreis, zwei weiße Linien um die
    Blickrichtung (112 Grad auseinander) und weiße Quest-Punkte, die nichts verfälschen dürfen."""
    rng = random.Random(1)
    image = Image.new("RGB", (238, 238), (120, 110, 80))
    draw = ImageDraw.Draw(image)
    for _ in range(300):  # Gelände
        x, y = rng.randrange(238), rng.randrange(238)
        draw.ellipse((x, y, x + 12, y + 12), fill=(rng.randrange(70, 150), rng.randrange(70, 140), 60))
    draw.ellipse((62, 62, 176, 176), fill=(190, 170, 130))
    if look is not None:
        for degrees in (look - 56, look + 56):
            rad = math.radians(degrees)
            draw.line((119 + 57 * math.sin(rad), 119 - 57 * math.cos(rad),
                       119 + 170 * math.sin(rad), 119 - 170 * math.cos(rad)), fill=(250, 245, 230), width=2)
    for _ in range(25):  # Quest-Punkte überall
        x, y = rng.randrange(10, 220), rng.randrange(10, 220)
        draw.ellipse((x, y, x + 8, y + 8), fill=(250, 250, 250))
    return image


def angle_gap(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def test_blickrichtung_ist_die_mitte_zwischen_den_linien():
    for wanted in (0, 55, 140, 270, 330):
        found = view_direction(minimap_image(wanted))
        assert found is not None and angle_gap(found, wanted) <= 5, wanted
    assert view_direction(minimap_image(None)) is None  # ohne Linien keine Richtung


def test_echtes_bild_mit_dunklem_kegel():
    """Bild vom 05.11.2026: Pfeil nach Südwest, die Fläche im Kegel ist dunkler als der Rest."""
    found = view_direction(Image.open(DATA / "minikarte-suedwest.png"))
    assert found is not None and angle_gap(found, 228) <= 6


def test_richtung_als_weltvektor():
    """Norden = Welt -y, Osten = +x (wie World.heading)."""
    assert heading(0) == pytest.approx((0, -1))
    assert heading(90) == pytest.approx((1, 0))


# ---------------------------------------------------------------- Sprecher
class Playback:
    """Ein abspielender Satz, den der Test selbst beendet."""

    def __init__(self, text: str, log: list) -> None:
        self.text, self.log, self.done = text, log, threading.Event()

    def wait(self) -> None:
        self.done.wait(2)

    def terminate(self) -> None:
        self.log.append(("abgebrochen", self.text))
        self.done.set()


def test_wichtiger_satz_bricht_boss_zeile_ab():
    log, playing = [], []
    started = threading.Semaphore(0)

    def player(file: Path) -> Playback:
        playback = Playback(str(file), log)
        playing.append(playback)
        started.release()
        return playback
    speaker = Speaker(lambda: "de", player)
    speaker.say("eins", important=False)
    started.acquire(timeout=2)
    speaker.say("zwei", important=False)
    speaker.say("drei", important=False)  # zwei warten schon: fällt weg
    assert [text for text, _ in speaker.waiting] == ["zwei"]
    speaker.say("jetzt", important=True)  # bricht die Boss-Zeile ab und verwirft den Stau
    assert [text for text, _ in speaker.waiting] == ["jetzt"]
    assert len(log) == 1
    for playback in playing:
        playback.done.set()
