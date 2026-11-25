"""Grenzen der Module: Ein Modul importiert den Kern und die Module, die es in `requires` nennt; der Kern
importiert kein Modul (außer dort, wo er sie anmeldet)."""
import ast
from pathlib import Path

from nexhub_api.modules import MODULES

PACKAGE = Path(__file__).resolve().parents[1] / "nexhub_api"
# Hier meldet der Kern die Module an bzw. baut aus allen zusammen das Schema
REGISTERS = {"main.py", "web_types.py", "migrations/env.py", "modules/__init__.py"}


def imported_modules(path: Path) -> set[str]:
    """Kennungen der Module (modules/<id>), die diese Datei importiert."""
    package = list(path.relative_to(PACKAGE.parent).parts[:-1])
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.ImportFrom):
            continue
        base = package[:len(package) - node.level + 1] if node.level else []
        target = [*base, *(node.module or "").split(".")]
        names = [alias.name for alias in node.names] if target[-1] in ("modules", "") else []
        target = [part for part in target if part]
        if target[:2] == ["nexhub_api", "modules"]:
            found |= {target[2]} if len(target) > 2 else set(names)
    return found


def test_module_importieren_nur_was_sie_nennen():
    for module in MODULES:
        allowed = {module.id, *module.requires}
        for path in (PACKAGE / "modules" / module.id).rglob("*.py"):
            rel = path.relative_to(PACKAGE)
            assert imported_modules(path) <= allowed, f"{rel} importiert ein Modul außer {allowed}"


def test_kern_importiert_keine_module():
    for path in PACKAGE.rglob("*.py"):
        rel = path.relative_to(PACKAGE).as_posix()
        if rel.startswith("modules/") or rel in REGISTERS:
            continue
        assert not imported_modules(path), f"{rel} (Kern) importiert ein Modul"


def test_requires_nennt_nur_vorhandene_module_ohne_kreis():
    by_id = {module.id: module for module in MODULES}
    for module in MODULES:
        assert set(module.requires) <= by_id.keys()
        assert module.id not in {r for needed in module.requires for r in by_id[needed].requires}, module.id
