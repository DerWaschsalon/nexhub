// Daten kommen aus der Hub-API (hub/api/nexhub_api/routes/runs.py und public.py).
// NexLogs läuft auf derselben Adresse wie der Hub, das Login-Cookie geht automatisch mit.

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

export async function api<T>(path: string): Promise<T> {
	const r = await fetch(path, { credentials: 'same-origin' });
	if (!r.ok) {
		const body = await r.json().catch(() => null);
		throw new ApiError(r.status, body?.detail ?? `Fehler ${r.status}`);
	}
	return (await r.json()) as T;
}

export type Player = { name: string; cls: string | null; damage: number; dps: number };

export type Boss = {
	fight: string;
	name: string;
	mob: number;
	start_ms: number;
	duration_ms: number;
	killed: boolean;
	players: Player[];
};

export type Summary = { fight_ms: number; players: Player[]; bosses: Boss[] };

export type RunListItem = {
	id: number;
	dungeon: string;
	difficulty: string | null;
	start_ms: number;
	end_ms: number;
	complete: boolean;
	bosses_total: number;
	bosses_killed: number;
	fights: number;
	hits: number;
	character: string | null;
	uploader: string;
	created_at: string;
};

export type Run = Omit<RunListItem, 'id' | 'uploader' | 'created_at'> &
	Partial<Pick<RunListItem, 'id' | 'uploader' | 'created_at'>> & { summary: Summary };

export type FightSkill = {
	code: number | null;
	name: string;
	dot: boolean;
	damage: number;
	share: number;
	hits: number;
	crit: number;
	back: number;
	perfect: number;
	double: number;
	parry: number;
	min: number;
	max: number;
	avg: number;
	multi_hits: number;
	multi_damage: number;
	/** aktive Spezialisierungen 1–5 */
	specs: number[];
	/** Zeitpunkte der Treffer in ms seit Kampfbeginn */
	casts: number[];
};

/** Abschnitt eines Buffs: [start, ende, stapel, wodurch beendet], ms seit Kampfbeginn. */
export type BuffSegment = [number, number, number, number];
export type Buff = { actor: number; by: number; id: number; up: number; segments: BuffSegment[] };

export type FightPlayer = Player & { actor: number; skills: FightSkill[] };

export type Fight = {
	fight: string;
	name: string;
	mob: number;
	duration_ms: number;
	killed: boolean;
	max_hp: number;
	run_players: string[];
	players: FightPlayer[];
	timeline: { bucket_ms: number; players: { actor: number; damage: number[] }[] } | null;
	deaths: { name: string; t_ms: number; revived_ms: number | null }[];
	target: number | null;
	buffs: Buff[];
};

/** Quelle eines Runs: eigener Run im Hub (mit Login) oder geteilter Link (ohne Login). */
export type Source = { kind: 'run'; id: string } | { kind: 'shared'; token: string };

export const runUrl = (s: Source) => (s.kind === 'run' ? `/api/runs/${s.id}` : `/api/public/runs/${s.token}`);
export const fightUrl = (s: Source, fight: string) => `${runUrl(s)}/fights/${encodeURIComponent(fight)}`;
