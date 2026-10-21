// Typen und Adresse der Steuer-API von TheWashBot (bot/bot/cogs/control.py), über den Hub unter
// /api/admin/bot (hub/api/nexhub_api/routes/bot.py).
// Discord-IDs sind Strings: als Zahl verlöre JavaScript die letzten Stellen.

export const BOT_API = '/api/admin/bot';

export type BotStatus = {
	ready: boolean;
	name: string | null;
	avatar_url: string | null;
	guild: { id: string; name: string; members: number; icon_url: string | null } | null;
	guilds: number;
	latency_ms: number | null;
	uptime_s: number;
	version: string;
	cogs: string[];
};

export type BotChannel = { id: string; name: string; kind: 'text' | 'voice' | 'category'; category: string | null };
export type BotRole = { id: string; name: string; color: string | null; assignable: boolean };
export type BotPerson = { id: string; name: string; tag: string };
export type BotGuild = {
	id: string;
	name: string;
	icon_url: string | null;
	members: number;
	channels: BotChannel[];
	roles: BotRole[];
	/** Mitglieder ohne Bots, für Felder vom Typ „member“ */
	people: BotPerson[];
};

export type BotFieldKind =
	| 'channel'
	| 'voice'
	| 'role'
	| 'member'
	| 'channels'
	| 'roles'
	| 'multi'
	| 'bool'
	| 'int'
	| 'text'
	| 'textarea'
	| 'choice';

export type BotValue = string | string[] | number | boolean | null;

export type BotField = {
	key: string;
	kind: BotFieldKind;
	label: string;
	group: string;
	hint: string;
	min: number | null;
	max: number | null;
	required: boolean;
	options: { value: string; label: string }[];
	/** Nur sichtbar, wenn das Feld `key` einen der Werte hat */
	show_if: { key: string; values: string[] } | null;
	value: BotValue;
};

export type BotSection = {
	id: string;
	title: string;
	description: string;
	note: string;
	fields: BotField[];
	info: { label: string; value: string | null; code?: boolean; secret?: boolean }[];
	actions: { id: string; label: string }[];
};

export type LevelReward = { level: number; role_id: string; role: string | null };
export type Announcement = {
	id: number;
	channel_id: string;
	channel: string | null;
	text: string;
	interval_minutes: number;
	next_run: number;
};
export type CustomCommand = { name: string; response: string };
export type Verification = { channel: string | null; role: string | null; panel: boolean; text: string | null };
export type VisibilityMatrix = {
	roles: { id: string; name: string }[];
	rows: { id: string | null; name: string; category: boolean; kind: string | null; cells: boolean[] }[];
};

// ---- Seiten (bot/bot/hubpages.py): Menü und Inhalt kommen vom Bot ------------------------------

export type BotNavItem = { id: string; title: string; group: string; order: number; custom: boolean };

export type BotAction = {
	id: string;
	label: string;
	/** Beschriftung des Absende-Knopfs */
	submit: string;
	confirm: string;
	danger: boolean;
	/** Nur für Zeilen bzw. Zustände, bei denen dieser Schlüssel wahr ist */
	when: string;
	fields: BotField[];
};

export type BotRow = Record<string, unknown> & { id: string };

export type BotBlock =
	| { type: 'form'; id: string; section: BotSection }
	| {
			type: 'table';
			id: string;
			title: string;
			description: string;
			columns: { key: string; label: string; kind: 'text' | 'num' | 'time' | 'date' | 'badge' | 'link' }[];
			rows: BotRow[];
			create: BotAction | null;
			actions: BotAction[];
			empty: string;
	  }
	| {
			type: 'status';
			id: string;
			title: string;
			description: string;
			items: { label: string; value: string; href?: string | null }[];
			flags: Record<string, unknown>;
			actions: BotAction[];
	  }
	| { type: 'actions'; id: string; title: string; description: string; actions: BotAction[] };

export type BotPage = BotNavItem & { description: string; blocks: BotBlock[] };
export type BotActionResult = { message: string; page: BotPage };
