// Erzeugt aus den Modellen der Hub-API (hub/api/nexhub_api/web_types.py). Nicht von Hand ändern:
// cd hub/api && uv run python -m nexhub_api.web_types

export type AccountOut = {
	id: number;
	discord_id: string;
	name: string;
	avatar_url: string | null;
	role: "admin" | "member";
	created_at: string;
	last_login_at: string;
	blocked: boolean;
	sessions: number;
};

export type Approved = {
	name: string;
};

export type ArmoryDetail = {
	id: number;
	name: string;
	cls: string | null;
	server_id: number;
	status: "offen" | "ok" | "nicht_gefunden" | "name_maskiert" | "fehler";
	combat_power: number | null;
	item_level: number | null;
	fetched_at: string | null;
	armory_id: number | null;
	owner: string;
	mine: boolean;
	class_name: string | null;
	server: string | null;
	image: string | null;
	data: Record<string, unknown> | null;
	error: string | null;
	days: Day[];
	can_delete: boolean;
	hints: Record<string, Record<string, unknown>[]>;
	ratings: Record<string, Record<string, unknown>>;
};

export type ArmoryOut = {
	id: number;
	name: string;
	cls: string | null;
	server_id: number;
	status: "offen" | "ok" | "nicht_gefunden" | "name_maskiert" | "fehler";
	combat_power: number | null;
	item_level: number | null;
	fetched_at: string | null;
	armory_id: number | null;
	owner: string;
	mine: boolean;
	class_name: string | null;
	server: string | null;
	image: string | null;
};

export type ArmoryRefreshStarted = {
	started: boolean;
};

export type Bench = {
	pct: number;
	lowest: number;
	top75: number;
	median: number;
	top25: number;
	top10: number;
	highest: number;
	week_before_median: number | null;
	samples: number;
	characters: number;
	cp_floor: number | null;
	cp_ceil: number | null;
};

export type BisOut = {
	cls: string;
	size: number;
	tiers: Record<string, number>;
	raid: string | null;
	oldest: string | null;
	newest: string | null;
	min_sample: number;
	slots: Record<string, unknown>[];
	skills: Record<string, unknown>[];
};

export type Boss = {
	mob: number;
	name: string;
	kills: number;
	items: Item[];
};

export type BossParse = {
	eu: number | null;
	guild: number | null;
};

export type Bound = {
	letter: string;
	low: number;
};

export type Card = {
	slot: string;
	name: string | null;
	icon: string | null;
	grade: string | null;
	score: number | null;
	letter: string | null;
	steps: Step[];
	after: [number, number];
	mean: number;
	after_letter: string;
	tries: number;
	per_try: number;
};

export type CharacterDetail = {
	id: number;
	name: string;
	cls: string | null;
	server_id: number;
	status: "offen" | "ok" | "nicht_gefunden" | "name_maskiert" | "fehler";
	combat_power: number | null;
	item_level: number | null;
	fetched_at: string | null;
	armory_id: number | null;
	data: Record<string, unknown> | null;
	error: string | null;
};

export type CharacterOut = {
	id: number;
	name: string;
	cls: string | null;
	server_id: number;
	status: "offen" | "ok" | "nicht_gefunden" | "name_maskiert" | "fehler";
	combat_power: number | null;
	item_level: number | null;
	fetched_at: string | null;
	armory_id: number | null;
};

export type ClassOut = {
	cls: string;
	size: number;
	hard: number;
	newest: string;
};

export type ClassPool = {
	cls: string;
	players: number;
	counted_at: string | null;
};

export type CompareShare = {
	left: number;
	server_id: number;
	name: string;
};

export type ComparisonOut = {
	left: Side;
	right: Live | null;
	right_error: string | null;
};

export type Day = {
	day: string;
	combat_power: number | null;
	item_level: number | null;
};

export type DeviceOut = {
	id: number;
	name: string;
	created_at: string;
	last_seen_at: string | null;
	version: string | null;
};

export type DeviceParses = {
	bosses: Record<string, Record<string, BossParse>>;
};

export type DeviceSelf = {
	id: number;
	name: string;
	owner: string;
};

export type Dungeon = {
	dungeon_id: number;
	dungeon: string;
	difficulty: string | null;
	runs: number;
	bosses: Boss[];
};

export type DungeonStat = {
	dungeon_id: number;
	dungeon: string;
	difficulty: string | null;
	category: string | null;
	runs: number;
	complete: number;
	fastest_ms: number | null;
	kills: number;
	wipes: number;
	players: number;
	last_ms: number;
};

export type FeedbackEntry = {
	id: number;
	title: string;
	body: string;
	status: "neu" | "gesehen" | "geplant" | "erledigt" | "abgelehnt";
	created_at: string;
	votes: number;
	voted: boolean;
	mine: boolean;
	author: string | null;
};

export type Forwarded = {
	forwarded: boolean;
};

export type HTTPValidationError = {
	detail: ValidationError[];
};

export type Hall = {
	computed_at: string | null;
	entries: TopParse[];
};

export type Hit = {
	name: string;
	server_id: number;
	server: string | null;
	level: number | null;
	cls: string | null;
	character_id: string;
	image: string | null;
	taken_by: string | null;
};

export type Info = {
	login: boolean;
	operator: Operator | null;
	hoster: string | null;
};

export type Item = {
	item_id: number;
	drops: number;
	kills: number;
	one_in: number | null;
	one_in_low: number | null;
	one_in_high: number | null;
};

export type KnownLegion = {
	name: string;
	characters: number;
};

