// AION-2-Klassen: Farben und deutsche Namen wie in der NexBoard-Oberfläche (web/js/core.js).
export const CLASS_COLORS: Record<string, string> = {
	gladiator: '#E8A33D',
	templar: '#5B8DEF',
	ranger: '#6CCB5F',
	assassin: '#B46AE6',
	sorcerer: '#4FC3F7',
	cleric: '#F4E07A',
	spiritmaster: '#EC7FB8',
	chanter: '#4DD4B0'
};

export const CLASS_LABELS: Record<string, string> = {
	gladiator: 'Gladiator',
	templar: 'Templer',
	assassin: 'Assassine',
	ranger: 'Waldläufer',
	sorcerer: 'Magier',
	cleric: 'Kleriker',
	spiritmaster: 'Beschwörer',
	chanter: 'Kantor'
};

export const classColor = (cls: string | null) => (cls && CLASS_COLORS[cls]) || '#9aa3b2';
