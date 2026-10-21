import { api } from '#lib/api.ts';
import type { RunListItem } from '#modules/logs/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	runs: await api<RunListItem[]>('/api/runs', undefined, fetch)
});
