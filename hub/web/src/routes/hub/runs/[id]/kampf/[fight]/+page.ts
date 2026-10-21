import { apiLoad, type FightDetail } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	fight: await apiLoad<FightDetail>(`/api/runs/${params.id}/fights/${encodeURIComponent(params.fight)}`, fetch)
});
