// AION-2-Klassen aus nexproto (proto/nexproto/classes.py): Namen, Farben wie im Meter; Symbole in
// hub/web/static/klassen/, Herkunft in data/HERKUNFT.md.
import { i18n } from '#lib/i18n.svelte.ts';
import { CLASSES, UNKNOWN_CLASS_COLOR } from '#lib/nexproto.ts';

export type ClassInfo = { label: string; color: string; icon: string };

const BY_KEY = new Map(CLASSES.map((c) => [c.key, c]));

/** alle Klassen, z. B. für eine Auswahlliste */
export const CLASS_KEYS = CLASSES.map((c) => c.key);

export function classInfo(cls: string | null | undefined): ClassInfo | null {
	const c = cls ? BY_KEY.get(cls) : undefined;
	return c ? { label: c[i18n.lang], color: c.color, icon: `/klassen/${cls}.png` } : null;
}

/** Klasse zum Klassennamen, wie die AION-2-Website ihn schreibt (Englisch oder Deutsch). */
export function classFromName(name: string | null | undefined): string | null {
	const n = name?.trim().toLowerCase();
	if (!n) return null;
	return CLASSES.find((c) => c.en.toLowerCase() === n || c.de.toLowerCase() === n)?.key ?? null;
}

export const classColor = (cls: string | null | undefined) => (cls && BY_KEY.get(cls)?.color) || UNKNOWN_CLASS_COLOR;
