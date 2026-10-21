// Antworten der Hub-API für Runs (hub/api/nexhub_api/routes/runs.py und public.py).

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

/** Was jede Run-Ansicht braucht – im Hub und auf einer geteilten Seite. */
export type Run = Omit<RunListItem, 'id' | 'uploader' | 'created_at'> &
	Partial<Pick<RunListItem, 'uploader'>> & { summary: Summary };

/** Run im Hub (mit Login): dazu Teilen und Löschen. */
export type RunDetail = RunListItem & Run & { size: number; can_delete: boolean; share_url: string | null };

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
