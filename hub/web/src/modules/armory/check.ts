// Build-Check (hub/api/nexhub_api/evaluation.py, routes/armory.py): der Charakter gegen die
// Top-Spieler seiner Klasse. Werte der Gruppe stehen auf Englisch, so wie die Website sie liefert.
import type { ComparisonLeft } from './api.ts';

export type Light = 'green' | 'yellow' | 'red';

/** Ein verglichenes Feld: Bereich, Platz (Ausrüstungsplatz, Brett, Skill …) und Feld */
export type CheckField = {
	area: 'profile' | 'stats' | 'equipment' | 'daevanion' | 'skills' | 'titles' | 'wing' | 'pet';
	slot: string;
	key: string;
	kind: 'number' | 'choice';
	mine: number | string;
	median: number | null;
	common: { value: string; count: number }[];
	/** so viele aus der Gruppe haben es besser – zugleich die Priorität */
	better: number;
	light: Light;
};

export type CheckResult = { size: number; fields: CheckField[]; todo: CheckField[] };

export type BuildCheck = {
	status: 'läuft' | 'fertig' | 'fehler';
	progress: number;
	size: number | null;
	error: string | null;
	result: CheckResult | null;
	started_at: string;
	finished_at: string | null;
	share_url: string | null;
};

/** Geteilter Build-Check (GET /api/public/check/{token}) */
export type SharedCheck = ComparisonLeft & { result: CheckResult; finished_at: string | null };

/** Schlechteste Ampel einer Reihe von Feldern (eine Karte je Ausrüstungsplatz) */
export function worst(fields: CheckField[]): Light {
	if (fields.some((f) => f.light === 'red')) return 'red';
	return fields.some((f) => f.light === 'yellow') ? 'yellow' : 'green';
}
