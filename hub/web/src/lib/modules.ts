// Angemeldete Module. Ein neues Modul bekommt hier eine Zeile; Menü und Texte ergeben sich daraus.
import type { Me } from '#lib/api.ts';
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

/** Was dieses Konto im Menü sieht: Admin-Seiten nur für Admins. */
export const navFor = (me: Me): NavItem[] => NAV.filter((i) => !i.admin || me.role === 'admin');

/** Ein Eintrag der Seitenleiste: eine Seite, oder ein Spiel mit seinen Seiten (`pages`). */
export type MenuEntry = NavItem & { pages: NavItem[] };

/** Fasst die Einträge eines Spiels zu einem zusammen. Er führt zur ersten Seite des Spiels und
 *  trägt deren Symbol; die Seiten selbst zeigt das Layout als Reiter über dem Inhalt. */
export function menu(items: NavItem[]): MenuEntry[] {
	const entries: MenuEntry[] = [];
	for (const item of items) {
		const game = item.game ? entries.find((e) => e.label === item.game) : undefined;
		if (game) game.pages.push(item);
		else if (item.game) entries.push({ ...item, label: item.game, pages: [item] });
		else entries.push({ ...item, pages: [] });
	}
	return entries;
}
