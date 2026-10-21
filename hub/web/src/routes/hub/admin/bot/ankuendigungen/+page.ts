import { apiLoad, BOT_API, type Announcement } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	announcements: await apiLoad<Announcement[]>(`${BOT_API}/announcements`, fetch)
});
