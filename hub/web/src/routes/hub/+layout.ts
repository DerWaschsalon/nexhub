import { redirect } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';

// Alles unter /hub braucht eine Anmeldung; sonst zur Login-Seite und danach hierher zurück
export const load: LayoutLoad = async ({ parent, url }) => {
	const { me } = await parent();
	if (!me) redirect(307, `/login?next=${encodeURIComponent(url.pathname + url.search)}`);
	return { me };
};
