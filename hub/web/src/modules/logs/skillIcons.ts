// Skill-Symbole vom CDN des Spiels, Zuordnung wie im Meter (A2Tools-DPS-Meter,
// public/src/js/skillIcons.js, GPL-3.0): erst die Tabelle aus den Spieldaten (erste vier Ziffern des
// achtstelligen Codes), sonst aus Klasse und Nummer. Das CDN erlaubt kein fetch von fremden Seiten,
// ein einfaches <img> lädt aber.
import { GAMEDATA as BASE } from './assets.ts';
import iconMap from './data/skill_icons.json';

const MAP = iconMap as Record<string, string>;

const CLASS_BY_PREFIX: Record<string, string> = {
	'11': 'GL',
	'12': 'TE',
	'13': 'AS',
	'14': 'RA',
	'15': 'SO',
	'16': 'EL',
	'17': 'CL',
	'18': 'CH',
	'19': 'GT'
};

/** 'auto' für Standardangriffe (eigenes Symbol), sonst die Bild-Adresse oder null. */
export function skillIcon(rawCode: number | null | undefined): string | 'auto' | null {
	const digits = String(rawCode ?? '').replace(/\D/g, '');
	if (!digits) return null;
	const code = digits.length >= 8 ? digits.slice(0, 8) : digits.padEnd(8, '0');
	const prefix = code.slice(0, 2);

	// Gottstein (Theostone): eigener Bildname aus Stelle 6–7
	if (prefix === '30') {
		const n = Number(code.slice(5, 7));
		return n > 0 ? `${BASE}/Icon_Item_Usable_Godstone_WP_r_${n.toString(16).padStart(3, '0')}.png` : null;
	}
	// Standardangriffe: xx0000xx je Klasse, 1000xxxx Beschwörer, 1699xxxx Geister
	if ((prefix >= '11' && prefix <= '18' && code.slice(2, 6) === '0000' && code.slice(6) !== '00') ||
		code.startsWith('1000') || code.startsWith('1699')) {
		return 'auto';
	}
	const named = MAP[code.slice(0, 4)];
	if (named) return `${BASE}/${named}.png`;
	const cls = CLASS_BY_PREFIX[prefix];
	const sub = Number(code.slice(2, 4));
	return cls && Number.isFinite(sub) ? `${BASE}/ICON_${cls}_SKILL_${String(sub).padStart(3, '0')}.png` : null;
}
