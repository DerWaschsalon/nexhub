// Antwort von GET /api/parses/runs/{id} und /api/public/parses/shared/{token}
// (hub/api/nexhub_api/modules/parses/routes.py).
import { api } from '#lib/api.ts';
import type { RunParses } from '#lib/api-types.ts';

export type { KnownLegion, LegionsOut, Parse, RunParses } from '#lib/api-types.ts';

type Fetch = typeof fetch;

/** Parses eines Runs; null, wenn sie nicht zu haben sind (der Kampf erscheint dann ohne). */
export async function loadParses(path: string, f: Fetch): Promise<RunParses | null> {
	try {
		return await api<RunParses>(path, undefined, f);
	} catch {
		return null;
	}
}

export const LEGIONS_PATH = '/api/parses/legions';
export const runParsesPath = (id: string | number) => `/api/parses/runs/${id}`;
export const sharedParsesPath = (token: string) => `/api/public/parses/shared/${encodeURIComponent(token)}`;

export type ParseColor = 'grey' | 'green' | 'blue' | 'purple' | 'orange' | 'pink' | 'gold';

/** Farbstufen wie bei Warcraft Logs. */
export function parseColor(value: number): ParseColor {
	if (value >= 100) return 'gold';
	if (value >= 99) return 'pink';
	if (value >= 95) return 'orange';
	if (value >= 75) return 'purple';
	if (value >= 50) return 'blue';
	if (value >= 25) return 'green';
	return 'grey';
}
