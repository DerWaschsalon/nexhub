// Was ein Modul dem Kern mitteilt. Der Kern liefert Layout, Design (app.css), Menü, Login, Sprache
// und API-Zugriff; ein Modul bringt nur seinen Inhalt mit.
//
// Ein Modul ist ein Ordner unter src/modules/<id>/ mit module.ts (diese Angaben) und allem, was es
// braucht (Komponenten, Typen, Texte). Seine Seiten liegen unter src/routes/hub/… (SvelteKit
// verlangt Seiten dort). Neu anmelden: in lib/modules.ts eintragen. Siehe hub/README.md.
import type { Component } from 'svelte';
import type { IconName } from '#lib/components/Icon.svelte';
import type { Texts } from '#lib/i18n.svelte.ts';

export type NavItem = {
	href: string;
	/** Textschlüssel (lib/i18n.svelte.ts), nicht der Text selbst */
	label: string;
	icon: IconName;
	/** nur für Admins sichtbar; die API prüft das zusätzlich */
	admin?: boolean;
	/** Spiel (Textschlüssel, z. B. 'game.aion2'): Einträge desselben Spiels stehen im Menü als ein
	 *  Eintrag, ihre Seiten als Reiter über dem Inhalt (lib/modules.ts menu) */
	game?: string;
	/** Vorschau in der Kachel auf der Übersicht (routes/hub/+page.svelte); holt ihre Daten selbst */
	overview?: Component;
};

export type HubModule = {
	id: string;
	/** Einträge in der Seitenleiste, in dieser Reihenfolge */
	nav: NavItem[];
	texts?: Texts;
};
