import { api } from '#lib/api.ts';
import { RUN_LIMIT, type RunListItem } from '#modules/logs/api.ts';
import type { PageLoad } from './$types';

// Gefiltert wird im Browser (modules/logs/filter.ts), deshalb so viele, wie die API hergibt
export const load: PageLoad = async ({ fetch }) => ({
	runs: await api<RunListItem[]>(`/api/runs?limit=${RUN_LIMIT}`, undefined, fetch)
});
