import { defineTexts } from '#lib/i18n.svelte.ts';

export const TEXTS = defineTexts(
	{
		'loot.nav': 'Loot',
		'loot.title': 'Loot',
		'loot.intro':
			'What bosses dropped for the group to roll on, counted from uploaded runs. Only gear the group rolls for is seen, not personal drops.',
		'loot.none': 'No run with loot has been uploaded yet. NexBoards record it from this version on.',
		'loot.runs': 'runs: {n}',
		'loot.kills': 'kills: {n}',
		'loot.col.item': 'Item',
		'loot.col.drops': 'Dropped',
		'loot.col.rate': 'Rate',
		'loot.col.band': 'Likely',
		'loot.item': 'Item #{id}',
		'loot.oneIn': '1 in {n}',
		'loot.band': '1 in {low} – {high}',
		'loot.tooFew': 'too little data (under {n} kills)',
		'loot.noDrops': 'Nothing rolled for yet.'
	},
	{
		'loot.nav': 'Beute',
		'loot.title': 'Beute',
		'loot.intro':
			'Worum die Gruppe nach einem Boss gewürfelt hat, gezählt aus den hochgeladenen Runs. Erfasst ist nur Würfel-Beute, keine persönlichen Drops.',
		'loot.none': 'Es gibt noch keinen Run mit Beute. NexBoards schreiben sie ab dieser Version mit.',
		'loot.runs': 'Runs: {n}',
		'loot.kills': 'Siege: {n}',
		'loot.col.item': 'Gegenstand',
		'loot.col.drops': 'Gefallen',
		'loot.col.rate': 'Rate',
		'loot.col.band': 'Wahrscheinlich',
		'loot.item': 'Gegenstand #{id}',
		'loot.oneIn': '1 zu {n}',
		'loot.band': '1 zu {low} – {high}',
		'loot.tooFew': 'zu wenig Daten (unter {n} Siege)',
		'loot.noDrops': 'Noch nichts gewürfelt.'
	}
);
