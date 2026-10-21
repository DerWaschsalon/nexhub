import { apiLoad, type FightDetail } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	fight: await apiLoad<FightDetail>(
		`/api/public/runs/${encodeURIComponent(params.token)}/fights/${encodeURIComponent(params.fight)}`,
		fetch
	)
});
