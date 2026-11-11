import { apiLoad } from '#lib/api.ts';
import type { BisClass } from '#modules/bis/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	classes: await apiLoad<BisClass[]>('/api/bis', fetch)
});
