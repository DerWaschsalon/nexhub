import { apiLoad } from '#lib/api.ts';
import type { Run } from '#modules/logs/api.ts';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, params }) => ({
	run: await apiLoad<Run>(`/api/public/runs/${encodeURIComponent(params.token)}`, fetch)
});
