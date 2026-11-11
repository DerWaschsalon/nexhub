// Modul BiS-Listen: was die Top-Spieler je Klasse tragen, als Anteile (Vorbild archon.gg). Gesammelt
// und gerechnet im Hub (hub/api/nexhub_api/bis_collector.py, bis_stats.py); angezeigt mit denselben
// Bausteinen wie ein Charakter der Armory (modules/logs/components). Seite unter routes/hub/bis/.
import type { HubModule } from '#lib/module.ts';
import { TEXTS } from './texts.ts';

export default {
	id: 'bis',
	nav: [{ href: '/hub/bis', label: 'bis.nav', icon: 'trophy', game: 'game.aion2' }],
	texts: TEXTS
} satisfies HubModule;
