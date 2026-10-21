// Namen und Symbole von Fähigkeiten und Buffs aus den Spieldaten (A2Tools, siehe data/HERKUNFT.md)
// in der gewählten Sprache. Die Tabellen sind zusammen gut 1 MB groß und werden erst beim ersten
// Aufruf je Sprache geladen; bis dahin gilt der Name aus der Kampfdatei.
import { i18n, type Lang } from '#lib/i18n.svelte.ts';

type Table = Record<string, string>;
const BASE = 'https://assets.playnccdn.com/static-aion2-gamedata/resources';

const skillTables: Record<Lang, () => Promise<{ default: Table }>> = {
	en: () => import('./data/skills/en.json'),
	de: () => import('./data/skills/de.json')
};
const buffTables: Record<Lang, () => Promise<{ default: Table }>> = {
	en: () => import('./data/buffs/en.json'),
	de: () => import('./data/buffs/de.json')
};

// $state.raw: die Tabellen werden nur ersetzt, nie verändert – kein tiefer Proxy über 9000 Einträge
let loaded = $state.raw<Partial<Record<Lang, { skills: Table; buffs: Table }>>>({});
let icons = $state.raw<Table | null>(null);
const pending = new Set<string>();

function tables() {
	const lang = i18n.lang;
	if (!loaded[lang] && !pending.has(lang)) {
		pending.add(lang);
		Promise.all([skillTables[lang](), buffTables[lang]()]).then(([s, b]) => {
			loaded = { ...loaded, [lang]: { skills: s.default, buffs: b.default } };
		});
	}
	return loaded[lang];
}

/** Name zum Skill-Code; ohne Eintrag der Name aus der Kampfdatei, sonst „[Code]“. */
export function skillName(code: number | null, fallback?: string): string {
	if (code == null) return fallback ?? '?';
	const key = String(code);
	const skills = tables()?.skills;
	// Varianten (z. B. 14100150) haben oft keinen eigenen Eintrag, die Grundfähigkeit schon
	return skills?.[key] ?? skills?.[key.slice(0, 4).padEnd(key.length, '0')] ?? fallback ?? `[${code}]`;
}

export function buffName(id: number): string {
	return tables()?.buffs[String(id)] ?? `[${id}]`;
}

export function buffIcon(id: number): string | null {
	if (!icons && !pending.has('icons')) {
		pending.add('icons');
		import('./data/buffs/icons.json').then((m) => (icons = m.default as Table));
	}
	const icon = icons?.[String(id)];
	return icon ? `${BASE}/${icon}.png` : null;
}
