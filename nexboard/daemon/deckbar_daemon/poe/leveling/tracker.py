"""Wo man im Guide steht (Leveltracker_Progress, „+“/„-“ im Original).

Der aktuelle Schritt endet mit dem Betreten seiner Zielzone (letzte „areaid“ der Seite); dann geht es
von selbst eine Seite weiter, nie zurück. Nach Blättern von Hand wartet das kurz, damit ein Zonenwechsel
im selben Moment nicht gleich noch eine Seite überspringt.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from .terms import AREA, COMMENT, END_MARKERS, HINT, Options, Page

MANUAL_GRACE_S = 2.0
FAST_FORWARD_LIMIT = 1000  # Sicherung gegen eine Endlosschleife bei kaputtem Guide
CANCEL_GRACE_S = 30.0  # nach dem Schnellvorlauf darf die nächste Zone sofort weiterschalten


def strip_comment(line: str) -> str:
    cut = line.find(COMMENT)
    return line[:cut] if cut >= 0 else line


def area_tokens(line: str) -> list[str]:
    return [token.replace(AREA, "") for token in line.split(" ") if AREA in token]


class Tracker:
    def __init__(self, pages: list[Page], options: Options, progress: int = 0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.pages = pages
        self.options = options
        self.progress = progress  # Index der aktuellen Seite
        self.clock = clock
        self.last_manual = -MANUAL_GRACE_S
        self.lines: list[str] = []  # Zeilen der aktuellen Seite ohne Kommentare
        self.target_area = ""
        self.refresh()

    def _applies(self, index: int) -> bool:
        return index >= len(self.pages) or self.pages[index].applies(self.options)

    def refresh(self) -> None:
        while not self._applies(self.progress):
            self.progress += 1
        self.progress = max(min(self.progress, len(self.pages) - 1), 0)
        page = self.pages[self.progress] if self.pages else Page([])
        self.lines = [strip_comment(line) for line in page.lines]
        self.target_area = ""
        for line in self.lines:
            if self.options.skips(line) or HINT in line:
                continue
            for area in area_tokens(line):
                self.target_area = area

    def at_end(self) -> bool:
        following = self.progress + 1
        while not self._applies(following):
            following += 1
        if following >= len(self.pages):
            return True
        last = self.pages[-1].lines
        return bool(self.lines and last and self.lines[-1] == strip_comment(last[-1]))

    def _step(self) -> None:
        self.progress += 1
        while not self._applies(self.progress) and self.progress + 1 != len(self.pages):
            self.progress += 1
        self.refresh()

    def next(self) -> bool:
        if self.at_end():
            return False
        self._step()
        self.last_manual = self.clock()
        return True

    def back(self) -> bool:
        if not self.progress:
            return False
        while self.progress and not self._applies(self.progress - 1):
            self.progress -= 1
        self.progress = max(self.progress - 1, 0)
        self.refresh()
        self.last_manual = self.clock()
        return True

    def reset(self) -> None:
        self.progress = 0
        self.refresh()

    def entered(self, area: str) -> bool:
        """Zone betreten: ist es das Ziel des Schritts, eine Seite weiter."""
        if self.clock() < self.last_manual + MANUAL_GRACE_S or area != self.target_area:
            return False
        self.target_area = ""
        return self.next()

    def skip_to(self, area: str) -> bool:
        """Schnellvorlauf bis zu dem Schritt, der in die Zone führt, in der man gerade steht."""
        if not self._ahead(area):
            return False
        for _ in range(FAST_FORWARD_LIMIT):
            self._step()
            if self.target_area == area or self._last_page():
                break
        self.last_manual = self.clock() - CANCEL_GRACE_S
        return True

    def _last_page(self) -> bool:
        text = " ".join(self.lines).lower()
        return any(marker in text for marker in END_MARKERS)

    def _ahead(self, area: str) -> bool:
        """Führt ein Schritt ab dem aktuellen in die Zone? (Ziel einer Seite = letzte Zone darauf)"""
        target = None
        for index in range(self.progress, len(self.pages)):
            if not self._applies(index):
                continue
            for line in self.pages[index].lines:
                tokens = area_tokens(line)
                if tokens and not self.options.skips(line):
                    target = tokens[-1]
            if target == area:
                return True
        return False
