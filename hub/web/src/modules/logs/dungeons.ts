// Runs nach Dungeon: Zeitraum (Heute, Woche, Alle), Schwierigkeiten und Gruppierung für die Übersicht
// (routes/hub/runs/) und die Seite eines Dungeons (routes/hub/runs/dungeon/[name]/).
//
// AION 2 gibt jeder Schwierigkeit eine eigene Dungeon-ID. Die API zählt je ID (GET /api/runs/dungeons), hier
// werden IDs mit gleichem Namen zu einem Dungeon. Name und Schwierigkeit kommen von Abyss Logs (Hub, Modul
// parses/extras.py), sonst aus der Aufnahme; fehlt die Schwierigkeit ganz, heißt sie „Stufe n“ nach der
// Reihenfolge der IDs – gezählt über alle Runs, damit die Nummer in jedem Zeitraum gleich bleibt.
import type * as Api from '#lib/api-types.ts';
import { i18n } from '#lib/i18n.svelte.ts';

export type DungeonStat = Api.DungeonStat;

export const PERIODS = ['heute', 'woche', 'alle'] as const;
export type Period = (typeof PERIODS)[number];
export const KINDS = ['gruppe', 'solo', 'alle'] as const;
export type Kind = (typeof KINDS)[number];

export const periodOf = (v: string | null): Period => (PERIODS.includes(v as Period) ? (v as Period) : 'heute');
export const kindOf = (v: string | null): Kind => (KINDS.includes(v as Kind) ? (v as Kind) : 'gruppe');

/** Beginn des Zeitraums in ms (Ortszeit): heute 0 Uhr, Montag 0 Uhr; null = alle Runs. */
export function sinceMs(period: Period, now = new Date()): number | null {
	if (period === 'alle') return null;
	const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
	if (period === 'woche') start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
	return start.getTime();
}

/** Höchstens so viele Spieler: Inhalt für eine Person (Solo), auch wenn einmal jemand mitlief */
const SOLO_PLAYERS = 2;
const GERMAN: Record<string, string> = {
	Hard: 'Schwer', Normal: 'Normal', Easy: 'Leicht', Exploration: 'Erkundung', Extreme: 'Extrem', Hell: 'Hölle',
	Insane: 'Wahnsinn', Doom: 'Verderben'
};
const HARD = ['Hard', 'Extreme', 'Hell', 'Insane', 'Doom'];
const EASY = ['Easy', 'Exploration'];

/** Kern der Schwierigkeit ohne „Conquest [ … ]“ (Abyss Logs schreibt „Conquest [Hard]“) */
const core = (d: string) => d.match(/^Conquest \[(.+)\]$/)?.[1] ?? d;

/** Schwierigkeit zum Anzeigen: übersetzt, „Stage 4“ wird „Stufe 4“ */
export function tierName(difficulty: string): string {
	const d = core(difficulty);
	const stage = d.match(/^(?:Stage|Level) (\d+)$/);
	if (i18n.lang !== 'de') return d;
	return stage ? `Stufe ${stage[1]}` : (GERMAN[d] ?? d);
}

/** Farbe der Schwierigkeit: schwer in Orange, leicht in Grün */
export const tierTone = (difficulty: string | null): 'hard' | 'easy' | null =>
	!difficulty ? null : HARD.includes(core(difficulty)) ? 'hard' : EASY.includes(core(difficulty)) ? 'easy' : null;

export type Tier = DungeonStat & {
	/** Reihenfolge der ID im Dungeon, für „Stufe n“, wenn die Schwierigkeit fehlt */
	stage: number;
	/** Schwierigkeit nur einmal im Dungeon: ohne Beschriftung */
	only: boolean;
};

export type DungeonGroup = {
	name: string;
	solo: boolean;
	/** im gewählten Zeitraum, nach ID aufsteigend; leer = im Zeitraum nicht gespielt */
	tiers: Tier[];
	runs: number;
	kills: number;
	wipes: number;
	fastest_ms: number | null;
	players: number;
	last_ms: number;
};

/** Dungeons aus den Kennzahlen des Zeitraums (`period`); `all` (alle Runs) liefert Stufen und Solo-Kennung. */
export function groupDungeons(all: DungeonStat[], period: DungeonStat[]): DungeonGroup[] {
	const byName = new Map<string, DungeonStat[]>();
	for (const s of all) byName.set(s.dungeon, [...(byName.get(s.dungeon) ?? []), s]);
	const inPeriod = new Map(period.map((s) => [s.dungeon_id, s]));
	const groups: DungeonGroup[] = [];
	for (const [name, stats] of byName) {
		const ordered = [...stats].sort((a, b) => a.dungeon_id - b.dungeon_id);
		const tiers = ordered.flatMap((s, i): Tier[] => {
			const p = inPeriod.get(s.dungeon_id);
			if (!p) return [];
			return [{ ...p, difficulty: p.difficulty ?? s.difficulty, stage: i + 1, only: ordered.length === 1 }];
		});
		if (!tiers.length) continue;
		const fastest = tiers.map((t) => t.fastest_ms).filter((x): x is number => x != null);
		groups.push({
			name,
			solo: Math.max(...stats.map((s) => s.players)) <= SOLO_PLAYERS,
			tiers,
			runs: sum(tiers, 'runs'),
			kills: sum(tiers, 'kills'),
			wipes: sum(tiers, 'wipes'),
			fastest_ms: fastest.length ? Math.min(...fastest) : null,
			players: Math.max(...tiers.map((t) => t.players)),
			last_ms: Math.max(...tiers.map((t) => t.last_ms))
		});
	}
	return groups.sort((a, b) => b.last_ms - a.last_ms);
}

const sum = (tiers: Tier[], key: 'runs' | 'kills' | 'wipes') => tiers.reduce((s, t) => s + t[key], 0);

export const matchesKind = (g: DungeonGroup, kind: Kind) => kind === 'alle' || (kind === 'solo') === g.solo;

/** Anteil getöteter Bosse in Prozent, ohne Kämpfe null */
export const killRate = (kills: number, wipes: number): number | null =>
	kills + wipes ? Math.round((100 * kills) / (kills + wipes)) : null;

/** Farbton eines Dungeons, fest aus dem Namen: jeder Dungeon leuchtet in seiner Farbe */
export function dungeonHue(name: string): number {
	let h = 0;
	for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
	return h;
}

/** Adresse der Seite eines Dungeons mit Zeitraum und Schwierigkeit */
export function dungeonHref(name: string, period: Period, tier?: number): string {
	const q = new URLSearchParams();
	if (period !== 'heute') q.set('zeit', period);
	if (tier != null) q.set('stufe', String(tier));
	const s = q.toString();
	return `/hub/runs/dungeon/${encodeURIComponent(name)}${s ? `?${s}` : ''}`;
}
