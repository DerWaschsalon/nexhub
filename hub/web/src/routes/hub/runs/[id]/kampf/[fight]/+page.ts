import { apiLoad } from '#lib/api.ts';
import type { Fight } from '#modules/logs/api.ts';
import { loadParses, runParsesPath } from '#modules/parses/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	const [fight, parses] = await Promise.all([
		apiLoad<Fight>(`/api/runs/${params.id}/fights/${encodeURIComponent(params.fight)}`, fetch),
		loadParses(runParsesPath(params.id), fetch)
	]);
	return { fight, parses };
};
