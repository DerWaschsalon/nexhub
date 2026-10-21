import type { FightPlayer } from './api.ts';

// Treffer derselben Fähigkeit, die so dicht aufeinander folgen, gehören zu einem Zauber
// (Mehrfachtreffer, Kanalisieren). DoTs zählen nicht als Zauber, ihre Ticks kommen von allein.
const SAME_CAST_MS = 400;

export type Cast = { t: number; code: number | null; name: string };

/** Zauber eines Spielers in zeitlicher Reihenfolge. */
export function castsOf(player: FightPlayer): Cast[] {
	const out: Cast[] = [];
	for (const s of player.skills) {
		if (s.dot) continue;
		let last = -Infinity;
		for (const t of s.casts) {
			if (t - last >= SAME_CAST_MS) out.push({ t, code: s.code, name: s.name });
			last = t;
		}
	}
	return out.sort((a, b) => a.t - b.t);
}
