"""Benachrichtigungen: Migration der Feeds-Tabelle, GitHub- und YouTube-Provider."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest

from bot.db import Database


def test_feeds_migration_on_existing_db() -> None:
    """Simuliert eine schon laufende Installation: feeds-Tabelle existiert noch ohne die neuen
    Spalten (events/filters/enabled/state/error) — Database.connect() muss sie nachrüsten,
    ohne bestehende Zeilen zu verlieren."""
    import aiosqlite

    async def go() -> Any:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.sqlite3"
            conn = await aiosqlite.connect(path)
            await conn.execute(
                "CREATE TABLE feeds (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, "
                "channel_id INTEGER NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL, "
                "message TEXT NOT NULL DEFAULT '', last_id TEXT)"
            )
            await conn.execute(
                "INSERT INTO feeds (guild_id, channel_id, kind, source) VALUES (1, 2, 'github', 'o/r')"
            )
            await conn.commit()
            await conn.close()

            db = Database(path)
            await db.connect()
            row = await db.fetchone("SELECT * FROM feeds WHERE source='o/r'")
            await db.close()
            return row

    row = asyncio.run(go())
    assert row["guild_id"] == 1 and row["source"] == "o/r"
    assert row["events"] == "[]" and row["filters"] == "{}" and row["enabled"] == 1 and row["state"] == "{}"


def test_github_provider_dedup_and_transitions() -> None:
    from bot.modules.notify.feeds.providers.github import GitHubProvider

    provider = GitHubProvider()
    responses: dict[str, tuple[int, object]] = {}

    async def fake_get(path: str, **params: Any) -> Any:
        return responses[path.split("/")[-1]]

    setattr(provider, "_get", fake_get)  # keine echten HTTP-Aufrufe in Tests

    async def go() -> Any:
        events = ["release", "issue_open", "issue_closed", "pr_open", "pr_closed", "pr_merged"]
        responses["releases"] = (200, [{"id": 1, "name": "v1", "prerelease": False, "draft": False}])
        responses["issues"] = (200, [{"number": 10, "state": "open", "title": "Bug", "labels": [],
                                      "user": {"login": "x"}}])
        responses["pulls"] = (200, [{"number": 20, "state": "open", "merged_at": None, "title": "PR",
                                     "labels": [], "user": {"login": "x"}}])

        # Erster Abruf (baseline): nichts melden, nur Zustand füllen
        notes, state = await provider.poll("o/r", events, {}, {}, baseline=True)
        assert notes == []
        assert state["releases"] == [1] and state["issues"]["10"] == "open"

        # Gleicher Stand, kein baseline mehr: immer noch nichts Neues
        notes, state2 = await provider.poll("o/r", events, {}, state, baseline=False)
        assert notes == []

        # Neuer Release + Issue geschlossen + PR gemerged
        responses["releases"] = (200, [
            {"id": 2, "name": "v2", "prerelease": False, "draft": False},
            {"id": 1, "name": "v1", "prerelease": False, "draft": False},
        ])
        responses["issues"] = (200, [{"number": 10, "state": "closed", "title": "Bug", "labels": [],
                                      "user": {"login": "x"}}])
        responses["pulls"] = (200, [{"number": 20, "state": "closed", "merged_at": "2026-01-01T00:00:00Z",
                                     "title": "PR", "labels": [], "user": {"login": "x"}}])
        notes, state3 = await provider.poll("o/r", events, {}, state2, baseline=False)
        kinds = sorted(n.event for n in notes)
        assert kinds == ["issue_closed", "pr_merged", "release"]
        assert state3["releases"] == [1, 2]
        assert state3["issues"]["10"] == "closed"
        assert state3["prs"]["20"] == "merged"

    asyncio.run(go())


def test_github_embeds_include_link_field() -> None:
    from bot.modules.notify.feeds.providers.github import GitHubProvider

    provider = GitHubProvider()
    release = {"id": 1, "name": "v1", "html_url": "https://github.com/o/r/releases/v1"}
    issue = {"number": 5, "title": "Bug", "labels": [], "html_url": "https://github.com/o/r/issues/5"}
    pr = {"number": 7, "title": "Fix", "labels": [], "html_url": "https://github.com/o/r/pull/7"}
    commit = {"sha": "abcdef1", "commit": {"message": "Fix"}, "html_url": "https://github.com/o/r/commit/abcdef1"}

    for embed, url in [
        (provider._release_embed("o/r", release), release["html_url"]),
        (provider._issue_embed("o/r", issue, False), issue["html_url"]),
        (provider._pr_embed("o/r", pr, "pr_open"), pr["html_url"]),
        (provider._commit_embed("o/r", commit), commit["html_url"]),
    ]:
        assert embed.url == url  # Titel bleibt verlinkt
        link_fields = [f for f in embed.fields if f.name == "Link"]
        assert len(link_fields) == 1 and str(url) in str(link_fields[0].value)


def test_github_provider_filters_and_baseline_skip() -> None:
    from bot.modules.notify.feeds.providers.github import GitHubProvider

    provider = GitHubProvider()
    data = [{"id": 1, "name": "v1", "prerelease": True, "draft": False}]

    async def fake_get(path: str, **params: Any) -> Any:
        return 200, data

    setattr(provider, "_get", fake_get)

    async def go() -> Any:
        # Baseline registriert die ID, meldet aber nichts
        _, state = await provider.poll("o/r", ["release"], {"prereleases": False}, {}, baseline=True)
        data.append({"id": 2, "name": "v2", "prerelease": True, "draft": False})
        notes, _ = await provider.poll("o/r", ["release"], {"prereleases": False}, state, baseline=False)
        assert notes == []  # Pre-Release durch Filter ausgeschlossen

    asyncio.run(go())


YOUTUBE_FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <yt:videoId>VIDEO1</yt:videoId>
  <title>Erstes Video</title>
  <author><name>Mein Kanal</name></author>
  <media:group><media:thumbnail url="https://i.ytimg.com/vi/VIDEO1/hqdefault.jpg"/></media:group>
 </entry>
 <entry>
  <yt:videoId>VIDEO2</yt:videoId>
  <title>Zweites, neueres Video</title>
  <author><name>Mein Kanal</name></author>
  <media:group><media:thumbnail url="https://i.ytimg.com/vi/VIDEO2/hqdefault.jpg"/></media:group>
 </entry>
</feed>"""


