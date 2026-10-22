// Antworten der Hub-API für die Armory (hub/api/nexhub_api/routes/armory.py). Ein Armory-Charakter
// ist eine Momentaufnahme wie ein Mitspieler im Run – Typen und Ansicht kommen aus modules/logs.
import type { CharacterData, CharacterListItem, CharacterSnapshot } from '#modules/logs/api.ts';

export type ArmoryItem = CharacterListItem & {
	owner: string;
	mine: boolean;
	/** Klassenname von der Website; Farbe und Symbol über classFromName (modules/logs/classes.ts) */
	class_name: string | null;
	server: string | null;
	image: string | null;
};

export type ArmoryDay = { day: string; combat_power: number | null; item_level: number | null };

export type ArmoryDetail = ArmoryItem & {
	data: CharacterSnapshot | null;
	error: string | null;
	days: ArmoryDay[];
	can_delete: boolean;
};

export type ArmoryHit = {
	name: string;
	server_id: number;
	server: string | null;
	level: number | null;
	/** Klasse wie im Hub ("ranger") */
	cls: string | null;
	character_id: string;
	image: string | null;
	taken_by: string | null;
};

/** Regionen der Global-Server (aion2.py SHARDS) */
export const REGIONS = ['eu', 'nae', 'naw', 'la', 'as'] as const;

/** Ein Charakter, live von der Website geholt (GET /api/armory/live) – wird nicht gespeichert. */
export type ArmoryLive = { name: string; server_id: number; data: CharacterData };

/** Linke Seite eines Vergleichs: ein Armory-Charakter, beim geteilten Link ohne Besitzer */
export type ComparisonLeft = Pick<ArmoryDetail, 'name' | 'cls' | 'class_name' | 'data'>;

/** Geteilter Vergleich (GET /api/public/vergleich/{token}): rechts live, kann fehlen */
export type ArmoryComparison = { left: ComparisonLeft; right: ArmoryLive | null; right_error: string | null };
