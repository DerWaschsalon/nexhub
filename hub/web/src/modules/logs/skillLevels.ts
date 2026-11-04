// Echte Skill-Stufe = Stufe aus der Skill-Liste + Boni aus Daevanion („Orkanpfeil +1“ je Brett)
// + verstärkte Skills auf der Ausrüstung (Schmuck, Arkana). Die Website rechnet das nicht zusammen,
// ohne die Boni zeigt die Liste bis zu 10 Stufen zu wenig. Zuordnung über den Namen, weil die Boni
// keine Skill-IDs tragen. Stigmen bekommen keine Boni (Endpunkt-Doku von doarjo/aion2-tracker).
import type { CharacterData } from './api.ts';

export type SkillBonus = { daevanion: number; items: number };

const LINE = /^(.+?)\s*\+(\d+)$/;

function add(map: Map<string, SkillBonus>, name: string, key: keyof SkillBonus, n: number) {
	const bonus = map.get(name) ?? { daevanion: 0, items: 0 };
	bonus[key] += n;
	map.set(name, bonus);
}

/** Boni je Skill-Name; Skills ohne Bonus fehlen. */
export function skillBonuses(data: CharacterData): Map<string, SkillBonus> {
	const bonuses = new Map<string, SkillBonus>();
	for (const board of data.daevanion) {
		for (const line of board.skills) {
			const m = LINE.exec(line);
			if (m) add(bonuses, m[1], 'daevanion', Number(m[2]));
		}
	}
	for (const item of data.equipment) {
		for (const s of item.detail?.skills ?? []) add(bonuses, s.name, 'items', s.level);
	}
	return bonuses;
}
