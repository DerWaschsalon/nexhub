import { apiLoad } from '#lib/api.ts';
import type { RatingRules } from '#modules/logs/rating.ts';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({
	rules: await apiLoad<RatingRules>('/api/rating/rules', fetch)
});
