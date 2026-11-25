// Modul Beute: Dropraten je Boss aus der Würfel-Beute der hochgeladenen Runs. Gezählt und gerechnet im
// Hub (hub/api/nexhub_api/modules/loot/table.py, modules/loot/routes.py); Seite unter routes/hub/beute/.
import type { HubModule } from '#lib/module.ts';
import { TEXTS } from './texts.ts';

export default {
	id: 'loot',
	nav: [{ href: '/hub/beute', label: 'loot.nav', icon: 'box', game: 'game.aion2' }],
	texts: TEXTS
} satisfies HubModule;
