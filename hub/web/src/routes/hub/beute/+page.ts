import { apiLoad } from '#lib/api.ts';
import type { Loot } from '#modules/loot/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	loot: await apiLoad<Loot>('/api/loot', fetch)
});
