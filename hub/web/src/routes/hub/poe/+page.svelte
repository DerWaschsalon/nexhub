<!-- Modul Path of Exile: oben Spiel (PoE 1 / PoE 2, in ?game=) und aktive Liga, darunter Items suchen
     und merken, dann die Merkliste als Karten. Preise kommen von poe.ninja, daher der feste Hinweis. -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { t } from '#lib/i18n.svelte.ts';
	import { addWatch, GAMES, ninjaEconomy, searchItems, type PoeFound } from '#modules/poe/api.ts';
	import WatchCard from '#modules/poe/components/WatchCard.svelte';
	import { formatPrice } from '#modules/poe/format.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let q = $state('');
	let hits = $state<PoeFound[] | null>(null);
	let busy = $state(false);
	let error = $state('');

	const watched = $derived(new Set(data.list?.watches.map((w) => w.key)));

	// Beim Spielwechsel gehören alte Treffer zum anderen Spiel. Über $derived, damit das Neuladen
	// nach „Merken“ (gleiches Spiel) die Treffer stehen lässt.
	const game = $derived(data.game);
	$effect(() => {
		void game;
		hits = null;
	});

	async function run(action: () => Promise<void>) {
		busy = true;
		error = '';
		try {
			await action();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	function search(e: SubmitEvent) {
		e.preventDefault();
		run(async () => {
			hits = await searchItems(data.game, q.trim());
		});
	}

	function add(hit: PoeFound) {
		run(async () => {
			await addWatch(data.game, hit.key);
			await invalidateAll();
		});
	}
</script>

<svelte:head><title>{t('poe.title')} · NexHub</title></svelte:head>

<header class="page-head">
	<div class="title">
		<h1>{t('poe.title')}</h1>
		<nav class="tabs" aria-label={t('poe.title')}>
			{#each GAMES as g (g)}
				<a href="?game={g}" class:active={g === data.game}>{t(`poe.game.${g}`)}</a>
			{/each}
		</nav>
		{#if data.list}<span class="chip accent">{t('poe.league', { name: data.list.league })}</span>{/if}
	</div>
	<p>{t('poe.intro')}</p>
</header>

{#if !data.list}
	<p class="notice" role="status">{t('poe.off')}</p>
{:else}
	<section class="glass pad add">
		<h2>{t('poe.watch')}</h2>
		<form onsubmit={search}>
			<label class="field grow">
				{t('poe.searchLabel')}
				<input class="input" bind:value={q} placeholder={t('poe.searchPlaceholder')} maxlength="100" required
					autocomplete="off" spellcheck="false" />
			</label>
			<button class="btn primary" disabled={busy || !q.trim()}>{t('poe.search')}</button>
		</form>
		{#if hits?.length}
			<ul class="hits">
				{#each hits as h (h.key)}
					<li>
						{#if h.icon}<img src={h.icon} alt="" width="32" height="32" referrerpolicy="no-referrer" />{/if}
						<span class="hit">
							<strong>{h.name}</strong>
							<span class="dim">{h.category} · {formatPrice(h.price, h.unit)}</span>
						</span>
						{#if watched.has(h.key)}
							<span class="chip ok">{t('poe.watched')}</span>
						{:else}
							<button class="btn small" disabled={busy} onclick={() => add(h)}>{t('poe.add')}</button>
						{/if}
					</li>
				{/each}
			</ul>
		{:else if hits}
			<p class="dim">{t('poe.noHits')}</p>
		{/if}
		{#if error}<p class="notice error" role="alert">{error}</p>{/if}
	</section>

	{#if data.list.watches.length}
		<div class="grid">
			{#each data.list.watches as w (w.id)}<WatchCard {w} unit={data.list.unit} />{/each}
		</div>
	{:else}
		<p class="dim">{t('poe.none')}</p>
	{/if}

	<p class="source dim">
		{t('poe.source')} ·
		<a href={ninjaEconomy(data.game)} target="_blank" rel="noopener noreferrer">{t('poe.allPrices')} →</a>
	</p>
{/if}

<style>
	.title {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 16px;
	}
	.title h1 {
		margin-right: auto;
	}
	.tabs {
		margin: 0;
	}
	.add {
		margin-bottom: 22px;
	}
	h2 {
		font-size: 18px;
		margin-bottom: 14px;
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
		object-fit: contain;
	}
	.hit {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 0;
	}
	.hits + p,
	.add > p {
		margin: 14px 0 0;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr));
		gap: 12px;
	}
	.source {
		margin-top: 22px;
		font-size: 13px;
	}
</style>
