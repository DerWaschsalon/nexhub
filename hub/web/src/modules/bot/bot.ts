// Unterseiten des Bereichs „Bot“. Bereiche mit `section` sind reine Formulare aus dem Schema
// des Bots (Route [bereich]); die anderen haben eine eigene Seite.
export type BotNavItem = { slug: string; label: string };

export const BOT_NAV: BotNavItem[] = [
	{ slug: '', label: 'Übersicht' },
	{ slug: 'allgemein', label: 'Allgemein' },
	{ slug: 'verifizierung', label: 'Verifizierung' },
	{ slug: 'automod', label: 'Automod' },
	{ slug: 'verwarnungen', label: 'Verwarnungen' },
	{ slug: 'tickets', label: 'Tickets' },
	{ slug: 'community', label: 'Community' },
	{ slug: 'level', label: 'Levelsystem' },
	{ slug: 'ankuendigungen', label: 'Ankündigungen' },
	{ slug: 'befehle', label: 'Eigene Befehle' },
	{ slug: 'dps', label: 'DPS-Webhook' },
	{ slug: 'aion', label: 'AION 2' },
	{ slug: 'benachrichtigungen', label: 'Benachrichtigungen' },
	{ slug: 'sichtbarkeit', label: 'Sichtbarkeit' }
];

export const botHref = (slug: string) => (slug ? `/hub/admin/bot/${slug}` : '/hub/admin/bot');

/** "3 Tg. 4 Std." / "5 Std. 12 Min." / "8 Min." */
export function formatUptime(s: number): string {
	const d = Math.floor(s / 86400);
	const h = Math.floor((s % 86400) / 3600);
	const m = Math.floor((s % 3600) / 60);
	if (d) return `${d} Tg. ${h} Std.`;
	if (h) return `${h} Std. ${m} Min.`;
	return `${m} Min.`;
}
