import { apiLoad, apiOrNull } from '#lib/api.ts';
import type { RunOverview } from '#lib/api-types.ts';
import type { CharacterListItem } from '#modules/logs/api.ts';
import { loadParses, runParsesPath } from '#modules/parses/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	const [characters, overview, parses] = await Promise.all([
		apiLoad<CharacterListItem[]>(`/api/runs/${params.id}/characters`, fetch),
		// Fehlt die Datei des Runs, bleibt die Zusammenfassung ohne Tode und Fähigkeiten
		apiOrNull<RunOverview>(`/api/runs/${params.id}/overview`, 404, fetch).catch(() => null),
		loadParses(runParsesPath(params.id), fetch)
	]);
	return { characters, overview, parses };
};
