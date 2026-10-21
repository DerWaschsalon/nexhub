import { error } from '@sveltejs/kit';
import { apiLoad } from '#lib/api.ts';
import { BOT_API, type BotSection } from '#modules/bot/api.ts';
import type { PageLoad } from './$types';

// Reine Formular-Bereiche (allgemein, automod, …): Schema und Werte kommen vom Bot
export const load: PageLoad = async ({ fetch, params }) => {
	const sections = await apiLoad<BotSection[]>(`${BOT_API}/sections`, fetch);
	const section = sections.find((s) => s.id === params.bereich);
	if (!section) error(404, 'Diesen Bereich hat der Bot nicht');
	return { section };
};
