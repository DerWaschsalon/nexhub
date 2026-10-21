import { api, loadMe, type PublicInfo } from '#lib/api.ts';
import type { LayoutLoad } from './$types';

// Alles läuft im Browser; Daten kommen aus der API
export const ssr = false;
export const prerender = false;

// Wer angemeldet ist und ob der Login eingerichtet ist, brauchen beide Bereiche
export const load: LayoutLoad = async ({ fetch }) => {
	const [me, info] = await Promise.all([
		loadMe(fetch),
		api<PublicInfo>('/api/public/info', undefined, fetch).catch((): PublicInfo => ({ login: false, operator: null, hoster: null }))
	]);
	return { me, info };
};
