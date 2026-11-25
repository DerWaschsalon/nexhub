// Angemeldete Module. Ein neues Modul bekommt hier eine Zeile; Menü und Texte ergeben sich daraus.
import type { Me } from '#lib/api.ts';
import { addTexts } from '#lib/i18n.svelte.ts';
import type { HubModule, NavItem } from '#lib/module.ts';
import { CORE_TEXTS } from '#lib/texts.ts';
import armory from '#modules/armory/module.ts';
import bis from '#modules/bis/module.ts';
import bot from '#modules/bot/module.ts';
import devices from '#modules/devices/module.ts';
import feedback from '#modules/feedback/module.ts';
import logs from '#modules/logs/module.ts';
import loot from '#modules/loot/module.ts';
import schedule from '#modules/schedule/module.ts';

export const MODULES: HubModule[] = [logs, armory, bis, loot, schedule, devices, feedback, bot];

addTexts(CORE_TEXTS);
for (const m of MODULES) if (m.texts) addTexts(m.texts);

/** Seitenleiste: Übersicht, dann die Module, am Ende die Admin-Seiten des Kerns. */
export const NAV: NavItem[] = [
	{ href: '/hub', label: 'nav.overview', icon: 'home' },
	...MODULES.flatMap((m) => m.nav),
	{ href: '/hub/admin/konten', label: 'nav.accounts', icon: 'users', admin: true },
	{ href: '/hub/admin/statistik', label: 'nav.stats', icon: 'chart', admin: true },
	{ href: '/hub/admin/system', label: 'nav.system', icon: 'server', admin: true }
];

/** Was dieses Konto im Menü sieht: Admin-Seiten nur für Admins. */
export const navFor = (me: Me): NavItem[] => NAV.filter((i) => !i.admin || me.role === 'admin');

/** Ein Eintrag der Seitenleiste: eine Seite, oder eine Gruppe mit ihren Seiten (`pages`). */
export type MenuEntry = NavItem & { pages: NavItem[] };

const ADMIN_GROUP = 'nav.admin';
const ADMIN_ICON = 'server';

/** Fasst die Seiten eines Spiels und die Admin-Seiten je zu einer aufklappbaren Gruppe zusammen. */
export function menu(items: NavItem[]): MenuEntry[] {
	const entries: MenuEntry[] = [];
	for (const item of items) {
		const group = item.game ?? (item.admin ? ADMIN_GROUP : undefined);
		const entry = group ? entries.find((e) => e.label === group) : undefined;
		if (entry) entry.pages.push(item);
		else if (group) entries.push({ ...item, label: group, icon: item.game ? item.icon : ADMIN_ICON, pages: [item] });
		else entries.push({ ...item, pages: [] });
	}
	return entries;
}
