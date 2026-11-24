import { apiLoad } from '#lib/api.ts';
import type { ArmoryDetail } from '#modules/armory/api.ts';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch, params }) => ({
	character: await apiLoad<ArmoryDetail>(`/api/armory/${params.id}`, fetch)
});
