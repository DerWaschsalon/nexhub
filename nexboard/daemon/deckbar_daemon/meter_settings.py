"""Einstellungen der Meter-Oberfläche: flache Schlüssel mit Textwerten in a2-settings.json, wie im Meter."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .a2tools_meter import a2tools_settings_path
from .capture import DEFAULT_INTERVAL_MS
from .config import _atomic_write

log = logging.getLogger(__name__)

UPDATE_RATE = "dpsMeter.updateRateMs"  # Einstellung „Aktualisierung“ des Meters
UPDATE_RATES_MS = (100, 200, 250, 500)  # Auswahl im Meter
# Nicht aus den Einstellungen des A2Tools-Meters übernehmen: Geheimnisse, Fensterlagen, Online-Kram
NO_IMPORT = re.compile(r"(?i)key|token|secret|account|^window\.|streamOverlay|autoUpload|discord|kwinRule|plugin")


class MeterSettings:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.values = self._load()

    def set(self, key: str, value: str) -> None:
        self.values[key] = value
        self._save()

    def clear(self) -> None:
        self.values = {}
        self._save()

    @property
    def update_rate_ms(self) -> int:
        """Takt der DPS-Ansicht; alles außerhalb der Auswahl des Meters fällt auf den Standard zurück."""
        rate = self.values.get(UPDATE_RATE, "")
        return int(rate) if rate.isdigit() and int(rate) in UPDATE_RATES_MS else DEFAULT_INTERVAL_MS

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("%s unlesbar: %s", self.path, e)
        self.values = self._imported()
        self._save()
        return self.values

    def _imported(self) -> dict[str, str]:
        """Erster Start: Einstellungen des A2Tools-Meters übernehmen (Theme, Spielerlimit, Sprache …)."""
        try:
            a2 = json.loads(a2tools_settings_path().read_text())
        except (OSError, ValueError):
            return {}
        data = {k: str(v) for k, v in a2.items() if not NO_IMPORT.search(k)} if isinstance(a2, dict) else {}
        if data:
            log.info("%d Einstellungen aus dem A2Tools-Meter übernommen", len(data))
        return data

    def _save(self) -> None:
        _atomic_write(self.path, json.dumps(self.values, ensure_ascii=False, indent=1) + "\n", 0o600)
