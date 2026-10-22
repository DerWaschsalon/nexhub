// Modul Geräte: NexBoards per Code mit dem eigenen Konto koppeln (RFC 8628) und entfernen.
// Seite unter routes/hub/geraete/ – der Daemon verlinkt dorthin mit ?code=…
import type { HubModule } from '#lib/module.ts';
import MyDevices from './components/MyDevices.svelte';
import { TEXTS } from './texts.ts';

export default {
	id: 'devices',
	nav: [{ href: '/hub/geraete', label: 'devices.nav', icon: 'device', overview: MyDevices }],
	texts: TEXTS
} satisfies HubModule;
