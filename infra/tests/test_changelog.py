"""Changelog aus der Merge-Historie (infra/changelog.py): Merge- und Squash-Commits, Bereiche aus Pfaden."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from changelog import FIELD, HEAD_END, RECORD, Entry, area_of, parse  # noqa: E402


def commit(date: str, subject: str, body: str, files: list[str]) -> str:
    return f"{RECORD}{date}{FIELD}{subject}{FIELD}{body}{HEAD_END}\n\n" + "\n".join(files) + "\n"


LOG = (
    commit("2026-11-24", "Merge pull request #127 from DerWaschsalon/welle3-termine-seite",
           "Hub: Seite „Termine“ mit Countdown\n\nzweite Zeile", ["hub/web/src/a.svelte", "proto/nexproto/termine.py"])
    + commit("2026-11-24", "CI für den Hub: API-Tests und Build (claude-navoserver) (#118)", "",
             [".github/workflows/hub.yml"])
    + commit("2026-11-23", "capture: A2Tools 2.1.4, Treffer-Patch entfällt", "", ["nexboard/capture/build.sh"])
    + commit("2026-11-19", "Merge pull request #112 from DerWaschsalon/guide-icons",
             "Guide-Kachel: echte Symbole statt Textmarken (FW 0.9.0)",
             ["nexboard/firmware/src/main.cpp", "nexboard/daemon/x.py"])
)


def test_merge_und_squash_ohne_direkte_commits():
    entries = parse(LOG)
    assert [e.pr for e in entries] == [127, 118, 112]  # der Commit ohne PR fehlt
    assert entries[0] == Entry("2026-11-24", 127, "Hub: Seite „Termine“ mit Countdown", ["core", "hub"])
    assert entries[1].title == "CI für den Hub: API-Tests und Build (claude-navoserver)" and entries[1].areas == []
    assert entries[2].areas == ["firmware", "nexboard"]


def test_bereich_aus_dem_pfad():
    assert area_of("nexboard/firmware/src/ui.c") == "firmware"
    assert area_of("nexboard/daemon/app.py") == "nexboard"
    assert area_of("packages/nexcore/bus.py") == "core"
    assert area_of("README.md") is None


def test_leere_historie():
    assert parse("") == []
