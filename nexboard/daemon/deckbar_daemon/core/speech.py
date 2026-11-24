"""core.speech: Sprachausgabe und Töne. Gesprochen wird lokal mit Piper (Stimmen Thorsten/Amy), fertige
Sätze liegen im Cache; fehlt Piper, kommt der Alarmton. Töne werden einmal als WAV erzeugt."""
from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
import threading
import wave
from collections.abc import Callable, Iterable
from pathlib import Path

CACHE = Path.home() / ".cache" / "aion2-radar"
PIPER = Path.home() / ".local" / "share" / "aion2-radar" / "piper"  # Programm + Stimmen
VOICES = {"de": "de_DE-thorsten-medium", "en": "en_US-amy-medium"}
SAMPLE_RATE = 44100
MAX_WAITING = 2  # so viele Sätze dürfen warten

Player = Callable[[Path], subprocess.Popen | None]


def play(file: Path) -> subprocess.Popen | None:
    """Spielt die Datei ab, ohne zu warten. Der Prozess kommt zurück, damit man warten oder abbrechen kann."""
    player = shutil.which("pw-play") or shutil.which("paplay")
    if not player:
        return None
    return subprocess.Popen([player, str(file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _fade(t: float, length: float) -> float:
    """Kurzes Ein- und Ausblenden, sonst knackt es."""
    return min(1.0, t * 80, (length - t) * 80)


def _decay(t: float, length: float) -> float:
    return math.exp(-t * 14)


def tone_file(name: str, tones: tuple[int, ...], length: float, volume: float = 0.6,
              envelope: Callable[[float, float], float] = _fade) -> Path:
    """WAV-Datei mit diesen Tönen nacheinander (Hz, je `length` Sekunden), einmal erzeugt."""
    file = CACHE / name
    if not file.exists():
        file.parent.mkdir(parents=True, exist_ok=True)
        data = bytearray()
        for tone in tones:
            for i in range(int(SAMPLE_RATE * length)):
                t = i / SAMPLE_RATE
                sample = int(volume * 32767 * envelope(t, length) * math.sin(2 * math.pi * tone * t))
                data += sample.to_bytes(2, "little", signed=True)
        with wave.open(str(file), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(bytes(data))
    return file


def alarm_file() -> Path:
    return tone_file("alarm.wav", (988, 740, 988, 740), 0.11)


def spoken(text: str, language: str) -> Path | None:
    """WAV-Datei mit dem gesprochenen Text. Wird beim ersten Mal mit Piper erzeugt (ca. 0,4 s)."""
    file = CACHE / "ansagen" / language / (hashlib.md5(text.encode()).hexdigest() + ".wav")
    if not file.exists():
        program = PIPER / "piper" / "piper"
        if not program.exists():
            return None
        file.parent.mkdir(parents=True, exist_ok=True)
        fresh = file.with_suffix(f".{threading.get_ident()}.tmp")
        subprocess.run([program, "-m", PIPER / "stimmen" / f"{VOICES[language]}.onnx", "-f", fresh],
                       input=text.encode(), capture_output=True)
        if not fresh.exists():
            return None
        fresh.replace(file)
    return file


class Speaker:
    """Spricht nacheinander statt durcheinander, wie das A2Tools-Plugin Boss Callouts: höchstens zwei Sätze
    warten, ein wichtiger Satz bricht eine noch laufende Boss-Zeile oder einen Rückstau ab, eine weitere
    Boss-Zeile bei vollem Stau fällt weg."""

    def __init__(self, language: Callable[[], str], player: Player = play) -> None:
        self.language = language
        self.player = player  # startet das Abspielen und gibt den Prozess zurück (oder None)
        self.lock = threading.Lock()
        self.waiting: list[tuple[str, bool]] = []  # (Text, wichtig)
        self.running: tuple[subprocess.Popen | None, bool] | None = None  # (Prozess, wichtig)
        self.fresh = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def say(self, text: str, important: bool = True) -> None:
        with self.lock:
            jam = [important_ for _, important_ in self.waiting] + ([self.running[1]] if self.running else [])
            boss_line_in_jam = not all(jam)
            if important and (len(jam) >= MAX_WAITING or boss_line_in_jam):
                self._cancel()
            elif not important and len(jam) >= MAX_WAITING:
                return
            self.waiting.append((text, important))
        self.fresh.set()

    def _cancel(self) -> None:
        """Wartende Sätze verwerfen und den laufenden beenden. Aufruf unter self.lock."""
        self.waiting.clear()
        if self.running and self.running[0]:
            self.running[0].terminate()

    def _loop(self) -> None:
        while True:
            self.fresh.wait()
            with self.lock:
                if not self.waiting:
                    self.fresh.clear()
                    continue
                text, important = self.waiting.pop(0)
            process = self.player(spoken(text, self.language()) or alarm_file())
            with self.lock:
                self.running = (process, important)
            if process:
                process.wait()
            with self.lock:
                self.running = None


class Speech:
    """Sprechen und Töne für alle Module; der Sprecher startet erst mit dem ersten Satz."""

    def __init__(self, language: Callable[[], str]) -> None:
        self.language = language
        self._speaker: Speaker | None = None

    def say(self, text: str, important: bool = True) -> None:
        """Spricht den Text über die gemeinsame Warteschlange, ohne zu warten."""
        if self._speaker is None:
            self._speaker = Speaker(self.language)
        self._speaker.say(text, important)

    def prepare(self, texts: Iterable[str]) -> None:
        """Sätze vorab erzeugen, damit sie im Kampf sofort kommen."""
        language, wanted = self.language(), list(texts)
        threading.Thread(target=lambda: [spoken(t, language) for t in wanted], daemon=True).start()

    def alarm(self) -> None:
        play(alarm_file())

    def beep(self) -> None:
        """Kurz und hoch, z. B. je Welle."""
        play(tone_file("piep.wav", (1320,), 0.09))

    def ping(self) -> None:
        """Ton bei einem neuen Cube."""
        play(tone_file("ping.wav", (1250,), 0.22, volume=0.5, envelope=_decay))
