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
export type BotGuild = {
	id: string;
	name: string;
	icon_url: string | null;
	members: number;
	channels: BotChannel[];
	roles: BotRole[];
};

export type BotFieldKind =
	| 'channel'
	| 'voice'
	| 'role'
	| 'channels'
	| 'roles'
	| 'bool'
	| 'int'
	| 'text'
	| 'textarea'
	| 'choice';

export type BotField = {
	key: string;
	kind: BotFieldKind;
	label: string;
	group: string;
	hint: string;
	min: number | null;
	options: string[];
	value: string | string[] | number | boolean | null;
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
export type Feed = {
	id: number;
	kind: string;
	source: string;
	events: string[];
	channel: string | null;
	enabled: boolean;
	error: string | null;
};
export type Verification = { channel: string | null; role: string | null; panel: boolean; text: string | null };
export type VisibilityMatrix = {
	roles: { id: string; name: string }[];
	rows: { id: string | null; name: string; category: boolean; kind: string | null; cells: boolean[] }[];
};
