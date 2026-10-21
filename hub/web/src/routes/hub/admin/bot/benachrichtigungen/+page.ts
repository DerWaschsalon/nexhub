import { apiLoad } from '#lib/api.ts';
import { BOT_API, type Feed } from '#modules/bot/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	feeds: await apiLoad<Feed[]>(`${BOT_API}/notifications`, fetch)
});
