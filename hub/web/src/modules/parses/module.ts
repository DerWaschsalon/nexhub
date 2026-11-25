// Modul Parses: wie gut der DPS eines Spielers an einem Boss war, gegen Abyss Logs (EU) und gegen die Gilde.
// Gerechnet im Hub (hub/api/nexhub_api/modules/parses/). Keine eigene Seite: die Kampfseiten unter
// routes/ laden die Parses und zeigen ParseBadge in der Rangliste (FightView, Snippet `badge`).
import type { HubModule } from '#lib/module.ts';
import { TEXTS } from './texts.ts';

export default {
	id: 'parses',
	nav: [],
	texts: TEXTS
} satisfies HubModule;
