import { api, type RunDetail } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	run: await api<RunDetail>(`/api/runs/${params.id}`, undefined, fetch)
});
