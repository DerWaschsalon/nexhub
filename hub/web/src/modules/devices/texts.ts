import { defineTexts } from '#lib/i18n.svelte.ts';

export const TEXTS = defineTexts(
	{
		'devices.nav': 'Devices',
		'devices.title': 'Devices',
		'devices.intro': 'NexBoards connected to your account.',
		'devices.pair': 'Pair a device',
		'devices.pairHow': 'In NexBoard, open the “NexHub” module and click “Pair”. Enter the code shown there.',
		'devices.code': 'Code',
		'devices.name': 'Name (optional)',
		'devices.namePlaceholder': 'e.g. Gaming PC',
		'devices.pairButton': 'Pair',
		'devices.paired': '“{name}” is approved. NexBoard checks in within a few seconds.',
		'devices.col.device': 'Device',
		'devices.col.paired': 'Paired',
		'devices.col.seen': 'Last seen',
		'devices.col.version': 'Version',
		'devices.remove': 'Remove',
		'devices.confirmRemove': 'Remove {name}? The device has to be paired again afterwards.',
		'devices.none': 'No device paired yet.'
	},
	{
		'devices.nav': 'Geräte',
		'devices.title': 'Geräte',
		'devices.intro': 'NexBoards, die mit deinem Konto verbunden sind.',
		'devices.pair': 'Gerät koppeln',
		'devices.pairHow': 'In NexBoard das Modul „NexHub“ öffnen und auf „Koppeln“ klicken. Den angezeigten Code hier eingeben.',
		'devices.code': 'Code',
		'devices.name': 'Name (optional)',
		'devices.namePlaceholder': 'z. B. Gaming-PC',
		'devices.pairButton': 'Koppeln',
		'devices.paired': '„{name}“ ist bestätigt. NexBoard meldet sich in wenigen Sekunden.',
		'devices.col.device': 'Gerät',
		'devices.col.paired': 'Gekoppelt',
		'devices.col.seen': 'Zuletzt gesehen',
		'devices.col.version': 'Version',
		'devices.remove': 'Entfernen',
		'devices.confirmRemove': '{name} entfernen? Das Gerät muss danach neu gekoppelt werden.',
		'devices.none': 'Noch kein Gerät gekoppelt.'
	}
);
