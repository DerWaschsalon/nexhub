// Menü des Hubs. Ein neuer Bereich bekommt hier eine Zeile; `admin` blendet ihn für Mitglieder aus.
import type { IconName } from '#lib/components/Icon.svelte';

export type NavItem = { href: string; label: string; icon: IconName; admin?: boolean };

export const NAV: NavItem[] = [
	{ href: '/hub', label: 'Übersicht', icon: 'home' },
	{ href: '/hub/admin/konten', label: 'Konten', icon: 'users', admin: true },
	{ href: '/hub/admin/system', label: 'System', icon: 'server', admin: true }
];
