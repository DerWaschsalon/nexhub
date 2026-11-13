#!/usr/bin/env python3
"""Ebenen einer Klassenfigur: je Ausrüstungsplatz ein Bild gleich groß wie die Figur, in dem nur dieser Platz
sichtbar ist (hub/web/static/klassen/figur/<klasse>-<platz>.webp, eingetragen in SLOT_LAYERS in
hub/web/src/modules/logs/data/figureZones.ts). Die Armory lässt damit beim Zeigen den Gegenstand selbst
leuchten und trifft ihn pixelgenau.

Die Umrisse kommen von Segment Anything (Meta, Apache-2.0): je Platz ein paar Punkte im Bild, „gehört dazu“
oder „gehört nicht dazu“. Haut wird vorher bestimmt und keinem Platz zugeschlagen (außer den Händen als
Handschuhe), der Umhang ist der Rest hinter der Figur. Was das Modell nicht sauber trennt (der dünne, dunkle
Bogen, der Arm vor der Spitze des Umhangs), kommt aus Farbe und Handumriss.

Einrichtung (einmalig, nur zum Erzeugen der Bilder, der Hub braucht nichts davon):
    uv venv -p 3.12 ~/.cache/figur-sam
    uv pip install -p ~/.cache/figur-sam/bin/python --index-url https://download.pytorch.org/whl/cpu torch torchvision
    uv pip install -p ~/.cache/figur-sam/bin/python segment-anything pillow numpy scipy
    curl -L -o ~/.cache/figur-sam/sam_vit_b_01ec64.pth \\
        https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth
Aufruf:
    ~/.cache/figur-sam/bin/python hub/tools/figure_layers.py ranger [vorschau.png]
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter

Mask = NDArray[np.bool_]
Point = tuple[int, int]
Box = tuple[int, int, int, int]

FIGURE_DIR = Path(__file__).resolve().parent.parent / "web" / "static" / "klassen" / "figur"
MODEL = Path.home() / ".cache" / "figur-sam" / "sam_vit_b_01ec64.pth"
MIN_ALPHA = 40  # ab dieser Deckkraft zählt ein Pixel zur Figur (wie in der Armory beim Treffen)
EDGE_BLUR = 0.7  # weiche Kante statt Treppen
ISLAND_SHARE = 0.08  # kleinere abgetrennte Stücke einer Maske sind Splitter (Bänder, Spitze)


@dataclass
class Query:
    """Eine Abfrage an das Modell: Punkte (x, y, 1 = dazu, 0 = nicht dazu), Rahmen und optional ein harter Rand"""

    points: list[tuple[int, int, int]]
    box: Box
    clip: Box | None = None


@dataclass
class ClassSpec:
    """Was für eine Klasse ausgeschnitten wird; `parts` in der Reihenfolge, in der die Plätze Pixel bekommen.
    Ohne Abfragen für Handschuhe zählen die Hände (`hands`) als Handschuhe (Figur ohne sichtbare Handschuhe).
    Zum Umhang kommt zu seinen Abfragen der Rest im Umriss `cape` (dunkle Flächen, die das Modell nicht
    trennt). `arm` ist ein Umriss, in dem Haut nur nach Farbe gesucht wird."""

    skin: list[Query]
    parts: dict[str, list[Query]]
    arm: list[Point] = field(default_factory=list)
    hands: list[Box] = field(default_factory=list)
    cape: list[Point] = field(default_factory=list)
    drawn: dict[str, Callable[[Figure], Mask]] = field(default_factory=dict)


class Figure:
    """Die Figur als Bild und Zahlen, mit den Hilfen zum Ausschneiden"""

    def __init__(self, cls: str) -> None:
        self.cls = cls
        self.image = Image.open(FIGURE_DIR / f"{cls}.webp").convert("RGBA")
        rgba = np.asarray(self.image).astype(int)
        self.r, self.g, self.b, self.alpha = (rgba[..., i] for i in range(4))
        self.lum = 0.3 * self.r + 0.59 * self.g + 0.11 * self.b
        self.sat = rgba[..., :3].max(-1) - rgba[..., :3].min(-1)

    @property
    def shape(self) -> tuple[int, int]:
        return self.alpha.shape[0], self.alpha.shape[1]

    def polygon(self, points: list[Point]) -> Mask:
        m = Image.new("L", self.image.size, 0)
        ImageDraw.Draw(m).polygon(points, fill=255)
        return np.asarray(m) > 0

    def lines(self, segments: list[tuple[Point, Point]], width: int) -> Mask:
        m = Image.new("L", self.image.size, 0)
        draw = ImageDraw.Draw(m)
        for start, end in segments:
            draw.line([start, end], fill=255, width=width)
        return np.asarray(m) > 0

    def boxes(self, boxes: list[Box]) -> Mask:
        m = np.zeros(self.shape, bool)
        for x0, y0, x1, y1 in boxes:
            m[y0:y1, x0:x1] = True
        return m

    def color_skin(self) -> Mask:
        """Haut auch im Schatten: Rot vor Grün klar vor Blau (Farbton 12-18 Grad; rosa Metall hat Grün = Blau),
        nur zusammenhängende Flächen, damit dünne Verzierungen nicht mitzählen"""
        raw = (self.alpha > MIN_ALPHA) & (self.r > 55) & (self.r - self.g >= 8) & (self.g - self.b >= 5)
        raw &= (self.r - self.b >= 18) & (self.r - self.b <= 90)
        m = Image.fromarray((raw * 255).astype("uint8"))
        m = m.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MaxFilter(5))
        return np.asarray(m) > 0

    def save_layer(self, slot: str, mask: Mask) -> Image.Image:
        """Speichert die Ebene eines Platzes und gibt ihre Deckkraft zurück"""
        soft = Image.fromarray((mask * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(EDGE_BLUR))
        alpha = Image.fromarray(np.minimum(np.asarray(soft), self.alpha).astype("uint8"))
        layer = self.image.copy()
        layer.putalpha(alpha)
        layer.save(FIGURE_DIR / f"{self.cls}-{slot.lower()}.webp", "WEBP", quality=90, method=6)
        return alpha


class Segmenter:
    """Segment Anything auf einer Figur: das Bild wird einmal eingelesen, dann beliebig viele Abfragen"""

    def __init__(self, figure: Figure) -> None:
        from segment_anything import SamPredictor, sam_model_registry

        # Hintergrund neutral grau, damit die Kante zum Durchsichtigen klar ist
        rgb = Image.new("RGB", figure.image.size, (128, 128, 128))
        rgb.paste(figure.image, mask=figure.image.split()[3])
        self.predictor = SamPredictor(sam_model_registry["vit_b"](checkpoint=str(MODEL)))
        self.predictor.set_image(np.asarray(rgb))
        self.figure = figure

    def mask(self, query: Query) -> Mask:
        coords = np.array([(x, y) for x, y, _ in query.points], float)
        labels = np.array([label for _, _, label in query.points])
        masks, scores, _ = self.predictor.predict(
            point_coords=coords, point_labels=labels, box=np.array(query.box, float), multimask_output=True
        )
        best: Mask = masks[int(np.argmax(scores))]
        if query.clip:
            best &= self.figure.boxes([query.clip])
        return without_islands(best)

    def union(self, queries: list[Query]) -> Mask:
        result = np.zeros(self.figure.shape, bool)
        for query in queries:
            result |= self.mask(query)
        return result


def without_islands(mask: Mask) -> Mask:
    """Kleine abgetrennte Stücke einer Maske entfernen"""
    from scipy import ndimage

    labels, count = ndimage.label(mask)
    if count <= 1:
        return mask
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    keep = [i + 1 for i, size in enumerate(sizes) if size >= max(sizes) * ISLAND_SHARE]
    kept: Mask = np.isin(labels, keep)
    return kept


def ranger_bow(fig: Figure) -> Mask:
    """Bogen: oberer Arm (heller, bronze verziert), unterer Arm (dunkel) und die frei liegende Sehne"""
    upper = fig.polygon([(565, 385), (640, 330), (860, 105), (1000, 85), (1000, 200), (950, 150), (905, 240),
                         (870, 420), (700, 505), (600, 475), (565, 455)])
    lower = fig.polygon([(0, 640), (30, 600), (100, 572), (118, 566), (130, 588), (200, 603), (266, 612),
                         (266, 652), (200, 642), (100, 622), (40, 632), (12, 672), (0, 675)])
    opaque = fig.alpha > MIN_ALPHA
    wood = upper & opaque & (fig.lum < 170) & (fig.sat < 90)
    dark = lower & opaque & (fig.lum < 95)
    string = fig.lines([((875, 160), (560, 345)), ((110, 575), (255, 505))], 7)
    string &= (fig.alpha > 20) & (fig.sat < 60) & (fig.lum > 110)
    bow: Mask = wood | dark | string
    return bow


CLASSES: dict[str, ClassSpec] = {
    "ranger": ClassSpec(
        skin=[
            Query([(430, 100, 1), (440, 150, 1), (470, 195, 1), (400, 40, 0), (480, 240, 0)], (395, 55, 520, 235)),
            Query([(295, 455, 1), (285, 480, 1), (250, 470, 0)], (258, 425, 335, 505)),
            Query([(556, 445, 1)], (535, 420, 578, 472)),
            Query([(370, 480, 1), (360, 580, 1), (360, 532, 0), (440, 520, 0)], (325, 445, 410, 610)),
            Query([(475, 490, 1), (475, 575, 1), (475, 535, 0), (420, 520, 0)], (435, 460, 520, 600)),
        ],
        arm=[(340, 215), (398, 212), (396, 330), (360, 370), (335, 410), (295, 410), (318, 345), (332, 280)],
        hands=[(258, 425, 335, 505), (535, 420, 578, 472)],
        drawn={"MainHand": ranger_bow},
        parts={
            "MainHand": [],
            "Boots": [
                Query([(320, 650, 1), (270, 840, 1), (290, 760, 1), (350, 560, 0), (200, 800, 0), (190, 720, 0)],
                      (195, 570, 395, 942)),
                Query([(475, 650, 1), (470, 880, 1), (470, 760, 1), (480, 560, 0), (400, 760, 0), (410, 820, 0),
                       (385, 690, 0)], (425, 560, 540, 942)),
            ],
            "Gloves": [],
            "Belt": [
                Query([(440, 352, 1), (425, 335, 1), (458, 338, 1), (440, 380, 1), (440, 300, 0), (420, 420, 0)],
                      (398, 312, 485, 398)),
                Query([(482, 370, 1), (510, 345, 1), (520, 390, 1), (500, 400, 0)], (455, 315, 548, 448)),
            ],
            "Shoulder": [
                Query([(380, 180, 1), (360, 205, 1), (410, 175, 1), (430, 100, 0), (450, 250, 0)],
                      (335, 135, 450, 242)),
                Query([(487, 180, 1), (470, 230, 0)], (460, 145, 515, 215)),
            ],
            # links des Kleids liegt der dunkle Umhang, das Modell trennt die beiden dunklen Flächen nicht
            "Torso": [
                Query([(450, 260, 1), (500, 235, 1), (420, 290, 1), (480, 205, 0), (440, 352, 0), (450, 420, 0),
                       (320, 300, 0), (375, 280, 0), (385, 230, 0), (370, 250, 0), (382, 310, 0), (390, 335, 0),
                       (362, 210, 0)], (398, 160, 565, 345), clip=(398, 150, 570, 345)),
            ],
            "Pants": [
                Query([(450, 420, 1), (380, 410, 1), (530, 400, 1), (500, 440, 1), (380, 480, 0), (470, 490, 0),
                       (440, 352, 0)], (330, 335, 580, 482)),
                Query([(360, 532, 1), (340, 525, 1), (370, 510, 0), (370, 570, 0)], (322, 508, 402, 566)),
                Query([(475, 535, 1), (500, 532, 1), (470, 510, 0), (470, 570, 0)], (440, 505, 520, 566)),
            ],
            # kein Helm an der Figur: gemeint ist der Schmuck im Haar
            "Helmet": [
                Query([(478, 40, 1), (470, 62, 1), (488, 15, 1), (420, 40, 0), (430, 100, 0)], (452, 0, 502, 85)),
            ],
            "Cape": [],
        },
        cape=[(140, 150), (348, 148), (356, 240), (396, 214), (396, 336), (336, 402), (336, 470), (446, 468),
              (446, 662), (434, 874), (396, 874), (346, 762), (334, 662), (272, 942), (140, 942)],
    ),
    "gladiator": ClassSpec(
        skin=[
            Query([(560, 95, 1), (560, 150, 1), (555, 205, 1), (540, 20, 0), (600, 290, 0)], (505, 40, 620, 245)),
            Query([(390, 330, 1), (430, 300, 1), (330, 370, 0), (480, 220, 0)], (330, 265, 470, 400)),
            Query([(720, 320, 1), (790, 335, 1), (840, 400, 0), (680, 250, 0)], (675, 275, 870, 365)),
            Query([(420, 750, 1), (430, 860, 1), (400, 690, 1), (420, 960, 0), (535, 800, 0)], (365, 640, 485, 935)),
            Query([(565, 750, 1), (575, 860, 1), (560, 690, 1), (600, 960, 0), (535, 800, 0)], (505, 640, 635, 935)),
        ],
        parts={
            "MainHand": [
                Query([(150, 900, 1), (150, 700, 1), (110, 250, 1), (40, 515, 1), (220, 505, 1), (80, 130, 1),
                       (120, 375, 0)], (0, 100, 252, 1385)),
            ],
            "Boots": [
                Query([(400, 955, 1), (340, 1100, 1), (330, 1200, 1), (320, 1290, 1), (420, 860, 0), (365, 1150, 0),
                       (460, 1130, 0)], (290, 900, 470, 1345)),
                Query([(620, 955, 1), (625, 1100, 1), (615, 1250, 1), (580, 860, 0)], (570, 900, 670, 1345)),
            ],
            "Gloves": [
                Query([(250, 375, 1), (300, 360, 1), (130, 375, 1), (390, 330, 0), (110, 300, 0)], (80, 330, 345, 410)),
                Query([(760, 430, 1), (840, 370, 1), (720, 460, 1), (760, 320, 0)], (690, 345, 870, 500)),
            ],
            "Belt": [
                Query([(520, 470, 1), (600, 470, 1), (550, 570, 0), (560, 380, 0)], (450, 430, 680, 520)),
            ],
            "Shoulder": [
                Query([(480, 180, 1), (460, 230, 1), (560, 150, 0)], (430, 120, 530, 290)),
                Query([(700, 200, 1), (720, 160, 1), (760, 330, 0)], (640, 120, 790, 300)),
            ],
            "Torso": [
                Query([(560, 330, 1), (520, 400, 1), (620, 380, 1), (560, 245, 0), (560, 560, 0)], (460, 200, 690, 470)),
                # Kragen
                Query([(535, 190, 1), (610, 180, 1), (570, 180, 0), (570, 130, 0)], (505, 130, 640, 230)),
            ],
            "Pants": [
                Query([(500, 580, 1), (600, 600, 1), (450, 620, 1), (430, 700, 0), (560, 470, 0)], (390, 500, 700, 670)),
            ],
            "Cape": [
                Query([(300, 1000, 1), (800, 1000, 1), (720, 700, 1), (860, 1200, 1), (420, 800, 0), (560, 800, 0)],
                      (240, 400, 926, 1375)),
            ],
        },
        cape=[(240, 460), (926, 460), (926, 1385), (240, 1385)],
    ),
    "templar": ClassSpec(
        skin=[Query([(430, 140, 1), (440, 185, 1), (420, 60, 0), (440, 230, 0)], (380, 60, 500, 210))],
        parts={
            "MainHand": [
                Query([(20, 540, 1), (100, 600, 1), (220, 700, 1), (400, 880, 1), (600, 1050, 1), (820, 1230, 1),
                       (185, 670, 0)], (0, 520, 890, 1280)),
                Query([(20, 545, 1), (70, 580, 1), (120, 620, 1), (180, 640, 0)], (0, 520, 200, 660)),
            ],
            "SubHand": [
                Query([(800, 500, 1), (850, 650, 1), (720, 780, 1), (780, 380, 1), (645, 680, 0), (620, 520, 0)],
                      (555, 300, 935, 860)),
            ],
            "Boots": [
                Query([(190, 1320, 1), (190, 1250, 0)], (130, 1260, 260, 1364)),
                Query([(600, 1285, 1), (640, 1295, 1), (560, 1230, 0)], (510, 1240, 700, 1320)),
            ],
            "Gloves": [
                Query([(180, 520, 1), (185, 650, 1), (165, 450, 1), (250, 300, 0)], (130, 400, 250, 710)),
                Query([(650, 680, 1), (620, 520, 1), (750, 500, 0), (560, 400, 0)], (580, 420, 690, 720)),
            ],
            "Shoulder": [
                Query([(250, 250, 1), (260, 150, 1), (230, 330, 1), (400, 300, 0)], (190, 95, 330, 400)),
                Query([(575, 230, 1), (560, 150, 1), (480, 300, 0)], (520, 115, 620, 320)),
            ],
            "Torso": [
                Query([(450, 350, 1), (450, 500, 1), (470, 600, 1), (400, 220, 1), (430, 140, 0), (430, 700, 0)],
                      (300, 170, 570, 650)),
                # dunkles Unterhemd neben der Brustplatte
                Query([(285, 420, 1), (290, 520, 1), (585, 420, 1), (200, 500, 0), (700, 500, 0)], (240, 250, 620, 620),
                      clip=(240, 250, 620, 600)),
            ],
            "Pants": [
                Query([(420, 700, 1), (500, 800, 1), (520, 1000, 1), (280, 950, 1), (470, 1150, 1), (100, 1000, 0),
                       (80, 1200, 0)], (200, 600, 620, 1260), clip=(195, 600, 640, 1270)),
            ],
            "Cape": [Query([(100, 1100, 1), (60, 1250, 1), (150, 900, 1)], (0, 600, 330, 1364))],
        },
        cape=[(0, 600), (340, 600), (340, 1364), (0, 1364)],
    ),
    "assassin": ClassSpec(
        skin=[
            Query([(490, 120, 1), (470, 160, 1), (490, 30, 0)], (440, 20, 560, 200)),
            Query([(700, 450, 1), (690, 520, 1), (740, 600, 0)], (640, 380, 760, 560)),
        ],
        parts={
            "MainHand": [
                Query([(100, 620, 1), (250, 520, 1), (380, 420, 1), (330, 470, 1), (570, 230, 1), (540, 280, 1),
                       (470, 300, 0), (300, 330, 0), (380, 300, 0), (440, 320, 0),
                       (350, 230, 0), (330, 270, 0)], (0, 215, 600, 705)),
            ],
            "SubHand": [
                Query([(830, 500, 1), (780, 600, 1), (780, 700, 1), (730, 660, 0), (730, 600, 0), (745, 640, 0)],
                      (700, 470, 880, 770)),
            ],
            "Boots": [
                Query([(400, 1270, 1), (330, 1300, 1), (420, 1150, 0)], (285, 1180, 485, 1335)),
                Query([(710, 1320, 1), (700, 1230, 0)], (655, 1250, 765, 1380)),
            ],
            "Gloves": [
                Query([(300, 330, 1), (380, 300, 1), (470, 300, 1), (350, 450, 0)], (235, 255, 525, 405)),
                Query([(730, 600, 1), (740, 680, 1), (830, 520, 0)], (690, 540, 800, 750)),
            ],
            # roter Kragen über den Schultern und der goldene Schulterschutz
            "Shoulder": [
                Query([(600, 250, 1), (450, 230, 1), (680, 350, 1), (490, 120, 0)], (390, 100, 735, 400)),
                Query([(350, 220, 1), (330, 260, 1), (300, 330, 0)], (295, 185, 410, 320)),
            ],
            "Belt": [
                Query([(400, 570, 1), (600, 560, 1), (500, 525, 1), (560, 650, 0)], (340, 505, 670, 610)),
                # rotes Tuch am Gürtel
                Query([(560, 650, 1), (520, 720, 1), (600, 700, 1), (450, 750, 0)], (460, 570, 670, 810)),
            ],
            "Torso": [
                Query([(500, 420, 1), (420, 450, 1), (600, 450, 1), (500, 250, 0), (500, 560, 0)], (340, 330, 680, 530)),
            ],
            "Pants": [
                Query([(420, 800, 1), (430, 950, 1), (660, 980, 1), (550, 850, 1), (850, 900, 0), (720, 800, 0),
                       (800, 1000, 0)], (340, 600, 760, 1250)),
            ],
            "Cape": [Query([(850, 900, 1), (800, 1100, 1), (740, 500, 1)], (640, 380, 934, 1230))],
        },
        cape=[(640, 380), (934, 380), (934, 1240), (640, 1240)],
    ),
}


def slot_mask(slot: str, spec: ClassSpec, fig: Figure, sam: Segmenter, skin: Mask) -> Mask:
    """Maske eines Platzes vor dem Abzug dessen, was frühere Plätze schon haben"""
    if slot in spec.drawn:
        return spec.drawn[slot](fig)
    if slot == "Gloves" and not spec.parts[slot]:
        return skin & fig.boxes(spec.hands)  # die Figur trägt keine sichtbaren Handschuhe: die Hände
    if slot == "Cape":
        rest = fig.polygon(spec.cape) if spec.cape else np.zeros(fig.shape, bool)
        return (sam.union(spec.parts[slot]) | rest) & ~skin
    return sam.union(spec.parts[slot]) & ~skin


def main(cls: str, preview: str | None = None) -> None:
    spec = CLASSES[cls]
    fig = Figure(cls)
    sam = Segmenter(fig)
    skin = sam.union(spec.skin)
    if spec.arm:
        skin |= fig.polygon(spec.arm) & fig.color_skin()
    taken = np.zeros(fig.shape, bool)
    shown = Image.new("RGBA", fig.image.size, (40, 40, 60, 255))
    shown.alpha_composite(fig.image)
    for i, slot in enumerate(spec.parts):
        own = slot_mask(slot, spec, fig, sam, skin) & ~taken & (fig.alpha > MIN_ALPHA)
        taken |= own
        alpha = fig.save_layer(slot, own)
        print(f"{slot}: {int(own.sum())} Pixel")
        tint = Image.new("RGBA", fig.image.size, PREVIEW_COLORS[i % len(PREVIEW_COLORS)])
        tint.putalpha(alpha.point(lambda v: 130 if v > MIN_ALPHA else 0))
        shown.alpha_composite(tint)
    if preview:
        shown.save(preview)


# Vorschau: jeder Platz in eigener Farbe über der Figur
PREVIEW_COLORS = [(255, 0, 80, 0), (0, 200, 255, 0), (255, 200, 0, 0), (120, 255, 0, 0), (255, 0, 255, 0),
                  (255, 120, 0, 0), (0, 255, 160, 0), (160, 80, 255, 0), (255, 255, 255, 0)]

if __name__ == "__main__":
    main(*sys.argv[1:3])
