// AION-2-Klassen aus nexproto (proto/nexproto/classes.py): Namen, Farben wie im Meter; Symbole in
// hub/web/static/klassen/, Figuren in hub/web/static/klassen/figur/ (für Faustkämpfer gibt es noch keine), dort
// auch die Ebenen einzelner Plätze (hub/tools/figure_layers.py); Herkunft in data/HERKUNFT.md.
import { i18n } from '#lib/i18n.svelte.ts';
import { CLASSES, UNKNOWN_CLASS_COLOR } from '#lib/nexproto.ts';

export type ClassInfo = { label: string; color: string; icon: string; figure: string };

const BY_KEY = new Map(CLASSES.map((c) => [c.key, c]));
const FIGURE_DIR = '/klassen/figur';

/** alle Klassen, z. B. für eine Auswahlliste */
export const CLASS_KEYS = CLASSES.map((c) => c.key);

export function classInfo(cls: string | null | undefined): ClassInfo | null {
	const c = cls ? BY_KEY.get(cls) : undefined;
	if (!c) return null;
	return { label: c[i18n.lang], color: c.color, icon: `/klassen/${cls}.png`, figure: `${FIGURE_DIR}/${cls}.webp` };
}

/** Ebene eines Ausrüstungsplatzes zur Figur der Klasse: nur dieser Platz sichtbar, gleich groß wie die Figur */
export function figureLayer(cls: string, slot: string): string {
	return `${FIGURE_DIR}/${cls}-${slot.toLowerCase()}.webp`;
}

/** Klasse zum Klassennamen, wie die AION-2-Website ihn schreibt (Englisch oder Deutsch). */
export function classFromName(name: string | null | undefined): string | null {
	const n = name?.trim().toLowerCase();
	if (!n) return null;
	return CLASSES.find((c) => c.en.toLowerCase() === n || c.de.toLowerCase() === n)?.key ?? null;
}

export const classColor = (cls: string | null | undefined) => (cls && BY_KEY.get(cls)?.color) || UNKNOWN_CLASS_COLOR;
