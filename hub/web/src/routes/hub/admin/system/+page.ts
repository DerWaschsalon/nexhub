import { api, type Status } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	status: await api<Status>('/api/admin/status', undefined, fetch)
});