export type Legions = {
	legions: string[];
};

export type LegionsOut = {
	legions: string[];
	known: KnownLegion[];
};

export type Live = {
	name: string;
	server_id: number;
	data: Record<string, unknown>;
};

export type Loot = {
	min_kills: number;
	dungeons: Dungeon[];
};

export type Me = {
	discord_id: string;
	name: string;
	avatar_url: string | null;
	role: "admin" | "member";
};

export type NewCharacter = {
	name: string;
	server_id: number;
	character_id: string;
};

export type NewEntry = {
	title: string;
	body?: string;
};

export type NewStatus = {
	status: "neu" | "gesehen" | "geplant" | "erledigt" | "abgelehnt";
};

export type Operator = {
	name: string;
	address: string[];
	email: string | null;
};

export type PairApprove = {
	code: string;
	name?: string | null;
};

export type PairPoll = {
	device_code: string;
};

export type PairResult = {
	status: "pending" | "approved";
	token: string | null;
	device_id: number | null;
	device_name: string | null;
};

export type PairStart = {
	name?: string;
	version?: string | null;
};

export type PairStarted = {
	device_code: string;
	user_code: string;
	verification_uri: string;
	verification_uri_complete: string;
	expires_in: number;
	interval: number;
};

export type Parse = {
	eu: number | null;
	eu_n: number | null;
	eu_at: string | null;
	eu_cp: number | null;
	eu_few: boolean;
	guild: number | null;
	guild_n: number;
	member: boolean;
	bench: Bench | null;
};

export type Piece = {
	slot: string;
	name: string | null;
	icon: string | null;
	grade: string | null;
	score: number | null;
	letter: string | null;
};

export type Planned = {
	key: string;
	start: number;
};

export type RefreshStarted = {
	started: number;
};

export type ReportBoss = {
	name: string;
	mob: number;
	killed: boolean;
	duration_ms: number;
	players: ReportPlayer[];
};

export type ReportPlayer = {
	name: string;
	cls: string | null;
	damage: number;
	dps: number;
};

export type Rules = {
	bounds: Bound[];
	region: string;
	pool_size: number;
	goals: string[];
	default_goal: string;
	max_rerolls: number;
	tier_best: number;
	tier_good: number;
};

export type RunDeath = {
	fight: string;
	boss: string;
	name: string;
	cls: string | null;
	t_ms: number;
	revived_ms: number | null;
	skill: number | null;
};

export type RunDetail = {
	id: number;
	dungeon_id: number;
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
	players: string[];
	classes: (string | null)[];
	bosses: string[];
	results: boolean[];
	size: number;
	can_delete: boolean;
	share_url: string | null;
	summary: Record<string, unknown>;
};

export type RunOut = {
	id: number;
	dungeon_id: number;
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
	players: string[];
	classes: (string | null)[];
	bosses: string[];
	results: boolean[];
};

export type RunOverview = {
	deaths: RunDeath[];
	skills: RunSkill[];
};

export type RunParses = {
	guild_min: number;
	fights: Record<string, Record<string, Parse>>;
};

export type RunReport = {
	dungeon: string;
	difficulty?: string | null;
	dungeon_id: number;
	bosses_total: number;
	bosses_killed: number;
	complete: boolean;
	start_ms: number;
	end_ms: number;
	fight_ms: number;
	players: ReportPlayer[];
	bosses?: ReportBoss[];
	image_webp?: string | null;
};

export type RunSkill = {
	code: number | null;
	name: string;
	player: string;
	cls: string | null;
	damage: number;
	hits: number;
};

export type Schedule = {
	now: number;
	server_zone: string;
	events: ScheduleEntry[];
	week: Planned[];
};

export type ScheduleEntry = {
	key: string;
	name_en: string;
	name_de: string;
	start: number;
	open_until: number | null;
	place: string;
};

export type Shared = {
	share_url: string | null;
};

export type SharedRun = {
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
	summary: Record<string, unknown>;
};

export type Side = {
	name: string;
	cls: string | null;
	class_name: string | null;
	data: Record<string, unknown> | null;
};

export type Stats = {
	days: string[];
	runs: number[];
	accounts: number[];
	total_runs: number;
	total_accounts: number;
	characters: number;
	devices: number;
	devices_active: number;
	devices_by_version: Record<string, number>;
	bis: ClassPool[];
};

export type Status = {
	version: string;
	db_revision: string;
	login: boolean;
	member_check: boolean;
	accounts: number;
	active_sessions: number;
};

export type Step = {
	line: string;
	chance: number;
	tries: number;
	skill_only: boolean;
	tiers: Record<string, Target[]>;
};

export type Target = {
	name: string;
	gain_lo: number;
	gain_hi: number;
};

export type TopParse = {
	name: string;
	cls: string | null;
	eu: number;
	boss: string;
	fight: string;
	run_id: number;
	dungeon: string;
	start_ms: number;
};

export type Unreachable = {
	slot: string;
	name: string | null;
	icon: string | null;
	grade: string | null;
	score: number | null;
	letter: string | null;
	reason: "no_rolls" | "too_far";
};

export type UpgradePlan = {
	goal: "S+" | "BiS";
	group: string;
	cards: Card[];
	bind: Piece[];
	done: Piece[];
	unreachable: Unreachable[];
	arcana: Piece[];
};

export type Uploaded = {
	id: number;
	url: string;
	duplicate: boolean;
};

export type ValidationError = {
	loc: (string | number)[];
	msg: string;
	type: string;
	input: unknown;
	ctx: Record<string, unknown>;
};
