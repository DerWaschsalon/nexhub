import { apiLoad } from '#lib/api.ts';
import { BOT_API, type Verification } from '#modules/bot/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	verification: await apiLoad<Verification>(`${BOT_API}/verification`, fetch)
});
