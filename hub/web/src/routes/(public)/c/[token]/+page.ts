// Geteilter Build-Check: ohne Login, Stand vom letzten Check.
import { apiLoad } from '#lib/api.ts';
import type { SharedCheck } from '#modules/armory/check.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	check: await apiLoad<SharedCheck>(`/api/public/check/${encodeURIComponent(params.token)}`, fetch)
});
