"""Die erzeugten Typen des Webs sind aktuell, und der Erzeuger kennt die Formen, die das Schema nutzt."""
from nexhub_api import web_types
from nexhub_api.web_types import ts


def test_abgelegte_typen_sind_aktuell():
    assert web_types.FILE.read_text() == web_types.text(), "neu erzeugen: uv run python -m nexhub_api.web_types"


def test_jedes_modell_hat_einen_eigenen_namen():
    """Zwei gleichnamige Modelle bekämen im Schema den Modulpfad als Namen, im Web unlesbar."""
    assert not [name for name in web_types.schema()["components"]["schemas"] if "__" in name]


def test_formen():
    assert ts({"anyOf": [{"type": "string"}, {"type": "null"}]}) == "string | null"
    assert ts({"type": "array", "items": {"anyOf": [{"type": "integer"}, {"type": "null"}]}}) == "(number | null)[]"
    assert ts({"type": "array", "items": {"$ref": "#/components/schemas/Day"}}) == "Day[]"
    assert ts({"type": "array", "prefixItems": [{"type": "number"}, {"type": "string"}]}) == "[number, string]"
    assert ts({"type": "object", "additionalProperties": {"type": "integer"}}) == "Record<string, number>"
    assert ts({"type": "object"}) == ts({"type": "object", "additionalProperties": True}) == "Record<string, unknown>"
    assert ts({"enum": ["offen", "erledigt"], "type": "string"}) == '"offen" | "erledigt"'
    assert ts({}) == "unknown"


def test_standardwerte_fehlen_nur_in_anfragen():
    node = {"type": "object", "required": ["name"],
            "properties": {"name": {"type": "string"}, "lang": {"type": "string", "default": "en"}}}
    assert ts(node) == "{\n\tname: string;\n\tlang: string;\n}"  # Antwort: immer da
    assert ts(node, sent=True) == "{\n\tname: string;\n\tlang?: string;\n}"  # Anfrage: darf fehlen
