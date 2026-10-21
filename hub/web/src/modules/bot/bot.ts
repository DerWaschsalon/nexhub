import type { BotNavItem } from './api.ts';

// Das Menü des Bereichs „Bot“ kommt vom Bot selbst (/control/pages), Reihenfolge nach Gruppe und order.
export const botHref = (slug: string) => (slug ? `/hub/admin/bot/${slug}` : '/hub/admin/bot');

/** Menüeinträge nach Gruppe, Reihenfolge wie vom Bot geliefert. */
export function navGroups(items: BotNavItem[]): { name: string; items: BotNavItem[] }[] {
	const out: { name: string; items: BotNavItem[] }[] = [];
	for (const it of items) {
		const last = out.at(-1);
		if (last && last.name === it.group) last.items.push(it);
		else out.push({ name: it.group, items: [it] });
	}
	return out;
}

/** "3 Tg. 4 Std." / "5 Std. 12 Min." / "8 Min." */
export function formatUptime(s: number): string {
	const d = Math.floor(s / 86400);
	const h = Math.floor((s % 86400) / 3600);
	const m = Math.floor((s % 3600) / 60);
	if (d) return `${d} Tg. ${h} Std.`;
	if (h) return `${h} Std. ${m} Min.`;
	return `${m} Min.`;
}
