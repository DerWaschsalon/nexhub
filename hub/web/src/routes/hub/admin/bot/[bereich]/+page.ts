import { apiLoad } from '#lib/api.ts';
import { BOT_API, type BotPage } from '#modules/bot/api.ts';
import type { PageLoad } from './$types';

// Seiten aus Blöcken (Formulare, Tabellen, Status, Aktionen): Aufbau und Daten kommen vom Bot
export const load: PageLoad = async ({ fetch, params }) => ({
	page: await apiLoad<BotPage>(`${BOT_API}/pages/${params.bereich}`, fetch)
});
