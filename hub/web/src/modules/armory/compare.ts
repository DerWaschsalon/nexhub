// Die beiden Seiten eines Vergleichs für CompareView: links ein Charakter aus der Armory, rechts einer
// live von der Website. Gebraucht im Hub (hub/armory/vergleich) und beim geteilten Link ((public)/v).
import type { CharacterData, CharacterItem } from '#modules/logs/api.ts';
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

/** Teile eines Gegenstands im Vergleich, in der Reihenfolge des Gegenstandsfensters */
export const ITEM_PARTS = ['main', 'sub', 'stones', 'skills', 'set'] as const;
export type ItemPart = (typeof ITEM_PARTS)[number];

/** Eine Zeile im Vergleich zweier Gegenstände; null = hat der Gegenstand nicht */
export type ItemRow = { name: string; a: number | null; b: number | null; unit: string };

type Line = { name: string; value: number; unit: string };

const NUMBER = /-?\d+(?:\.\d+)?/;

/** Erste Zahl in einem Wert von NC („12.3%“ → 12.3, „+10“ → 10); ohne Zahl 0 */
function numberIn(text: string | null | undefined): number {
	const found = NUMBER.exec(text ?? '');
	return found ? Number(found[0]) : 0;
}

/** Die Zeilen eines Teils als Name, Zahl, Einheit. Grundwerte samt Bonus aus der Verzauberung
 *  („431(+146)“ zählt als 577), Skills mit Stufe, Set mit angelegten Teilen. Werte aus dem Durchbruch
 *  schickt NC nicht (nur die Stufe am Gegenstand). */
function linesOf(item: CharacterItem | undefined, part: ItemPart): Line[] {
	const d = item?.detail;
	if (!d) return [];
	const unit = (value: string) => (value.includes('%') ? '%' : '');
	switch (part) {
		case 'main':
			return d.main.map((s) => ({ name: s.name, value: numberIn(s.value) + numberIn(s.extra), unit: unit(s.value) }));
		case 'sub':
		case 'stones':
			return d[part].map((s) => ({ name: s.name, value: numberIn(s.value), unit: unit(s.value) }));
		case 'skills':
			return d.skills.map((s) => ({ name: s.name, value: s.level, unit: '' }));
		case 'set':
			return d.set ? [{ name: d.set.name, value: d.set.equipped, unit: '' }] : [];
	}
}

/** Gleichnamige Zeilen zusammengezählt (zweimal Manastein Angriff +10 = 20) */
function summed(lines: Line[]): Map<string, Line> {
	const out = new Map<string, Line>();
	for (const line of lines) {
		const known = out.get(line.name);
		out.set(line.name, known ? { ...known, value: known.value + line.value } : { ...line });
	}
	return out;
}

/** Zwei Gegenstände desselben Platzes, Teil für Teil: erst die Zeilen des linken, dann die nur rechts */
export function compareItems(a: CharacterItem | undefined, b: CharacterItem | undefined): [ItemPart, ItemRow[]][] {
	const parts: [ItemPart, ItemRow[]][] = [];
	for (const part of ITEM_PARTS) {
		const left = summed(linesOf(a, part));
		const right = summed(linesOf(b, part));
		const names = [...new Set([...left.keys(), ...right.keys()])];
		const rows = names.map((name) => ({
			name,
			a: left.get(name)?.value ?? null,
			b: right.get(name)?.value ?? null,
			unit: left.get(name)?.unit || right.get(name)?.unit || ''
		}));
		if (rows.length) parts.push([part, rows]);
	}
	return parts;
}
