import { api, type Device } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	devices: await api<Device[]>('/api/devices', undefined, fetch)
});
