"""Musik: Zeitformat, FFmpeg-Optionen, Senderanzeige, Rückmeldung nach /play."""

from __future__ import annotations

from unittest.mock import MagicMock

from bot.modules.music.player.commands import added_text, station_label
from bot.modules.music.player.player import FFMPEG_BEFORE, ffmpeg_before, fmt_time
from bot.modules.music.player.sources import Track


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
