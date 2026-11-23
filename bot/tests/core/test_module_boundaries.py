"""Modulgrenzen (CLAUDE.md, Dependency Inversion): kein Modul importiert aus einem anderen Modul.

Ein Modul liegt unter bot/modules/<Bereich>/<Name>/. Gemeinsames gehört nach bot/core oder in nexcore,
nicht in ein Modul, das ein anderes dann importiert.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "bot"
MODULES = PACKAGE / "modules"


def module_of(name: str) -> str | None:
    """"bot.modules.music.player.sources" → "bot.modules.music.player"; außerhalb der Module None."""
    parts = name.split(".")
    if parts[:2] != ["bot", "modules"] or len(parts) < 4:
        return None
    return ".".join(parts[:4])


def package_of(path: Path) -> str:
    """Paket, in dem die Datei liegt, z. B. "bot.modules.music.player"."""
    return ".".join(("bot", *path.parent.relative_to(PACKAGE).parts))


def imported_names(code: str, package: str) -> list[str]:
    """Alle importierten Namen im Code, relative Importe vom Paket aus aufgelöst."""
    names = []
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1] + ([base] if base else []))
            names += [f"{base}.{alias.name}" for alias in node.names]
    return names


def test_kein_modul_importiert_ein_anderes() -> None:
    violations = []
    for path in sorted(MODULES.rglob("*.py")):
        own = module_of(package_of(path) + ".x")
        if own is None:
            continue  # bot/modules/__init__.py und die Bereiche: die Liste aller Module darf sie kennen
        for name in imported_names(path.read_text(encoding="utf-8"), package_of(path)):
            other = module_of(name)
            if other and other != own:
                violations.append(f"{path.relative_to(PACKAGE.parent)}: {name}")
    assert not violations, "Modul importiert aus anderem Modul:\n" + "\n".join(sorted(set(violations)))


def test_pruefung_erkennt_verstoesse() -> None:
    """Die Auflösung relativer Importe stimmt, sonst prüfte der Test oben nichts."""
    code = "from . import sources\nfrom ..autoplay import x\nfrom ...aion2.runs import posts\nimport bot.core\n"
    names = imported_names(code, "bot.modules.music.player")
    assert names == ["bot.modules.music.player.sources", "bot.modules.music.autoplay.x",
                     "bot.modules.aion2.runs.posts", "bot.core"]
    assert [module_of(n) for n in names] == ["bot.modules.music.player", "bot.modules.music.autoplay",
                                             "bot.modules.aion2.runs", None]
