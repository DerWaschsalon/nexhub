import { api, ApiError, BOT_API, type BotGuild, type BotStatus } from '#lib/api.ts';
import type { LayoutLoad } from './$types';

// Status und Kanäle/Rollen für alle Unterseiten. Ist der Bot nicht erreichbar, zeigt das Layout
// die Meldung statt einer Fehlerseite, damit die Navigation bleibt.
export const load: LayoutLoad = async ({ fetch }) => {
	try {
		const [status, guild] = await Promise.all([
			api<BotStatus>(`${BOT_API}/status`, undefined, fetch),
			api<BotGuild>(`${BOT_API}/guild`, undefined, fetch)
		]);
		return { status, guild, offline: null };
	} catch (e) {
		if (!(e instanceof ApiError)) throw e;
		return { status: null, guild: null, offline: e.message };
	}
};
