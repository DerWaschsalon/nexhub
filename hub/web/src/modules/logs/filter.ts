// Suche und Filter der Run-Liste. Gefiltert wird im Browser über das, was /api/runs liefert;
// der Zustand steht in der Adresse (?q=…&dungeon=…), damit Zurück aus einem Run ihn behält.
import type { RunListItem } from '#modules/logs/api.ts';

export type RunFilter = {
	/** Freitext: jedes Wort muss in Dungeon, Schwierigkeit, Boss, Spieler oder Uploader vorkommen */
	q: string;
	dungeon: string;
	difficulty: string;
	player: string;
	uploader: string;
	/** '' alle, 'clear' alle Bosse besiegt, 'open' nicht alle */
	status: string;
	/** '' jederzeit, sonst gespielt in den letzten n Tagen */
	days: string;
};

const KEYS = ['q', 'dungeon', 'difficulty', 'player', 'uploader', 'status', 'days'] as const;
export const PERIODS = ['1', '7', '30', '90'];

export function fromParams(params: Pick<URLSearchParams, 'get'>): RunFilter {
	return Object.fromEntries(KEYS.map((k) => [k, params.get(k) ?? ''])) as RunFilter;
}

/** Nur gesetzte Werte, damit die Adresse ohne Filter sauber bleibt. */
export function toSearch(f: RunFilter): string {
	const params = new URLSearchParams();
	for (const k of KEYS) if (f[k].trim()) params.set(k, f[k].trim());
	const s = params.toString();
	return s ? `?${s}` : '';
}

export const isActive = (f: RunFilter): boolean => KEYS.some((k) => f[k].trim() !== '');

const sorted = (values: Iterable<string>) => [...new Set(values)].filter(Boolean).sort((a, b) => a.localeCompare(b));

/** Auswahl für die Listenfelder, aus den geladenen Runs. */
export function filterOptions(runs: RunListItem[]) {
	return {
		dungeons: sorted(runs.map((r) => r.dungeon)),
		difficulties: sorted(runs.map((r) => r.difficulty ?? '')),
		players: sorted(runs.flatMap((r) => [...r.players, r.character ?? ''])),
		uploaders: sorted(runs.map((r) => r.uploader))
	};
}

function haystack(r: RunListItem): string {
	return [r.dungeon, r.difficulty, r.uploader, r.character, ...r.players, ...r.bosses].join('\n').toLowerCase();
}

export function applyFilter(runs: RunListItem[], f: RunFilter, now = Date.now()): RunListItem[] {
	const words = f.q.toLowerCase().split(/\s+/).filter(Boolean);
	const since = f.days ? now - Number(f.days) * 86_400_000 : null;
	return runs.filter(
		(r) =>
			(!f.dungeon || r.dungeon === f.dungeon) &&
			(!f.difficulty || r.difficulty === f.difficulty) &&
			(!f.player || r.players.includes(f.player) || r.character === f.player) &&
			(!f.uploader || r.uploader === f.uploader) &&
			(f.status !== 'clear' || r.bosses_killed === r.bosses_total) &&
			(f.status !== 'open' || r.bosses_killed !== r.bosses_total) &&
			(since === null || r.start_ms >= since) &&
			(!words.length || words.every((w) => haystack(r).includes(w)))
	);
}
