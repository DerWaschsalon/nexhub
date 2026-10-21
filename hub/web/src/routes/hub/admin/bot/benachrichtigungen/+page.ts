import { apiLoad, BOT_API, type Feed } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	feeds: await apiLoad<Feed[]>(`${BOT_API}/notifications`, fetch)
});
