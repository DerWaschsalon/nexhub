import { apiLoad } from '#lib/api.ts';
import type { FeedbackEntry } from '#modules/feedback/api.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	entries: await apiLoad<FeedbackEntry[]>('/api/feedback', fetch)
});
