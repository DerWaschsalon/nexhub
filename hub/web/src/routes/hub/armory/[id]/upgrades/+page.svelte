<!-- Reiter „Upgrades“ eines Armory-Charakters: der Plan aus der API (upgrades.py), neu geladen, wenn Ziel
     (?goal=BiS) oder Sprache wechseln, weil die Namen übersetzt von der API kommen. -->
<script lang="ts">
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import UpgradePlanView from '#modules/logs/components/UpgradePlan.svelte';
	import { DEFAULT_GOAL, type UpgradePlan } from '#modules/logs/rating.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const c = $derived(data.character);
	const goal = $derived(page.url.searchParams.get('goal') ?? DEFAULT_GOAL);
	let plan = $state<UpgradePlan | null>(null);
	let loaded = $state(false);
	let error = $state('');

	function show(result: UpgradePlan | null) {
		plan = result;
		loaded = true;
	}

	$effect(() => {
		const query = new URLSearchParams({ goal, lang: i18n.lang });
		error = '';
		api<UpgradePlan | null>(`/api/armory/${c.id}/upgrades?${query}`)
			.then(show)
			.catch((e) => (error = e instanceof Error ? e.message : String(e)));
	});
</script>

{#if error}
	<p class="notice error" role="alert">{error}</p>
{:else if plan}
	<UpgradePlanView {plan} hints={c.hints[i18n.lang] ?? []} base={page.url.pathname} />
{:else if loaded}
	<p class="notice">{t('logs.upgrades.noCensus')}</p>
{/if}
