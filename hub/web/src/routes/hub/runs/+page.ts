import { api, type Run } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	runs: await api<Run[]>('/api/runs', undefined, fetch)
});
