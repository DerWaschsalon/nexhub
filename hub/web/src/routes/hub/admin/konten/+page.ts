import { api, type Account } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	accounts: await api<Account[]>('/api/admin/users', undefined, fetch)
});
