import { defineTexts } from '#lib/i18n.svelte.ts';

export const TEXTS = defineTexts(
	{
		'parses.eu': 'EU',
		'parses.guild': 'Guild',
		'parses.eu.tip': 'EU: better than {pct}% of {n} {cls} on Abyss Logs (as of {date})',
		'parses.eu.loading': 'EU: loading the Abyss Logs ranking',
		'parses.eu.none': 'EU: no ranking on Abyss Logs for this boss',
		'parses.eu.noClass': 'EU: class unknown',
		'parses.guild.tip': 'Guild: better than {pct}% of {n} characters',
		'parses.guild.few': 'Guild: too little data ({n} of {min} characters)'
	},
	{
		'parses.eu': 'EU',
		'parses.guild': 'Gilde',
		'parses.eu.tip': 'EU: besser als {pct} % von {n} {cls} auf Abyss Logs (Stand {date})',
		'parses.eu.loading': 'EU: Rangliste von Abyss Logs wird geladen',
		'parses.eu.none': 'EU: keine Rangliste bei Abyss Logs für diesen Boss',
		'parses.eu.noClass': 'EU: Klasse unbekannt',
		'parses.guild.tip': 'Gilde: besser als {pct} % von {n} Charakteren',
		'parses.guild.few': 'Gilde: zu wenig Daten ({n} von {min} Charakteren)'
	}
);
