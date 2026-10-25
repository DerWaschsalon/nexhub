<!-- Modul Armory: eigene Charaktere über die Suche der AION-2-Website eintragen, darunter alle. -->
<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { ArmoryHit, ArmoryItem } from '#modules/armory/api.ts';
	import CharacterGrid from '#modules/armory/components/CharacterGrid.svelte';
	import CharacterSearch from '#modules/armory/components/CharacterSearch.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let busy = $state(false);
	let error = $state('');

	const mine = $derived(data.characters.filter((c) => c.mine));
	const others = $derived(data.characters.filter((c) => !c.mine));

	// Solange ein eigener Charakter noch geholt wird, alle 5 s neu laden
	$effect(() => {
		if (!data.characters.some((c) => c.status === 'offen')) return;
		const timer = setInterval(() => invalidateAll(), 5000);
		return () => clearInterval(timer);
	});

	async function add(hit: ArmoryHit) {
		busy = true;
		error = '';
		try {
			const c = await api<ArmoryItem>('/api/armory', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ name: hit.name, server_id: hit.server_id, character_id: hit.character_id })
			});
			await goto(`/hub/armory/${c.id}`);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}
</script>

<header class="page-head">
	<h1>{t('armory.title')}</h1>
	<p>{t('armory.intro')}</p>
	<a class="btn small" href="/hub/armory/vergleich">{t('armory.compare.title')}</a>
</header>

<section class="glass pad add">
	<h2>{t('armory.add')}</h2>
	<p class="dim">{t('armory.addHow')}</p>
	<CharacterSearch>
		{#snippet action(h: ArmoryHit)}
			{#if !h.taken_by}
				<button class="btn small" disabled={busy} onclick={() => add(h)}>{t('armory.addButton')}</button>
			{/if}
		{/snippet}
	</CharacterSearch>
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
</section>

{#if mine.length}
	<h2 class="group">{t('armory.mine')}</h2>
	<CharacterGrid characters={mine} />
{/if}

{#if others.length}
	<h2 class="group">{t('armory.all')}</h2>
	<CharacterGrid characters={others} />
{:else if !mine.length}
	<h2 class="group">{t('armory.all')}</h2>
	<p class="dim empty">{t('armory.none')}</p>
{/if}

<style>
	.page-head .btn {
		margin-top: 10px;
	}
	.add {
		margin-bottom: 22px;
	}
	h2 {
		font-size: 18px;
		margin-bottom: 4px;
	}
	.add > p {
		margin: 0 0 14px;
	}
	/* Abstand nach oben statt unter dem Raster: fällt mit dem des Suchkastens zusammen */
	.group {
		margin: 22px 0 12px;
	}
</style>
