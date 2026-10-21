// Zugriff auf die Hub-API. Cookies gehen automatisch mit, die Seite läuft auf derselben Adresse.

export type Me = {
	discord_id: string;
	username: string;
	display_name: string | null;
	avatar_url: string | null;
	role: 'admin' | 'member';
};

export type Health = { ok: boolean; login: boolean };

type Fetch = typeof fetch;

export async function loadMe(f: Fetch = fetch): Promise<Me | null> {
	const r = await f('/api/me');
	if (r.status === 401) return null;
	if (!r.ok) throw new Error(`/api/me: HTTP ${r.status}`);
	return r.json();
}

export async function loadHealth(f: Fetch = fetch): Promise<Health> {
	const r = await f('/api/health');
	if (!r.ok) return { ok: false, login: false };
	return r.json();
}

export async function logout(): Promise<void> {
	await fetch('/api/auth/logout', { method: 'POST' });
}

export const ROLE_LABEL: Record<Me['role'], string> = { admin: 'Admin', member: 'Mitglied' };
