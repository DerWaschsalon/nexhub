import { pageError } from '#lib/api.ts';
import { gameFrom, loadWatches } from '#modules/poe/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, url }) => {
	const game = gameFrom(url.searchParams.get('game'));
	try {
		return { game, list: await loadWatches(game, fetch) };
	} catch (e) {
		pageError(e); // z. B. 503, solange der Hub die Preise noch lädt
	}
};
