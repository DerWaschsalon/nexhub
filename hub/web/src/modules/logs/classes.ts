// AION-2-Klassen: Namen auf Englisch und Deutsch, Farben und Symbole wie im Meter (A2Tools-DPS-Meter,
// public/src/js/core.js jobColorMap; Symbole in hub/web/static/klassen/, Herkunft in data/HERKUNFT.md).
import { i18n } from '#lib/i18n.svelte.ts';

export type ClassInfo = { label: string; color: string; icon: string };

const CLASSES: Record<string, { en: string; de: string; color: string }> = {
	gladiator: { en: 'Gladiator', de: 'Gladiator', color: '#4FD1C5' },
	templar: { en: 'Templar', de: 'Templer', color: '#5F8CFF' },
	assassin: { en: 'Assassin', de: 'Assassine', color: '#7BE35A' },
	ranger: { en: 'Ranger', de: 'Waldläufer', color: '#41D98A' },
	sorcerer: { en: 'Sorcerer', de: 'Magier', color: '#9A6BFF' },
	spiritmaster: { en: 'Spiritmaster', de: 'Beschwörer', color: '#E06BFF' },
	cleric: { en: 'Cleric', de: 'Kleriker', color: '#F2C15A' },
	chanter: { en: 'Chanter', de: 'Kantor', color: '#FF9A3D' },
	brawler: { en: 'Brawler', de: 'Faustkämpfer', color: '#E85D5D' }
};

/** alle Klassen, z. B. für eine Auswahlliste */
export const CLASS_KEYS = Object.keys(CLASSES);

const UNKNOWN = '#8a90a3';

export function classInfo(cls: string | null | undefined): ClassInfo | null {
	const c = cls ? CLASSES[cls] : undefined;
	return c ? { label: c[i18n.lang], color: c.color, icon: `/klassen/${cls}.png` } : null;
}

/** Klasse zum Klassennamen, wie die AION-2-Website ihn schreibt (Englisch oder Deutsch). */
export function classFromName(name: string | null | undefined): string | null {
	const n = name?.trim().toLowerCase();
	if (!n) return null;
	return Object.keys(CLASSES).find((k) => CLASSES[k].en.toLowerCase() === n || CLASSES[k].de.toLowerCase() === n) ?? null;
}

export const classColor = (cls: string | null | undefined) => (cls && CLASSES[cls]?.color) || UNKNOWN;
