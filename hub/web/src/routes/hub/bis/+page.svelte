<!-- Modul BiS-Listen: Klasse wählen (?k=ranger), dann die Ausrüstungsspalte wie in der Armory mit dem
     typischen Gegenstand je Platz. Ein Klick öffnet das Gegenstandsfenster mit dem Anteil je Zeile,
     daneben Skills, Stigmen und Arkana mit Anteil. Wahlweise nur Spieler aus dem Schwer-Modus. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import { formatDateTime, formatPct } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import type { BisSlot, BisStats } from '#modules/bis/api.ts';
	import { CLASS_KEYS, classInfo } from '#modules/logs/classes.ts';
	import { ARCANA } from '#modules/logs/slots.ts';
	import ArcanaRow from '#modules/logs/components/ArcanaRow.svelte';
	import EquipmentPanel from '#modules/logs/components/EquipmentPanel.svelte';
	import ItemTooltip from '#modules/logs/components/ItemTooltip.svelte';
	import Modal from '#modules/logs/components/Modal.svelte';
	import SkillGrid from '#modules/logs/components/SkillGrid.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const collected = $derived(new Map(data.classes.map((c) => [c.cls, c])));
	const cls = $derived(page.url.searchParams.get('k') ?? data.classes[0]?.cls ?? null);
	let hardOnly = $state(false);
	let stats = $state<BisStats | null>(null);
	let error = $state('');
	let open = $state<BisSlot | null>(null);

	// Neu laden, wenn Klasse, Modus oder Sprache wechseln (die Namen kommen übersetzt von der API)
	$effect(() => {
		if (!cls) return;
		const query = new URLSearchParams({ lang: i18n.lang, ...(hardOnly ? { tier: 'Hard' } : {}) });
		error = '';
		api<BisStats>(`/api/bis/${cls}?${query}`)
			.then((s) => (stats = s))
			.catch((e) => (error = e instanceof Error ? e.message : String(e)));
	});

	const items = $derived(stats?.slots.map((s) => s.item) ?? []);
	const equipment = $derived({ equipment: items, wing: null, pet: null });
	const arcana = $derived(items.filter((i) => ARCANA.includes(i.slot_name)));
	const pick = (slot: string) => (open = stats?.slots.find((s) => s.item.slot_name === slot) ?? null);
	const choose = (key: string) => goto(`?k=${key}`, { replaceState: true });
</script>

<svelte:head><title>{t('bis.title')} · NexHub</title></svelte:head>

<header class="page-head">
	<h1>{t('bis.title')}</h1>
	<p class="dim">{t('bis.intro')}</p>
</header>

{#if !data.classes.length}
	<p class="notice">{t('bis.none')}</p>
{:else}
	<nav class="tabs">
		{#each CLASS_KEYS as key (key)}
			{@const info = classInfo(key)}
			<button class:active={key === cls} disabled={!collected.has(key)} onclick={() => choose(key)}>
				<img src={info?.icon} alt="" width="20" height="20" />
				<span style:color={key === cls ? info?.color : undefined}>{info?.label}</span>
			</button>
		{/each}
	</nav>

	{#if error}<p class="notice error" role="alert">{error}</p>{/if}

	{#if stats && stats.cls === cls}
		<div class="meta">
			<nav class="tabs">
				<button class:active={!hardOnly} onclick={() => (hardOnly = false)}>{t('bis.all')}</button>
				<button class:active={hardOnly} onclick={() => (hardOnly = true)}>{t('bis.hardOnly')}</button>
			</nav>
			<span class="chip accent">{t('bis.players', { n: stats.size })}</span>
			{#if stats.raid}
				<span class="dim small">
					{t('bis.source', { raid: stats.raid, hard: stats.tiers.Hard ?? 0, normal: stats.tiers.Normal ?? 0 })}
				</span>
			{/if}
			{#if stats.oldest && stats.newest}
				<span class="dim small">{t('bis.span', { from: formatDateTime(stats.oldest), to: formatDateTime(stats.newest) })}</span>
			{/if}
		</div>

		{#if !stats.slots.length}
			<p class="notice">{t('bis.notEnough', { n: stats.size, min: stats.min_sample })}</p>
		{:else}
			<div class="layout">
				<section class="glass pad">
					<h3>{t('bis.skills')}</h3>
					<SkillGrid data={{ skills: stats.skills }} />
					<ArcanaRow {arcana} onItem={(item) => pick(item.slot_name)} />
				</section>
				<div class="doll"><EquipmentPanel data={equipment} onItem={(item) => pick(item.slot_name)} /></div>
			</div>
		{/if}
	{/if}
{/if}

<Modal open={open !== null} onclose={() => (open = null)}>
	{#if open}
		<ItemTooltip item={open.item} lines={open.lines} onclose={() => (open = null)}>
			<p class="dim small">{t('bis.items')}</p>
			<ul class="items">
				{#each open.items as i (i.name)}
					<li><span>{i.name}</span><b class="num">{formatPct(i.share * 100)}</b></li>
				{/each}
			</ul>
			<p class="dim small">{t('bis.maxEnchant', { pct: formatPct(open.max_enchant * 100) })}</p>
		</ItemTooltip>
	{/if}
</Modal>

<style>
	.tabs img {
		vertical-align: -5px;
		margin-right: 6px;
	}
	.tabs button:disabled {
		opacity: 0.35;
		cursor: default;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 14px;
		margin: 14px 0 18px;
	}
	.layout {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 18px;
		align-items: start;
	}
	@media (max-width: 760px) {
		.layout {
			grid-template-columns: 1fr;
		}
		/* schmal: erst die Ausrüstung, dann Skills und Arkana */
		.doll {
			order: -1;
		}
	}
	.items {
		list-style: none;
		margin: 4px 0 8px;
		padding: 0;
	}
	.items li {
		display: flex;
		justify-content: space-between;
		gap: 12px;
	}
</style>
