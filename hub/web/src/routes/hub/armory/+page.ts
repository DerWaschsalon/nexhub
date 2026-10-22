import { apiLoad } from '#lib/api.ts';
import type { ArmoryItem } from '#modules/armory/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	characters: await apiLoad<ArmoryItem[]>('/api/armory', fetch)
});
