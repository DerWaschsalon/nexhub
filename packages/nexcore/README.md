# nexcore

Kern für NexBoard, später auch Hub und Bot: alles, was jedes Modul braucht, aber keine Fachlogik.
Darf nur `nexproto`, `pydantic` und `pyyaml` importieren; `tests/test_imports.py` prüft das.

| Baustein | Datei | Ersetzt im Daemon |
|---|---|---|
| Modulvertrag `Module`, `ModuleInfo`, `Context` | `module.py` | Aufgabenlisten und Hooks in `modules.py`, Verdrahtung in `server.py` |
| `Registry`: an/aus, Abhängigkeiten, `modules.yaml` | `registry.py` | `ModuleManager` |
| `EventBus`: Themen statt Rückruf-Listen | `bus.py` | `listeners`-Listen, `bei_*`-Listen im Radar |
| `SettingsStore[T]`: laden mit Rückfall je Feld, Migration, Geheimnisse maskieren | `settings.py` | Lade-/Speicher-Kopien der Module, PUT-Handler |
| `GameWatch`: Spielerkennung mit Nachlauf | `gamewatch.py` | Schleifen mit eigenem `/proc`-Scan |
| `SseHub`: Server-Sent Events ohne Web-Framework | `sse.py` | Kopien in `a2ui.py` und `overlay.py` |
| `run`, `have`: externe Programme | `proc.py` | `proc.py` und Varianten |
| `Paths`, `atomic_write` | `paths.py` | XDG-Pfade und `_atomic_write` |
| `ApiError`: `{"error": "…"}` mit Status | `errors.py` | Fehlerantworten der Handler |

Sprachausgabe (Piper mit Piepton als Rückfall), Übersetzungen und die Paketquelle kommen mit dem
Radar-Umbau (Schritt 7) dazu: Vorher gibt es keinen zweiten Nutzer, und auf Vorrat wird nichts gebaut.

Ein Modul in Kürze:

```python
class Ping(Module):
    info = ModuleInfo("ping", "Ping", "system", "timer", "Zeigt den Ping im Spiel.", requires=("aion2.capture",))

    async def start(self) -> None:
        self.on("game.started", self.reset)  # Abo endet beim Ausschalten von selbst
        self.spawn(self.loop)                # Aufgabe ebenso; stürzt sie ab, startet sie neu
```

Tests, Lint und Typen: `uv run pytest -q && uv run ruff check . && uv run mypy`
