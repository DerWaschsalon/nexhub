"""Abhängigkeitsrichtung: der Kern kennt keine Programme und keine Fachmodule."""
import ast
from pathlib import Path

ALLOWED = {"nexcore", "nexproto", "pydantic", "yaml"}
STDLIB = {"abc", "asyncio", "collections", "dataclasses", "inspect", "json", "logging", "os", "pathlib",
          "shutil", "tempfile", "time", "typing", "__future__"}


def imported(node: ast.AST) -> list[str]:
    """Absolute Importe eines Knotens; relative (from .bus) bleiben im Paket."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and not node.level:
        return [node.module or ""]
    return []


def test_kern_importiert_nur_erlaubtes():
    for path in (Path(__file__).parents[1] / "nexcore").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            for name in imported(node):
                assert name.split(".")[0] in ALLOWED | STDLIB, f"{path.name} importiert {name}"
