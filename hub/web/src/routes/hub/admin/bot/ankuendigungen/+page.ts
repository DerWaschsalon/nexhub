import { apiLoad } from '#lib/api.ts';
import { BOT_API, type Announcement } from '#modules/bot/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	announcements: await apiLoad<Announcement[]>(`${BOT_API}/announcements`, fetch)
});
