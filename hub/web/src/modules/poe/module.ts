// Modul Path of Exile: Preise von poe.ninja suchen und eine eigene Merkliste mit Alarmschwelle führen
// (hub/api/nexhub_api/routes/poe.py). Seite unter routes/hub/poe/, das Spiel steht in `?game=`.
import type { HubModule } from '#lib/module.ts';
import WatchOverview from './components/WatchOverview.svelte';
import { TEXTS } from './texts.ts';

export default {
	id: 'poe',
	nav: [{ href: '/hub/poe', label: 'poe.nav', icon: 'chart', game: 'game.poe', overview: WatchOverview }],
	texts: TEXTS
} satisfies HubModule;
