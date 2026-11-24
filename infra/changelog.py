#!/usr/bin/env python3
"""Changelog aus den gemergten PRs von main, als JSON.

    infra/changelog.py [BEREICH]     BEREICH wie bei git log, z. B. alt..neu; ohne: die letzten MAX_ENTRIES

Die Merge-Historie ist die einzige Quelle, eine zweite Datei pflegt niemand von Hand: Der Titel eines PRs
ist seine Zeile im Changelog (deshalb deutsch und für Laien lesbar). Genutzt beim Bauen des Hubs:
nexhub-update schreibt hub/web/static/changelog.json für die Seite „Neu“. Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass

MAX_ENTRIES = 200
# Trenner in der Ausgabe von git log: Eintrag, Feld, Ende des Kopfs (danach folgen die geänderten Dateien)
RECORD, FIELD, HEAD_END = "\x1e", "\x1f", "\x1d"
LOG_FORMAT = f"{RECORD}%ad{FIELD}%s{FIELD}%b{HEAD_END}"
MERGE_TITLE = re.compile(r"^Merge pull request #(\d+) from ")
SQUASH_TITLE = re.compile(r"^(.*) \(#(\d+)\)$")
# Pfad → Bereich; der erste passende Anfang gilt, deshalb die Firmware vor dem Rest der NexBoard
AREAS = (("nexboard/firmware/", "firmware"), ("nexboard/", "nexboard"), ("hub/", "hub"), ("bot/", "bot"),
         ("proto/", "core"), ("packages/", "core"), ("infra/", "infra"))


@dataclass(frozen=True)
class Entry:
    date: str  # Tag des Merges, JJJJ-MM-TT
    pr: int
    title: str
    areas: list[str]


def area_of(path: str) -> str | None:
    return next((area for prefix, area in AREAS if path.startswith(prefix)), None)


def title_of(subject: str, body: str) -> tuple[int, str] | None:
    """PR-Nummer und Titel: beim Merge-Commit steht der Titel in der ersten Zeile des Texts, beim
    Squash-Merge im Betreff vor „(#N)“. Commits ohne PR gehören nicht in den Changelog."""
    merge = MERGE_TITLE.match(subject)
    if merge:
        first_line = body.strip().splitlines()[0] if body.strip() else subject
        return int(merge.group(1)), first_line
    squash = SQUASH_TITLE.match(subject)
    return (int(squash.group(2)), squash.group(1)) if squash else None


def parse(log: str) -> list[Entry]:
    """Die Ausgabe von `git log` (LOG_FORMAT mit --name-only) als Einträge, neueste zuerst."""
    entries = []
    for record in log.split(RECORD)[1:]:
        head, _, files = record.partition(HEAD_END)
        date, subject, body = head.split(FIELD, 2)
        found = title_of(subject, body)
        if not found:
            continue
        areas = sorted({area for path in files.split() if (area := area_of(path))})
        entries.append(Entry(date, found[0], found[1], areas))
    return entries


def git_log(revisions: str | None) -> str:
    """Erste Elternlinie von main; -m zeigt bei Merges, was gegenüber main dazukam."""
    command = ["git", "log", "--first-parent", "-m", "--name-only", "--date=short", f"--format={LOG_FORMAT}"]
    command += [revisions] if revisions else [f"-{MAX_ENTRIES}"]
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def main() -> None:
    entries = parse(git_log(sys.argv[1] if len(sys.argv) > 1 else None))
    json.dump([asdict(entry) for entry in entries], sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
