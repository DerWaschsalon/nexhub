import { api } from '#lib/api.ts';
import type { Device } from '#modules/devices/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	devices: await api<Device[]>('/api/devices', undefined, fetch)
});
