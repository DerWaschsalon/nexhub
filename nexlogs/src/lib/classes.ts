// AION-2-Klassen: deutsche Namen wie im NexHub (hub/web/src/lib/classes.ts), Farben und Symbole wie
// im Meter (A2Tools-DPS-Meter, public/src/js/core.js jobColorMap; Symbole in public/klassen/).

export type ClassInfo = { label: string; color: string; icon: string };

const CLASSES: Record<string, { label: string; color: string }> = {
	gladiator: { label: 'Gladiator', color: '#4FD1C5' },
	templar: { label: 'Templer', color: '#5F8CFF' },
	assassin: { label: 'Assassine', color: '#7BE35A' },
	ranger: { label: 'Waldläufer', color: '#41D98A' },
	sorcerer: { label: 'Magier', color: '#9A6BFF' },
	spiritmaster: { label: 'Beschwörer', color: '#E06BFF' },
	cleric: { label: 'Kleriker', color: '#F2C15A' },
	chanter: { label: 'Kantor', color: '#FF9A3D' },
	brawler: { label: 'Faustkämpfer', color: '#E85D5D' }
};

const UNKNOWN = '#8a90a3';

export function classInfo(cls: string | null | undefined): ClassInfo | null {
	const c = cls ? CLASSES[cls] : undefined;
	return c ? { ...c, icon: `${import.meta.env.BASE_URL}klassen/${cls}.png` } : null;
}

export const classColor = (cls: string | null | undefined) => (cls && CLASSES[cls]?.color) || UNKNOWN;
