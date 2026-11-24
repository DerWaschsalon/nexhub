import { api, type Stats } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	stats: await api<Stats>('/api/admin/stats', undefined, fetch)
});
