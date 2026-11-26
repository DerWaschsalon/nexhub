import { apiLoad } from '#lib/api.ts';
import type { Fight } from '#modules/logs/api.ts';
import { loadParses, sharedParsesPath } from '#modules/parses/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	const [fight, parses] = await Promise.all([
		apiLoad<Fight>(
			`/api/public/runs/${encodeURIComponent(params.token)}/fights/${encodeURIComponent(params.fight)}`,
			fetch
		),
		loadParses(sharedParsesPath(params.token), fetch)
	]);
	return { fight, parses };
};
