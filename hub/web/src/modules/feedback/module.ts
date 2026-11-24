// Modul Feedback: Mitglieder schreiben Wünsche und stimmen ab, Admins setzen den Status
// (hub/api/nexhub_api/routes/feedback.py). Seite unter routes/hub/feedback/.
import type { HubModule } from '#lib/module.ts';
import { TEXTS } from './texts.ts';

export default {
	id: 'feedback',
	nav: [{ href: '/hub/feedback', label: 'feedback.nav', icon: 'chat' }],
	texts: TEXTS
} satisfies HubModule;