def test_youtube_feed_parsing() -> None:
    from bot.modules.notify.feeds.providers.youtube import parse_feed

    videos = parse_feed(YOUTUBE_FEED_XML)
    assert [v["id"] for v in videos] == ["VIDEO1", "VIDEO2"]
    assert videos[0]["title"] == "Erstes Video"
    assert videos[0]["author"] == "Mein Kanal"
    assert videos[0]["thumbnail"] == "https://i.ytimg.com/vi/VIDEO1/hqdefault.jpg"


def test_youtube_provider_dedup_and_baseline() -> None:
    from bot.modules.notify.feeds.providers.youtube import YouTubeProvider

    provider = YouTubeProvider()
    feed_xml = [YOUTUBE_FEED_XML]

    async def fake_fetch(channel_id: str) -> Any:
        from bot.modules.notify.feeds.providers.youtube import parse_feed
        return parse_feed(feed_xml[0])

    setattr(provider, "_fetch", fake_fetch)  # keine echten HTTP-Aufrufe in Tests

    async def go() -> Any:
        # Baseline: registriert beide Videos, meldet aber nichts
        notes, state = await provider.poll("UCabc", ["video"], {}, {}, baseline=True)
        assert notes == []
        assert set(state["seen"]) == {"VIDEO1", "VIDEO2"}

        # Gleicher Feed, kein baseline mehr -> nichts Neues
        notes2, state2 = await provider.poll("UCabc", ["video"], {}, state, baseline=False)
        assert notes2 == []

        # Ein drittes, neues Video im Feed -> genau eine Meldung
        feed_xml[0] = YOUTUBE_FEED_XML.replace(
            "</feed>", '<entry><yt:videoId>VIDEO3</yt:videoId><title>Drittes</title>'
                       '<author><name>Mein Kanal</name></author></entry></feed>'
        )
        notes3, state3 = await provider.poll("UCabc", ["video"], {}, state2, baseline=False)
        assert len(notes3) == 1 and notes3[0].event == "video"
        assert "VIDEO3" in state3["seen"]

    asyncio.run(go())


def test_youtube_validate_source_rejects_non_channel_ids() -> None:
    from bot.modules.notify.feeds.providers.base import ProviderError
    from bot.modules.notify.feeds.providers.youtube import YouTubeProvider

    provider = YouTubeProvider()

    async def go() -> Any:
        with pytest.raises(ProviderError):
            await provider.validate_source("@nicht-die-kanal-id")

    asyncio.run(go())


