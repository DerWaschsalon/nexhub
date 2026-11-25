// Modul Termine: die festen Termine der AION-2-Server (proto/nexproto/termine.py) mit Countdown und
// Wochenplan. Gerechnet wird im Hub (modules/schedule/routes.py); die Seite gibt es mit Login unter
// routes/hub/termine/ und ohne unter routes/(public)/termine/, beide zeigen ScheduleView.
import type { HubModule } from '#lib/module.ts';
import { TEXTS } from './texts.ts';

export default {
	id: 'schedule',
	nav: [{ href: '/hub/termine', label: 'schedule.nav', icon: 'clock', game: 'game.aion2' }],
	texts: TEXTS
} satisfies HubModule;
