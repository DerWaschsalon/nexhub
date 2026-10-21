import { api, ApiError } from '#lib/api.ts';
import { BOT_API, type BotGuild, type BotNavItem, type BotStatus } from '#modules/bot/api.ts';
import type { LayoutLoad } from './$types';

// Status, Kanäle/Rollen und das Menü (vom Bot) für alle Unterseiten. Ist der Bot nicht erreichbar,
// zeigt das Layout die Meldung statt einer Fehlerseite.
export const load: LayoutLoad = async ({ fetch }) => {
	try {
		const [status, guild, nav] = await Promise.all([
			api<BotStatus>(`${BOT_API}/status`, undefined, fetch),
			api<BotGuild>(`${BOT_API}/guild`, undefined, fetch),
			api<BotNavItem[]>(`${BOT_API}/pages`, undefined, fetch)
		]);
		return { status, guild, nav, offline: null };
	} catch (e) {
		if (!(e instanceof ApiError)) throw e;
		return { status: null, guild: null, nav: [] as BotNavItem[], offline: e.message };
	}
};
