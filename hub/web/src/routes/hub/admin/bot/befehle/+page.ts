import { apiLoad } from '#lib/api.ts';
import { BOT_API, type CustomCommand } from '#modules/bot/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	commands: await apiLoad<CustomCommand[]>(`${BOT_API}/commands`, fetch)
});
