import { apiLoad, BOT_API, type CustomCommand } from '#lib/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	commands: await apiLoad<CustomCommand[]>(`${BOT_API}/commands`, fetch)
});
