import { apiLoad, type RunDetail } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	run: await apiLoad<RunDetail>(`/api/runs/${params.id}`, fetch)
});
