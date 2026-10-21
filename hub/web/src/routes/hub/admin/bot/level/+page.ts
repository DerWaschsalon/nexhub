import { apiLoad } from '#lib/api.ts';
import { BOT_API, type BotSection, type LevelReward } from '#modules/bot/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
	const [sections, rewards] = await Promise.all([
		apiLoad<BotSection[]>(`${BOT_API}/sections`, fetch),
		apiLoad<LevelReward[]>(`${BOT_API}/level-rewards`, fetch)
	]);
	return { section: sections.find((s) => s.id === 'level')!, rewards };
};
