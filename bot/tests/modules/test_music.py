"""Musik: Zeitformat, FFmpeg-Optionen, Senderanzeige, Rückmeldung nach /play."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from bot.modules.music.player.commands import added_text, station_label
from bot.modules.music.player.player import FFMPEG_BEFORE, ffmpeg_before, fmt_time
from bot.modules.music.player.sources import SPOTIFY_RE, Track, _find_key, is_url


def track(title: str = "Lied", live: bool = False) -> Track:
    return Track(title=title, query="ytsearch1:x", requester_id=1, live=live)


def test_time_and_ffmpeg_options() -> None:
    assert (fmt_time(None), fmt_time(75), fmt_time(3725)) == ("?", "1:15", "1:02:05")
    assert ffmpeg_before(track()) == FFMPEG_BEFORE
    with_headers = Track(title="x", query="x", requester_id=1, headers={"Referer": "a"})
    assert "-headers" in ffmpeg_before(with_headers)


def test_station_label() -> None:
    assert station_label({"name": " Radio Eins ", "countrycode": "DE", "bitrate": "128"}) == \
        "Radio Eins (DE · 128 kbit/s)"
    assert station_label({"name": "Nur Name"}) == "Nur Name"


def test_added_text() -> None:
    player = MagicMock(queue=[track()], current=None)
    assert "läuft gleich" in added_text(player, [track()], None, was_idle=True, front=False)
    assert added_text(player, [track(), track()], "Mix", was_idle=False, front=False) == "➕ **2 Titel** aus **Mix**"
    player.current = track(live=True)
    assert "Livestream" in added_text(player, [track()], None, was_idle=False, front=False)
    assert added_text(player, [track("Vorne")], None, was_idle=False, front=True) == "⏫ Vorne kommt als Nächstes."


def make_player(tracks: list[Track], loop: str = "aus") -> Any:
    from bot.modules.music.player.player import Player
    p = Player.__new__(Player)
    p.queue, p.current, p.loop, p._skipped = list(tracks), None, loop, False
    return p


def t(name: str) -> Track:
    return Track(title=name, query=name, requester_id=1)


def test_queue_order_and_loops() -> None:
    a, b, c = t("a"), t("b"), t("c")
    p = make_player([a, b, c])
    seq = []
    for _ in range(3):
        p.current = p._next()
        seq.append(p.current.title)
    assert seq == ["a", "b", "c"] and p._next() is None

    p = make_player([a, b], loop="song")
    p.current = p._next()
    assert p._next() is a            # Song wiederholen
    p._skipped = True
    assert p._next() is b            # Überspringen beendet die Wiederholung des Songs

    p = make_player([a, b], loop="liste")
    seq = []
    for _ in range(5):
        p.current = p._next()
        seq.append(p.current.title)
    assert seq == ["a", "b", "a", "b", "a"]


def test_source_detection() -> None:
    assert is_url("https://youtu.be/x") and not is_url("never gonna give you up")
    m = SPOTIFY_RE.search("https://open.spotify.com/intl-de/playlist/37i9dQZF1DXcBWIGoYBM5M?si=1")
    assert m is not None
    assert m.group(1) == "playlist" and m.group(2) == "37i9dQZF1DXcBWIGoYBM5M"
    assert _find_key({"a": [{"b": {"trackList": [1]}}]}, "trackList") == [1]


