"""Modulgrenzen (CLAUDE.md, Dependency Inversion): kein Modul unter modules/ importiert ein anderes.

Gemeinsam nutzen dürfen sie nur modules/base.py; alles andere kommt aus dem Daemon-Kern (Komponenten
eine Ebene höher) oder aus nexcore.
"""
import ast
from pathlib import Path

MODULES = Path(__file__).resolve().parents[1] / "deckbar_daemon" / "modules"
SHARED = {"base", "__init__"}


def imported_modules(code: str) -> set[str]:
    """Namen der Geschwister-Module, die der Code importiert (`from .x`, `from . import x`, absolut)."""
    found = set()
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            found |= {node.module.split(".")[0]} if node.module else {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("deckbar_daemon.modules."):
            found.add(node.module.split(".")[2])
        elif isinstance(node, ast.Import):
            found |= {a.name.split(".")[2] for a in node.names if a.name.startswith("deckbar_daemon.modules.")}
    return found


def test_kein_modul_importiert_ein_anderes():
    violations = []
    for path in sorted(MODULES.glob("*.py")):
        if path.stem in SHARED:
            continue
        for other in sorted(imported_modules(path.read_text(encoding="utf-8")) - SHARED - {path.stem}):
            violations.append(f"modules/{path.name}: {other}")
    assert not violations, "Modul importiert aus anderem Modul:\n" + "\n".join(violations)


def test_pruefung_erkennt_verstoesse():
    code = ("from .base import WebModule\nfrom .dps import x\nfrom . import radar\nfrom ..updates import Updates\n"
            "from deckbar_daemon.modules.hub import y\n")
    assert imported_modules(code) == {"base", "dps", "radar", "hub"}
