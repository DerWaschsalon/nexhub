// Antworten der Hub-API für die Armory (hub/api/nexhub_api/routes/armory.py). Ein Armory-Charakter
// ist eine Momentaufnahme wie ein Mitspieler im Run – Typen und Ansicht kommen aus modules/logs.
import type * as Api from '#lib/api-types.ts';
import type { CharacterData, CharacterListItem, CharacterSnapshot } from '#modules/logs/api.ts';
import type { Ratings } from '#modules/logs/rating.ts';

/** class_name: Klassenname von der Website; Farbe und Symbol über classFromName (modules/logs/classes.ts) */
export type ArmoryItem = Api.ArmoryOut;

export type ArmoryDay = Api.Day;

/** hints: Sprache → Hinweise „das zuerst verbessern“ (ratgeber.py); ratings: Sprache → Bewertung gegen
 * Top-Spieler (rating.py), leer ohne Zählung der Klasse */
export type ArmoryDetail = Omit<Api.ArmoryDetail, 'data' | 'hints' | 'ratings'> & {
	data: CharacterSnapshot | null;
	hints: Record<string, ArmoryHint[]>;
	ratings: Record<string, Ratings>;
};

type HintItem = { slot: string; item: string; icon: string | null; grade: string };
/** Ein Hinweis des Ratgebers; Reihenfolge von schnell erledigt bis teuer */
export type ArmoryHint =
	| (HintItem & { art: 'sockel'; frei: number })
	| (HintItem & { art: 'verzaubern'; stufe: number; werte: string[] })
	| (HintItem & { art: 'stein' | 'nebenwert'; werte: string[] })
	| { art: 'set'; set: string; hat: number; braucht: number };

/** cls: Klasse wie im Hub ("ranger") */
export type ArmoryHit = Api.Hit;

/** Regionen der Global-Server (aion2.py SHARDS) */
export const REGIONS = ['eu', 'nae', 'naw', 'la', 'as'] as const;

/** Ein Charakter, live von der Website geholt (GET /api/armory/live) – wird nicht gespeichert. */
export type ArmoryLive = Omit<Api.Live, 'data'> & { data: CharacterData };

/** Linke Seite eines Vergleichs: ein Armory-Charakter, beim geteilten Link ohne Besitzer */
export type ComparisonLeft = Pick<ArmoryDetail, 'name' | 'cls' | 'class_name' | 'data'>;

/** Geteilter Vergleich (GET /api/public/vergleich/{token}): rechts live, kann fehlen */
export type ArmoryComparison = { left: ComparisonLeft; right: ArmoryLive | null; right_error: string | null };
