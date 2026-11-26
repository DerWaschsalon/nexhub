import { apiLoad } from '#lib/api.ts';
import { LEGIONS_PATH, type LegionsOut } from '#modules/parses/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	legions: await apiLoad<LegionsOut>(LEGIONS_PATH, fetch)
});
