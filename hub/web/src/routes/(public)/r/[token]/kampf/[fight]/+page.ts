import { apiLoad } from '#lib/api.ts';
import type { Fight } from '#modules/logs/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	fight: await apiLoad<Fight>(
		`/api/public/runs/${encodeURIComponent(params.token)}/fights/${encodeURIComponent(params.fight)}`,
		fetch
	)
});
