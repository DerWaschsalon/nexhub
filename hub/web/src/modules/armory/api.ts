// Antworten der Hub-API für die Armory (hub/api/nexhub_api/routes/armory.py). Ein Armory-Charakter
// ist eine Momentaufnahme wie ein Mitspieler im Run – Typen und Ansicht kommen aus modules/logs.
import type { CharacterListItem, CharacterSnapshot } from '#modules/logs/api.ts';

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
	character_id: string;
	image: string | null;
	taken_by: string | null;
};

/** Regionen der Global-Server (aion2.py SHARDS) */
export const REGIONS = ['eu', 'nae', 'naw', 'la', 'as'] as const;
