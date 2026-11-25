// Antworten der Hub-API für die BiS-Listen (hub/api/nexhub_api/routes/bis.py). Der typische Gegenstand
// je Platz hat das Format eines Armory-Gegenstands, die Anteile das Format der Bewertung (rating.ts).
import type * as Api from '#lib/api-types.ts';
import type { CharacterData, CharacterItem } from '#modules/logs/api.ts';
import type { RatedLine } from '#modules/logs/rating.ts';

/** Eine Klasse mit Bestand (GET /api/bis) */
export type BisClass = Api.ClassOut;

/** Einer der häufigsten Gegenstände eines Platzes */
export type BisItem = { name: string; share: number; icon: string | null; grade: string | null };

export type BisSlot = {
	/** häufigster Gegenstand mit üblicher Verzauberung, Zusatzwerten, Steinen und Skills */
	item: CharacterItem;
	players: number;
	/** Anteil der Top-Spieler, die den Platz belegt haben */
	share: number;
	/** Anteil auf höchster Verzauberung */
	max_enchant: number;
	items: BisItem[];
	lines: RatedLine[];
};

export type BisSkill = CharacterData['skills'][number] & { share: number };

/** Auswertung einer Klasse (GET /api/bis/{cls}); slots leer, solange weniger als min_sample Spieler da sind */
export type BisStats = Omit<Api.BisOut, 'slots' | 'skills'> & { slots: BisSlot[]; skills: BisSkill[] };

/** Modi der Raids bei Abyss Logs; „Hard“ zählt zuerst */
export const TIERS = ['Hard', 'Normal'] as const;
