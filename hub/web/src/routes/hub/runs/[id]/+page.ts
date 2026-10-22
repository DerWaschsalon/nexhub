import { apiLoad } from '#lib/api.ts';
import type { CharacterListItem } from '#modules/logs/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	characters: await apiLoad<CharacterListItem[]>(`/api/runs/${params.id}/characters`, fetch)
});
