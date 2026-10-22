// Geteilter Vergleich: ohne Login, Werte bei jedem Öffnen neu (rechts live von der Website).
import { apiLoad } from '#lib/api.ts';
import { i18n } from '#lib/i18n.svelte.ts';
import type { ArmoryComparison } from '#modules/armory/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	comparison: await apiLoad<ArmoryComparison>(
		`/api/public/vergleich/${encodeURIComponent(params.token)}?lang=${i18n.lang}`,
		fetch
	)
});
