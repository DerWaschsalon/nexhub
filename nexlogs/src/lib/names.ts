// Namen und Symbole aus den Spieldaten (A2Tools, siehe data/HERKUNFT.md), je Sprache erst bei
// Bedarf geladen: die Tabellen sind zusammen gut 1 MB groß.
import { useEffect, useState } from 'react';
import type { Lang } from './i18n.tsx';

type Table = Record<string, string>;
const BASE = 'https://assets.playnccdn.com/static-aion2-gamedata/resources';

const skillTables: Record<Lang, () => Promise<{ default: Table }>> = {
	en: () => import('../data/skills/en.json'),
	de: () => import('../data/skills/de.json')
};
const buffTables: Record<Lang, () => Promise<{ default: Table }>> = {
	en: () => import('../data/buffs/en.json'),
	de: () => import('../data/buffs/de.json')
};

export type GameNames = {
	/** Name zum Skill-Code; ohne Eintrag der Name aus der Kampfdatei, sonst „[Code]“. */
	skill: (code: number | null, fallback?: string) => string;
	buff: (id: number) => string;
	buffIcon: (id: number) => string | null;
};

let icons: Table | null = null;

export function useGameNames(lang: Lang): GameNames {
	const [tables, setTables] = useState<{ skills: Table; buffs: Table; icons: Table } | null>(null);
	useEffect(() => {
		let live = true;
		Promise.all([
			skillTables[lang](),
			buffTables[lang](),
			icons ? Promise.resolve({ default: icons }) : import('../data/buffs/icons.json')
		]).then(([s, b, i]) => {
			icons = i.default as Table;
			if (live) setTables({ skills: s.default, buffs: b.default, icons });
		});
		return () => {
			live = false;
		};
	}, [lang]);

	return {
		skill: (code, fallback) => {
			if (code == null) return fallback ?? '?';
			const key = String(code);
			// Varianten (z. B. 14100150) haben oft keinen eigenen Eintrag, die Grundfähigkeit schon
			const named = tables?.skills[key] ?? tables?.skills[key.slice(0, 4).padEnd(key.length, '0')];
			return named ?? fallback ?? `[${code}]`;
		},
		buff: (id) => tables?.buffs[String(id)] ?? `[${id}]`,
		buffIcon: (id) => {
			const icon = tables?.icons[String(id)];
			return icon ? `${BASE}/${icon}.png` : null;
		}
	};
}
