// Charakterwerte der offiziellen Seite: Reihenfolge, Symbole und das Zusammenzählen der Effekte.
// Eine Stelle für StatPanel (Kacheln) und StatWheel (Kreis).
import type { CharacterData } from './api.ts';
import { CHARACTER_ART } from './assets.ts';

type Stat = CharacterData['stats'][number];

/** Sechs Grundwerte und zehn Lord-Werte in der Reihenfolge der offiziellen Seite */
export const BASE = ['STR', 'DEX', 'AGI', 'WIS', 'INT', 'CON'];
export const LORDS = ['Destruction', 'Death', 'Wisdom', 'Destiny', 'Space', 'Time', 'Life', 'Illusion', 'Freedom', 'Justice'];

/** Symbol eines Werts (stat_<typ>.png, stat_lords_<typ>.png) */
export function statIcon(type: string): string {
	const lord = LORDS.includes(type) ? 'lords_' : '';
	return `${CHARACTER_ART}/info/stat_${lord}${type.toLowerCase()}.png`;
}

/** „Zeit [Siel]“ → Name und Lord getrennt */
export function splitLord(name: string): { name: string; lord: string } {
	const m = name.match(/^(.*?)\s*\[(.+)\]$/);
	return m ? { name: m[1], lord: m[2] } : { name, lord: '' };
}

/** Werte der gewünschten Typen in deren Reihenfolge; fehlende fallen weg */
export function pickStats(stats: Stat[], types: string[]): Stat[] {
	const byType = new Map(stats.map((s) => [s.type, s]));
	return types.map((type) => byType.get(type)).filter((s) => s !== undefined);
}

export type StatTotal = { name: string; value: number; unit: string };

// „Angriffskraft + +3.6%“ (so schickt NC es) oder „Attack Increase +5.9%“ → Name, Zahl, Einheit
const EFFECT = /^(.*?)[\s+]*(-?\d+(?:\.\d+)?)(%?)$/;

/** Gleichnamige Effekte aller Werte zusammengezählt, in der Reihenfolge ihres ersten Auftretens.
 *  Zeilen ohne Zahl am Ende (reiner Text) zählen nicht mit. */
export function sumEffects(stats: Stat[]): StatTotal[] {
	const totals = new Map<string, StatTotal>();
	for (const line of stats.flatMap((s) => s.effects)) {
		const m = line.trim().match(EFFECT);
		if (!m) continue;
		const key = `${m[1]}|${m[3]}`;
		const total = totals.get(key) ?? { name: m[1], value: 0, unit: m[3] };
		total.value += Number(m[2]);
		totals.set(key, total);
	}
	return [...totals.values()];
}

/** „+5.9%“; auf eine Nachkommastelle gerundet, damit 0.1-Schritte nicht als 5.8999 auftauchen */
export function formatTotal(t: StatTotal): string {
	const rounded = Math.round(t.value * 10) / 10;
	return `${rounded >= 0 ? '+' : ''}${rounded}${t.unit}`;
}

/** Werte-Kreis wie im Spiel, Fläche 610 × 412: Lage der Zahl jedes Werts (Symbol und Name darüber).
 *  Außen die Lord-Werte im Uhrzeigersinn ab oben links, innen die Grundwerte ab oben. */
export const WHEEL = { width: 610, height: 412, innerRadius: 88, outerRadius: 140 };
export const WHEEL_LORDS: [string, number, number][] = [
	['Justice', 208, 91],
	['Destruction', 401, 91],
	['Death', 478, 162],
	['Wisdom', 502, 249],
	['Destiny', 449, 331],
	['Space', 372, 381],
	['Time', 238, 381],
	['Life', 161, 331],
	['Illusion', 108, 249],
	['Freedom', 132, 162]
];
export const WHEEL_BASE: [string, number, number][] = [
	['STR', 305, 150],
	['DEX', 381, 195],
	['AGI', 381, 278],
	['WIS', 305, 320],
	['INT', 228, 278],
	['CON', 228, 195]
];
/** Speichen zwischen den Lord-Werten, in Grad (0 = rechts, im Uhrzeigersinn) */
export const WHEEL_SPOKES = [-90, -55, -15, 15, 55, 90, 125, 165, 195, 235];

