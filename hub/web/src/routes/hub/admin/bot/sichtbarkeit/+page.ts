import { apiLoad } from '#lib/api.ts';
import { BOT_API, type VisibilityMatrix } from '#modules/bot/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	matrix: await apiLoad<VisibilityMatrix>(`${BOT_API}/matrix`, fetch)
});
