import { apiLoad } from '#lib/api.ts';
import { kindOf, periodOf, sinceMs, type DungeonStat } from '#modules/logs/dungeons.ts';
import type { PageLoad } from './$types';

// Alle Runs liefern die Stufen der Dungeons (dungeons.ts), der Zeitraum die Zahlen auf den Karten
export const load: PageLoad = async ({ fetch, url }) => {
	const period = periodOf(url.searchParams.get('zeit'));
	const since = sinceMs(period);
	const [all, inPeriod] = await Promise.all([
		apiLoad<DungeonStat[]>('/api/runs/dungeons', fetch),
		since == null ? null : apiLoad<DungeonStat[]>(`/api/runs/dungeons?since_ms=${since}`, fetch)
	]);
	return { period, kind: kindOf(url.searchParams.get('art')), all, inPeriod: inPeriod ?? all };
};
