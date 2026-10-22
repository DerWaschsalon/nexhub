// Build-Check eines Armory-Charakters: der Charakter und sein letzter Check (fehlt, solange noch keiner lief).
import { ApiError, api, apiLoad } from '#lib/api.ts';
import type { ArmoryDetail } from '#modules/armory/api.ts';
import type { BuildCheck } from '#modules/armory/check.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	const character = await apiLoad<ArmoryDetail>(`/api/armory/${params.id}`, fetch);
	const check = await api<BuildCheck>(`/api/armory/${params.id}/check`, undefined, fetch).catch((e) => {
		if (e instanceof ApiError && e.status === 404) return null;
		throw e;
	});
	return { character, check };
};
