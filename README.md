# NexHub

Alles rund um NexBoard und den Waschsalon-Discord an einem Ort.

| Ordner | Inhalt | Stand |
|---|---|---|
| [`nexboard/`](nexboard/) | NexBoard: Touch-Leiste (ESP32-S3), Python-Daemon, Overlay, AION-2-Mitschnitt | läuft |
| [`bot/`](bot/) | TheWashBot: Discord-Bot (Musik, Rollen, Moderation, AION-2-Runs, Dashboard) | läuft |
| [`hub/`](hub/) | NexHub-Website: Discord-Login, Gerätekopplung, Log-Uploads | geplant |
| [`proto/`](proto/) | `nexproto`: gemeinsame Schemas für Board, Hub und Bot | geplant |
| [`planner/`](planner/) | Daevanion-Planner | kommt noch |
| [`infra/`](infra/) | Konfiguration des VPS waschsalon, Deploy und Sperre | im Aufbau |

Jeder Ordner bringt seine eigene README mit Aufbau, Installation und Tests mit. Regeln für die
Zusammenarbeit (auch für Claude-Instanzen) stehen in [CLAUDE.md](CLAUDE.md).

Das Bot-Image baut GitHub Actions bei Änderungen unter `bot/` nach
`ghcr.io/derwaschsalon/thewashbot`.

## Lizenz

GPL-3.0, siehe [LICENSE](LICENSE). NexBoard bindet den A2Tools-Kern (GPL-3) ein.
