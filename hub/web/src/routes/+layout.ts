import { loadHealth, loadMe } from '#lib/api.ts';
import type { LayoutLoad } from './$types';

// Alles läuft im Browser; Daten kommen aus der API
export const ssr = false;
export const prerender = false;

export const load: LayoutLoad = async ({ fetch }) => {
	const [me, health] = await Promise.all([loadMe(fetch), loadHealth(fetch)]);
	return { me, health };
};
