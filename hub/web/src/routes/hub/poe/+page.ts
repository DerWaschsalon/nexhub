import { gameFrom, loadWatches } from '#modules/poe/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, url }) => {
	const game = gameFrom(url.searchParams.get('game'));
	return { game, list: await loadWatches(game, fetch) };
};
