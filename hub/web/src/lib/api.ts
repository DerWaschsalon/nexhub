// Zugriff auf die Hub-API. Cookies gehen automatisch mit, die Seite läuft auf derselben Adresse.
import { error } from '@sveltejs/kit';

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

type Fetch = typeof fetch;

/** JSON von der API holen; wirft ApiError mit der deutschen Meldung der API. */
export async function api<T>(path: string, init?: RequestInit, f: Fetch = fetch): Promise<T> {
	const r = await f(path, init);
	if (!r.ok) {
		const body = await r.json().catch(() => null);
		throw new ApiError(r.status, body?.detail ?? `Fehler ${r.status}`);
	}
	return (r.status === 204 ? undefined : await r.json()) as T;
}

export const post = (path: string) => api<void>(path, { method: 'POST' });

/** Für load-Funktionen: Fehler der API werden zu einer Fehlerseite mit Status und Meldung
 *  (sonst zeigt SvelteKit nur „500 Internal Error“). */
export async function apiLoad<T>(path: string, f: Fetch): Promise<T> {
	try {
		return await api<T>(path, undefined, f);
	} catch (e) {
		if (e instanceof ApiError) error(e.status, e.message);
		throw e;
	}
}

/** Wie api(), aber 401 heißt „nicht angemeldet“ statt Fehler. */
export async function loadMe(f: Fetch = fetch): Promise<Me | null> {
	try {
		return await api<Me>('/api/me', undefined, f);
	} catch (e) {
		if (e instanceof ApiError && e.status === 401) return null;
		throw e;
	}
}

// Antworten der API (Pydantic-Modelle in hub/api/nexhub_api/routes/)

export type Role = 'admin' | 'member';

export type Me = { discord_id: string; name: string; avatar_url: string | null; role: Role };

export type PublicInfo = { login: boolean };

export type Account = {
	id: number;
	discord_id: string;
	name: string;
	avatar_url: string | null;
	role: Role;
	created_at: string;
	last_login_at: string;
	blocked: boolean;
	sessions: number;
};

export type Status = {
	version: string;
	db_revision: string;
	login: boolean;
	member_check: boolean;
	accounts: number;
	active_sessions: number;
};

export type Device = {
	id: number;
	name: string;
	created_at: string;
	last_seen_at: string | null;
	version: string | null;
};

export type RunPlayer = { name: string; cls: string | null; damage: number; dps: number };

export type RunSummary = {
	fight_ms: number;
	players: RunPlayer[];
	bosses: {
		fight: string;
		name: string;
		mob: number;
		start_ms: number;
		duration_ms: number;
		killed: boolean;
		players: RunPlayer[];
	}[];
};

/** Was jede Run-Ansicht braucht – im Hub und auf einer geteilten Seite. */
export type RunCore = {
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
	summary: RunSummary;
};

export type Run = {
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

export type RunDetail = Run & RunCore & { size: number; can_delete: boolean; share_url: string | null };

export type FightSkill = {
	code: number;
	name: string;
	dot: boolean;
	damage: number;
	share: number;
	hits: number;
	crit: number;
	back: number;
	perfect: number;
	double: number;
};

export type FightDetail = {
	fight: string;
	name: string;
	duration_ms: number;
	killed: boolean;
	max_hp: number;
	run_players: string[];
	players: (RunPlayer & { actor: number; skills: FightSkill[] })[];
	timeline: { bucket_ms: number; players: { actor: number; damage: number[] }[] } | null;
	deaths: { name: string; t_ms: number; revived_ms: number | null }[];
};

export const ROLE_LABEL: Record<Role, string> = { admin: 'Admin', member: 'Mitglied' };
