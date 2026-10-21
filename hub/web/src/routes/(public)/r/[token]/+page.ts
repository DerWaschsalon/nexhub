import { apiLoad, type RunCore } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	run: await apiLoad<RunCore>(`/api/public/runs/${encodeURIComponent(params.token)}`, fetch)
});
