<!-- Modul Armory: eigene Charaktere über die Suche der AION-2-Website eintragen, darunter alle. -->
<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { REGIONS, type ArmoryHit, type ArmoryItem } from '#modules/armory/api.ts';
	import CharacterGrid from '#modules/armory/components/CharacterGrid.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let region = $state<string>('eu');
	let name = $state('');
	let hits = $state<ArmoryHit[] | null>(null);
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

	async function search(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			hits = await api<ArmoryHit[]>(`/api/armory/search?${new URLSearchParams({ name: name.trim(), region })}`);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

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
</header>

<section class="glass pad add">
	<h2>{t('armory.add')}</h2>
	<p class="dim">{t('armory.addHow')}</p>
	<form onsubmit={search}>
		<label class="field">
			{t('armory.region')}
			<select class="input" bind:value={region}>
				{#each REGIONS as r (r)}<option value={r}>{t(`region.${r}`)}</option>{/each}
			</select>
		</label>
		<label class="field grow">
			{t('armory.name')}
			<input class="input" bind:value={name} minlength="2" maxlength="64" required autocomplete="off" spellcheck="false" />
		</label>
		<button class="btn primary" disabled={busy || name.trim().length < 2}>{t('armory.search')}</button>
	</form>
	{#if hits}
		{#if hits.length}
			<ul class="hits">
				{#each hits as h (`${h.server_id}/${h.character_id}`)}
					<li>
						{#if h.image}<img src={h.image} alt="" width="36" height="36" referrerpolicy="no-referrer" />{/if}
						<span class="hit">
							<strong>{h.name}</strong>
							<span class="dim">{[h.server, h.level ? t('logs.char.level', { n: h.level }) : ''].filter(Boolean).join(' · ')}</span>
							{#if h.taken_by}<span class="dim small">{t('armory.takenBy', { name: h.taken_by })}</span>{/if}
						</span>
						{#if !h.taken_by}
							<button class="btn small" disabled={busy} onclick={() => add(h)}>{t('armory.addButton')}</button>
						{/if}
					</li>
				{/each}
			</ul>
		{:else}
			<p class="dim">{t('armory.noHits')}</p>
		{/if}
	{/if}
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
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		align-items: end;
	}
	.grow {
		flex: 1;
		min-width: 180px;
	}
	.hits {
		list-style: none;
		margin: 16px 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.hits li {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.hits img {
		border-radius: 8px;
		object-fit: cover;
	}
	.hit {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 0;
	}
	.small {
		font-size: 12px;
	}
	/* Abstand nach oben statt unter dem Raster: fällt mit dem des Suchkastens zusammen */
	.group {
		margin: 22px 0 12px;
	}
</style>
