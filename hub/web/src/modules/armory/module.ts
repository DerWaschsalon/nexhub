// Modul Armory: eigene Charaktere eintragen, alle Angemeldeten sehen alle. Täglich und auf Knopfdruck
// neu von der AION-2-Website (hub/api/nexhub_api/armory.py). Seiten unter routes/hub/armory/; das
// Profil selbst ist dieselbe Ansicht wie bei den Mitspielern eines Runs (modules/logs/components).
import type { HubModule } from '#lib/module.ts';
import { TEXTS } from './texts.ts';

export default {
	id: 'armory',
	nav: [{ href: '/hub/armory', label: 'armory.nav', icon: 'shield' }],
	texts: TEXTS
} satisfies HubModule;
