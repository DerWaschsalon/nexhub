<!-- Modul Logs: alle hochgeladenen Runs, neueste zuerst, mit Suche und Filtern. -->
<script lang="ts">
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { RUN_LIMIT } from '#modules/logs/api.ts';
	import RunTable from '#modules/logs/components/RunTable.svelte';
	import { applyFilter, filterOptions, fromParams, isActive, PERIODS, toSearch, type RunFilter } from '#modules/logs/filter.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Aus location statt page.url: nach Zurück aus einem Run zeigt page.url die Adresse ohne Filter
	let filter = $state<RunFilter>(fromParams(new URLSearchParams(location.search)));
	const options = $derived(filterOptions(data.runs));
	const runs = $derived(applyFilter(data.runs, filter));

	// Filter in die Adresse schreiben, ohne neu zu laden: Zurück aus einem Run landet in derselben Auswahl.
	// Verglichen wird mit location, nicht page.url – die bleibt bei shallow auf dem alten Stand – und
	// nur der Filter ist Abhängigkeit, sonst startet jede Adressänderung den Effekt endlos neu.
	$effect(() => {
		const search = toSearch(filter);
		untrack(() => {
			if (search !== location.search) goto(`${location.pathname}${search}`, { shallow: true, replace: true });
		});
	});

	function reset() {
		filter = fromParams(new URLSearchParams());
	}

	// Ein Auswahlfeld lohnt erst ab zwei Werten; ist schon einer gewählt (aus der Adresse), bleibt es da
	const show = (values: string[], current: string) => values.length > 1 || current !== '';
</script>

<header class="page-head">
	<h1>{t('logs.list.title')}</h1>
	<p>{t('logs.list.intro')}</p>
</header>

{#if data.runs.length}
	<section class="glass pad filters" aria-label={t('logs.find.search')}>
		<label class="field search">
			{t('logs.find.search')}
			<input class="input" type="search" bind:value={filter.q} placeholder={t('logs.find.placeholder')} />
		</label>
		{#if show(options.dungeons, filter.dungeon)}
			<label class="field">
				{t('logs.find.dungeon')}
				<select class="input" bind:value={filter.dungeon}>
					<option value="">{t('logs.find.any')}</option>
					{#each options.dungeons as d (d)}<option value={d}>{d}</option>{/each}
				</select>
			</label>
		{/if}
		{#if show(options.difficulties, filter.difficulty)}
			<label class="field">
				{t('logs.find.difficulty')}
				<select class="input" bind:value={filter.difficulty}>
					<option value="">{t('logs.find.any')}</option>
					{#each options.difficulties as d (d)}<option value={d}>{d}</option>{/each}
				</select>
			</label>
		{/if}
		{#if show(options.players, filter.player)}
			<label class="field">
				{t('logs.find.player')}
				<select class="input" bind:value={filter.player}>
					<option value="">{t('logs.find.any')}</option>
					{#each options.players as p (p)}<option value={p}>{p}</option>{/each}
				</select>
			</label>
		{/if}
		{#if show(options.uploaders, filter.uploader)}
			<label class="field">
				{t('logs.find.uploader')}
				<select class="input" bind:value={filter.uploader}>
					<option value="">{t('logs.find.any')}</option>
					{#each options.uploaders as u (u)}<option value={u}>{u}</option>{/each}
				</select>
			</label>
		{/if}
		<label class="field">
			{t('logs.find.status')}
			<select class="input" bind:value={filter.status}>
				<option value="">{t('logs.find.any')}</option>
				<option value="clear">{t('logs.find.clear')}</option>
				<option value="open">{t('logs.find.open')}</option>
			</select>
		</label>
		<label class="field">
			{t('logs.find.period')}
			<select class="input" bind:value={filter.days}>
				<option value="">{t('logs.find.any')}</option>
				{#each PERIODS as n (n)}
					<option value={n}>{n === '1' ? t('logs.find.day') : t('logs.find.days', { n })}</option>
				{/each}
			</select>
		</label>
		{#if isActive(filter)}
			<div class="reset">
				<button class="btn small" type="button" onclick={reset}>{t('logs.find.reset')}</button>
			</div>
		{/if}
	</section>

	<section class="glass pad table-wrap">
		{#if runs.length}
			<RunTable {runs} />
		{:else}
			<p class="dim empty">{t('logs.list.noMatch')}</p>
		{/if}
		<p class="dim count">
			{isActive(filter)
				? t('logs.list.countOf', { n: formatNumber(runs.length), t: formatNumber(data.runs.length) })
				: t('logs.list.count', { n: formatNumber(data.runs.length) })}
			{#if data.runs.length >= RUN_LIMIT}· {t('logs.list.limit', { n: formatNumber(RUN_LIMIT) })}{/if}
		</p>
	</section>
{:else}
	<section class="glass pad"><p class="dim empty">{t('logs.list.empty')}</p></section>
{/if}

<style>
	.filters {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
		gap: 14px;
		align-items: end;
		margin-bottom: 16px;
	}
	.search {
		grid-column: 1 / -1;
	}
	.reset {
		padding-bottom: 4px;
	}
	.count {
		margin: 12px 14px 0;
		font-size: 13px;
	}
	.empty {
		margin: 0;
	}
</style>
