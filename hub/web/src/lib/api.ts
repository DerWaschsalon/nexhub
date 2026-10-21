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

/** JSON senden (PUT/POST/DELETE) und die Antwort zurückgeben. */
export function send<T>(path: string, method: string, body?: unknown): Promise<T> {
	return api<T>(path, {
		method,
		headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});
}
