// Antworten der Hub-API für Runs (hub/api/nexhub_api/routes/runs.py und public.py).

/** Obergrenze von GET /api/runs (routes/runs.py) */
export const RUN_LIMIT = 500;

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
	/** Namen aus der Zusammenfassung, für Suche und Filter (modules/logs/filter.ts) */
	players: string[];
	bosses: string[];
};

/** Was jede Run-Ansicht braucht – im Hub und auf einer geteilten Seite. */
export type Run = Omit<RunListItem, 'id' | 'uploader' | 'created_at' | 'players' | 'bosses'> &
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

/** Eindeutiger Schlüssel eines Spielers: im Kampf die Actor-ID (zwei Spieler können gleich heißen,
 * z. B. nach einem Relog oder zwei gleich maskierte Namen), in der Run-Übersicht der Name. */
export const playerId = (p: { name: string; actor?: number }): string => (p.actor != null ? `#${p.actor}` : p.name);

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

// Charakterprofile (hub/api/nexhub_api/routes/characters.py, Format aus aion2.py)

export type CharacterStatus = 'offen' | 'ok' | 'nicht_gefunden' | 'name_maskiert' | 'fehler';

export type CharacterListItem = {
	id: number;
	name: string;
	cls: string | null;
	server_id: number;
	status: CharacterStatus;
	combat_power: number | null;
	item_level: number | null;
	fetched_at: string | null;
	/** derselbe Charakter in der Armory (nur in der Spielerliste eines Runs) */
	armory_id?: number | null;
};

export type CharacterItem = {
	/** Gegenstands-ID (ab Format 2), nötig zum Nachladen der Werte */
	id?: number | null;
	slot: number;
	slot_name: string;
	name: string;
	grade: string;
	enchant: number;
	exceed: number;
	icon: string | null;
	/** Werte wie im Spiel (aion2.py _item_detail); null = trägt der Charakter nicht mehr, fehlt = nicht geladen */
	detail?: ItemDetail | null;
};

export type ItemStat = { name: string; value: string; extra?: string | null };

export type ItemDetail = {
	level: number | null;
	category: string | null;
	/** Grundwerte; extra = Bonus aus Verzauberung */
	main: ItemStat[];
	/** zufällige Zusatzwerte (Seelenprägung) */
	sub: ItemStat[];
	stones: (ItemStat & { grade: string | null; icon: string | null })[];
	godstones: { name: string; desc: string | null; grade: string | null; icon: string | null }[];
	/** verstärkte Skills (Schmuck, Arkana) */
	skills: { name: string; level: number; icon: string | null }[];
	/** nur Arkana */
	set?: { name: string; equipped: number; total: number; bonuses: { degree: number; lines: string[] }[] };
};

export type CharacterData = {
	profile: {
		name: string;
		level: number;
		class: string;
		gender: string;
		race: number;
		server: string;
		guild: string | null;
		title: string | null;
		combat_power: number;
		image: string | null;
	};
	stats: { type: string; name: string; value: number; effects: string[] }[];
	titles: { owned: number; total: number; equipped: { name: string; grade: string; category: string; effects: string[] }[] };
	equipment: CharacterItem[];
	pet: { name: string; level: number; icon: string | null } | null;
	wing: { name: string; grade: string; enchant: number; icon: string | null } | null;
	skills: { name: string; category: string; level: number; learned: boolean; equipped: boolean; icon: string | null }[];
	daevanion: {
		id: number;
		name: string;
		icon: string | null;
		open: boolean;
		open_nodes: number;
		total_nodes: number;
		stats: string[];
		skills: string[];
		/** belegte Felder des Bretts (Raster 15×15); fehlt bei Momentaufnahmen vor dem Brett */
		nodes?: DaevanionNode[];
	}[];
};

export type DaevanionNode = {
	row: number;
	col: number;
	type: 'Start' | 'Stat' | 'SkillLevel' | string;
	grade: string;
	open: boolean;
	effects: string[];
};

/** Gespeicherte Momentaufnahme: ab Format 2 je Sprache, ältere sind ein Sprach-Objekt (Deutsch). */
export type CharacterSnapshot =
	| CharacterData
	| {
			v: number;
			de?: CharacterData;
			en?: CharacterData;
			/** nachgeladene Werte je Gegenstand (Runs, Knopf „Item-Werte laden“) */
			details?: { state: 'laden' | 'ok' | 'fehler'; at?: string; error?: string };
	  };

/** Die Momentaufnahme in der Sprache der Seite. */
export function localized(data: CharacterSnapshot, lang: string): CharacterData {
	if (!('v' in data)) return data;
	return (lang === 'de' ? data.de : data.en) ?? data.en ?? (data.de as CharacterData);
}

export type CharacterDetail = CharacterListItem & { data: CharacterSnapshot | null; error: string | null };
