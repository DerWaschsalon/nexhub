"""updates.py: Versionsvergleich, Commits hinter dem Upstream, A2Tools-Release."""
import subprocess

from deckbar_daemon.updates import Updates, version_tuple


def test_version_tuple():
    assert version_tuple("v2.0.62") == (2, 0, 62)
    assert version_tuple("v2.0.62") < version_tuple("v2.0.100") < version_tuple("v2.1.0")
    assert version_tuple("2.0.62-1-gabc") == (2, 0, 62)
    assert version_tuple(None) == () and version_tuple("main") == ()


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


async def test_commits_hinter_upstream(tmp_path):
    origin, work, other = tmp_path / "origin.git", tmp_path / "work", tmp_path / "other"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    for d in (work, other):
        subprocess.run(["git", "clone", "-q", str(origin), str(d)], check=True, capture_output=True)
        git(d, "config", "user.email", "t@example.invalid")
        git(d, "config", "user.name", "t")
    git(work, "commit", "-q", "--allow-empty", "-m", "eins")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(other, "pull", "-q", "origin", "main")
    git(other, "branch", "-u", "origin/main")
    git(work, "commit", "-q", "--allow-empty", "-m", "zwei")
    git(work, "commit", "-q", "--allow-empty", "-m", "drei")
    git(work, "push", "-q", "origin", "HEAD:main")

    up = Updates(other)

    async def kein_a2tools():
        return {"current": "v2.0.62", "latest": "v2.0.62", "newer": False}

    up._check_a2tools = kein_a2tools
    seen = []

    async def changed():
        seen.append(up.info())

    up.listeners.append(changed)
    await up.check()
    d = up.info()["deckbar"]
    assert d["behind"] == 2 and d["ahead"] == 0 and d["latest"] == "drei"
    assert up.info()["available"] and seen and up.info()["error"] == ""


async def test_neues_a2tools_release(tmp_path):
    up = Updates(tmp_path)

    async def repo():
        return {"behind": 0, "ahead": 0}

    async def a2():
        return {"current": "v2.0.62", "latest": "v2.0.63", "newer": True}

    up._check_repo, up._check_a2tools = repo, a2
    await up.check()
    assert up.info()["available"] and up.info()["a2tools"]["latest"] == "v2.0.63"


async def test_fehler_werden_gemeldet(tmp_path):
    up = Updates(tmp_path)  # kein Git-Repo, kein Submodul

    async def a2():
        raise RuntimeError("offline")

    up._check_a2tools = a2
    await up.check()
    info = up.info()
    assert not info["available"] and "DeckBar" in info["error"] and "offline" in info["error"]
