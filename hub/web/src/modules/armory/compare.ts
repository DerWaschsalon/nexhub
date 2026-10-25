// Die beiden Seiten eines Vergleichs für CompareView: links ein Charakter aus der Armory, rechts einer
// live von der Website. Gebraucht im Hub (hub/armory/vergleich) und beim geteilten Link ((public)/v).
import type { CharacterData } from '#modules/logs/api.ts';
import { localized } from '#modules/logs/api.ts';
import { classFromName } from '#modules/logs/classes.ts';
import type { ArmoryLive, ComparisonLeft } from './api.ts';

export type CompareSide = { name: string; cls: string | null; data: CharacterData };

/** Armory-Charakter in der Sprache der Seite; ohne Momentaufnahme (noch nie abgerufen) nichts */
export function armorySide(c: ComparisonLeft, lang: string): CompareSide | null {
	if (!c.data) return null;
	return { name: c.name, cls: c.cls ?? classFromName(c.class_name), data: localized(c.data, lang) };
}

/** Live geholter Charakter; die Website schreibt nur den Klassennamen aus */
export function liveSide(c: ArmoryLive): CompareSide {
	return { name: c.name, cls: classFromName(c.data.profile.class), data: c.data };
}
