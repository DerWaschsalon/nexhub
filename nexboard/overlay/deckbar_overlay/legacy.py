"""Click-Through per X11-Input-Shape für das alte Meter-Fenster unter XWayland."""
from __future__ import annotations

import ctypes

from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication


class InputShape:
    """Nur ein Rechteck des Fensters nimmt Maus an (XShapeCombineRectangles, ShapeInput). Leer = alles
    geht durch. Nur unter XWayland/X11."""

    class XRect(ctypes.Structure):
        _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short), ("w", ctypes.c_ushort), ("h", ctypes.c_ushort)]

    def __init__(self) -> None:
        self.ok = False
        if QGuiApplication.platformName() != "xcb":
            return
        try:
            self.x11 = ctypes.CDLL("libX11.so.6")
            self.xext = ctypes.CDLL("libXext.so.6")
            self.x11.XOpenDisplay.restype = ctypes.c_void_p
            self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self.x11.XFlush.argtypes = [ctypes.c_void_p]
            self.xext.XShapeCombineRectangles.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.POINTER(self.XRect), ctypes.c_int, ctypes.c_int, ctypes.c_int]
            self.dpy = self.x11.XOpenDisplay(None)
            self.ok = bool(self.dpy)
        except OSError:
            pass

    def set(self, wid: int, rects: list[QRect] | None) -> None:
        """rects None = ganzes Fenster klickbar, [] = nichts."""
        if not self.ok:
            return
        SHAPE_INPUT, SHAPE_SET = 2, 0
        if rects is None:
            rects = [QRect(0, 0, 32767, 32767)]
        arr = (self.XRect * max(1, len(rects)))(*[self.XRect(r.x(), r.y(), r.width(), r.height()) for r in rects])
        self.xext.XShapeCombineRectangles(self.dpy, wid, SHAPE_INPUT, 0, 0, arr, len(rects), SHAPE_SET, 0)
        self.x11.XFlush(self.dpy)
