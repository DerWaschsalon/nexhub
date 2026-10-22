// Angemeldete Module. Ein neues Modul bekommt hier eine Zeile; Menü und Texte ergeben sich daraus.
import { addTexts } from '#lib/i18n.svelte.ts';
import type { HubModule, NavItem } from '#lib/module.ts';
import { CORE_TEXTS } from '#lib/texts.ts';
import armory from '#modules/armory/module.ts';
import bot from '#modules/bot/module.ts';
import devices from '#modules/devices/module.ts';
import logs from '#modules/logs/module.ts';

export const MODULES: HubModule[] = [logs, armory, devices, bot];

addTexts(CORE_TEXTS);
for (const m of MODULES) if (m.texts) addTexts(m.texts);

/** Seitenleiste: Übersicht, dann die Module, am Ende die Admin-Seiten des Kerns. */
export const NAV: NavItem[] = [
	{ href: '/hub', label: 'nav.overview', icon: 'home' },
	...MODULES.flatMap((m) => m.nav),
	{ href: '/hub/admin/konten', label: 'nav.accounts', icon: 'users', admin: true },
	{ href: '/hub/admin/system', label: 'nav.system', icon: 'server', admin: true }
];
