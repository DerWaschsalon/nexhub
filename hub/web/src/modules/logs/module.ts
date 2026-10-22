// Modul Logs: hochgeladene Runs ansehen wie bei Warcraft Logs/AbyssLogs – je Boss Rangliste,
// DPS-Verlauf, Fähigkeiten, Zeitleisten und Tode. Seiten unter routes/hub/runs/ (mit Login) und
// routes/(public)/r/ (geteilte Links); die Ansicht selbst in components/, gleich für beide.
// Daten aus der Hub-API (hub/api/nexhub_api/routes/runs.py, public.py, analysis.py).
import type { HubModule } from '#lib/module.ts';
import RecentRuns from './components/RecentRuns.svelte';
import { TEXTS } from './texts.ts';

export default {
	id: 'logs',
	nav: [
		{ href: '/hub/runs', label: 'logs.nav', icon: 'trophy', game: 'game.aion2', overview: RecentRuns }
	],
	texts: TEXTS
} satisfies HubModule;
