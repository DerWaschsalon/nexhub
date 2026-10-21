import { apiLoad, BOT_API, type VisibilityMatrix } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	matrix: await apiLoad<VisibilityMatrix>(`${BOT_API}/matrix`, fetch)
});
