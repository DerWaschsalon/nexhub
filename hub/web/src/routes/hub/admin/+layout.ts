import { redirect } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';

// Admin-Seiten nur für Admins; die API prüft das zusätzlich bei jeder Anfrage
export const load: LayoutLoad = async ({ parent }) => {
	const { me } = await parent();
	if (me.role !== 'admin') redirect(307, '/hub');
};
