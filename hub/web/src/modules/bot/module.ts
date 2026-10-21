// Modul Bot: TheWashBot über seine Steuer-API einstellen (nur Admins). Seiten unter
// routes/hub/admin/bot/, Unterseiten in bot.ts. Die Texte des Bots selbst kommen vom Bot und
// sind deutsch; hier steht nur der Menüeintrag.
import { defineTexts } from '#lib/i18n.svelte.ts';
import type { HubModule } from '#lib/module.ts';

export default {
	id: 'bot',
	nav: [{ href: '/hub/admin/bot', label: 'bot.nav', icon: 'bot', admin: true }],
	texts: defineTexts({ 'bot.nav': 'Bot' }, { 'bot.nav': 'Bot' })
} satisfies HubModule;
