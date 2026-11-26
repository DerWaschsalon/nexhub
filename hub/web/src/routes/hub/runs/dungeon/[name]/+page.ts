import { error } from '@sveltejs/kit';
import { apiLoad } from '#lib/api.ts';
import type { RunListItem } from '#modules/logs/api.ts';
import { groupDungeons, periodOf, sinceMs, type DungeonStat } from '#modules/logs/dungeons.ts';
import type { PageLoad } from './$types';

/** So viele Runs einer Schwierigkeit lädt die Seite (die API gibt höchstens 500) */
const RUNS = 200;

export const load: PageLoad = async ({ fetch, url, params }) => {
	const period = periodOf(url.searchParams.get('zeit'));
	const since = sinceMs(period);
	const [all, inPeriod] = await Promise.all([
		apiLoad<DungeonStat[]>('/api/runs/dungeons', fetch),
		since == null ? null : apiLoad<DungeonStat[]>(`/api/runs/dungeons?since_ms=${since}`, fetch)
	]);
	// Alle Schwierigkeiten des Dungeons (über alle Runs) und ihre Zahlen im Zeitraum
	const group = groupDungeons(all, all).find((g) => g.name === params.name);
	if (!group) error(404, 'Dungeon nicht gefunden');
	const current = groupDungeons(all, inPeriod ?? all).find((g) => g.name === params.name);
	const wanted = Number(url.searchParams.get('stufe'));
	const played = current?.tiers ?? [];
	const tier = group.tiers.find((x) => x.dungeon_id === wanted)
		?? group.tiers.find((x) => x.dungeon_id === played.at(-1)?.dungeon_id)
		?? group.tiers.at(-1)!;
	const q = new URLSearchParams({ dungeon_id: String(tier.dungeon_id), limit: String(RUNS) });
	if (since != null) q.set('since_ms', String(since));
	return {
		period,
		group,
		stats: new Map(played.map((x) => [x.dungeon_id, x])),
		tier,
		runs: await apiLoad<RunListItem[]>(`/api/runs?${q}`, fetch)
	};
};
