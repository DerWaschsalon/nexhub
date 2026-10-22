// Vergleich: links ein Charakter aus der Armory, rechts ein beliebiger, live von der Website.
// Beides steht in der Adresse (?links=5&rechts=2302/ReZero), damit sich der Vergleich teilen lässt.
import { api, apiLoad } from '#lib/api.ts';
import { i18n } from '#lib/i18n.svelte.ts';
import type { ArmoryDetail, ArmoryItem, ArmoryLive } from '#modules/armory/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, url }) => {
	const characters = await apiLoad<ArmoryItem[]>('/api/armory', fetch);
	const leftId = Number(url.searchParams.get('links')) || characters.find((c) => c.mine)?.id || characters[0]?.id;
	const left = leftId ? await apiLoad<ArmoryDetail>(`/api/armory/${leftId}`, fetch) : null;

	// rechts: "Server-ID/Name"; Fehler (nicht gefunden, Website weg) zeigt die Seite an
	const [server, name] = (url.searchParams.get('rechts') ?? '').split('/');
	let right: ArmoryLive | null = null;
	let rightError = '';
	if (server && name) {
		const query = new URLSearchParams({ server_id: server, name, lang: i18n.lang });
		try {
			right = await api<ArmoryLive>(`/api/armory/live?${query}`, undefined, fetch);
		} catch (e) {
			rightError = e instanceof Error ? e.message : String(e);
		}
	}
	return { characters, left, right, rightError };
};
