import { apiLoad } from '#lib/api.ts';
import type { CharacterDetail } from '#modules/logs/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	character: await apiLoad<CharacterDetail>(`/api/runs/${params.id}/characters/${params.char}`, fetch)
});
