"""Die erzeugten Dateien (Schemas, C-, JS- und TS-Konstanten) passen zum Code von nexproto."""
import pytest

from nexproto.codegen import REPO, TARGETS


@pytest.mark.parametrize("path", TARGETS)
def test_erzeugte_datei_ist_aktuell(path):
    assert (REPO / path).read_text(encoding="utf-8") == TARGETS[path](), \
        f"{path} veraltet: cd proto && uv run python -m nexproto.codegen"
