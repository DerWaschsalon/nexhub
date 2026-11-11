import { defineTexts } from '#lib/i18n.svelte.ts';

export const TEXTS = defineTexts(
	{
		'bis.nav': 'BiS lists',
		'bis.title': 'BiS lists',
		'bis.intro':
			'What the top players of each class from the Abyss Logs rankings wear, collected a few at a time throughout the day. Click a slot for all values with their share.',
		'bis.none': 'No class has been collected yet. The hub fetches a few players every 5 minutes.',
		'bis.notEnough': 'Only {n} players collected so far, percentages start at {min}.',
		'bis.all': 'All',
		'bis.hardOnly': 'Hard only',
		'bis.players': '{n} players',
		'bis.source': '{raid}: Hard {hard} · Normal {normal}',
		'bis.span': 'collected {from} – {to}',
		'bis.items': 'Most worn',
		'bis.maxEnchant': 'Fully enchanted: {pct}',
		'bis.skills': 'Skills and stigmas'
	},
	{
		'bis.nav': 'BiS-Listen',
		'bis.title': 'BiS-Listen',
		'bis.intro':
			'Was die besten Spieler je Klasse aus den Ranglisten von Abyss Logs tragen, über den Tag verteilt gesammelt. Ein Klick auf einen Platz zeigt alle Werte mit ihrem Anteil.',
		'bis.none': 'Noch keine Klasse gesammelt. Der Hub holt alle 5 Minuten ein paar Spieler.',
		'bis.notEnough': 'Erst {n} Spieler gesammelt, Prozente gibt es ab {min}.',
		'bis.all': 'Alle',
		'bis.hardOnly': 'Nur Schwer',
		'bis.players': '{n} Spieler',
		'bis.source': '{raid}: Schwer {hard} · Normal {normal}',
		'bis.span': 'gesammelt {from} – {to}',
		'bis.items': 'Am häufigsten getragen',
		'bis.maxEnchant': 'Voll verzaubert: {pct}',
		'bis.skills': 'Skills und Stigmen'
	}
);
