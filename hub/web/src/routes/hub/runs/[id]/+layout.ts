import { apiLoad } from '#lib/api.ts';
import type { RunDetail } from '#modules/logs/api.ts';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, params }) => ({
	run: await apiLoad<RunDetail>(`/api/runs/${params.id}`, fetch)
});
