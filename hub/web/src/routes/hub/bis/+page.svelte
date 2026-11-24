<!-- Modul BiS-Listen: Klasse wählen (?k=ranger), dann die Ausrüstungsspalte wie in der Armory mit dem
     typischen Gegenstand je Platz, daneben die Figur der Klasse im Klassenlicht. Ein Klick öffnet das Gegenstandsfenster mit dem Anteil je Zeile,
     daneben Skills, Stigmen und Arkana mit Anteil. Wahlweise nur Spieler aus dem Schwer-Modus. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import Tabs from '#lib/components/Tabs.svelte';
	import { formatDateTime, formatPct } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import type { BisSlot, BisStats } from '#modules/bis/api.ts';
	import { CLASS_KEYS, classInfo } from '#modules/logs/classes.ts';
	import { ARCANA } from '#modules/logs/slots.ts';
	import ArcanaRow from '#modules/logs/components/ArcanaRow.svelte';
	import CharacterLayout from '#modules/logs/components/CharacterLayout.svelte';
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
	const skills = $derived(stats?.skills ?? []);
	const equipment = $derived({ equipment: items, wing: null, pet: null });
	const arcana = $derived(items.filter((i) => ARCANA.includes(i.slot_name)));
	const bySlot = $derived(new Map((stats?.slots ?? []).map((s) => [s.item.slot_name, s])));
	const pick = (slot: string) => (open = bySlot.get(slot) ?? null);
	const choose = (key: string) => goto(`?k=${key}`, { replaceState: true });
	// Reiter je Klasse; Klassen ohne gesammelte Spieler sind grau
	const classTabs = $derived(
		CLASS_KEYS.map((key) => {
			const info = classInfo(key);
			return { id: key, label: info?.label ?? key, icon: info?.icon, color: info?.color, disabled: !collected.has(key) };
		})
	);
</script>

<svelte:head><title>{t('bis.title')} · NexHub</title></svelte:head>

<header class="page-head">
	<h1>{t('bis.title')}</h1>
	<p class="dim">{t('bis.intro')}</p>
</header>

{#if !data.classes.length}
	<p class="notice">{t('bis.none')}</p>
{:else}
	<Tabs tabs={classTabs} active={cls} onselect={choose} label={t('bis.title')}>
		{#snippet tab(c)}
			<img src={c.icon} alt="" width="20" height="20" />
			<span style:color={c.id === cls ? c.color : undefined}>{c.label}</span>
		{/snippet}
	</Tabs>

	{#if error}<p class="notice error" role="alert">{error}</p>{/if}

	{#if stats && stats.cls === cls}
		<div class="meta">
			<Tabs tabs={[{ id: 'all', label: t('bis.all') }, { id: 'hard', label: t('bis.hardOnly') }]}
				active={hardOnly ? 'hard' : 'all'} onselect={(id) => (hardOnly = id === 'hard')} />
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
			<CharacterLayout {cls} data={equipment} onOpen={pick}>
				{#snippet detail(slot)}
					{@const s = bySlot.get(slot)}
					{#if s}<ItemTooltip item={s.item} lines={s.lines}>{@render shares(s)}</ItemTooltip>{/if}
				{/snippet}
				<section class="panel pad">
					<h3>{t('bis.skills')}</h3>
					<SkillGrid data={{ skills }} />
					<ArcanaRow {arcana} onItem={(item) => pick(item.slot_name)} />
				</section>
			</CharacterLayout>
		{/if}
	{/if}
{/if}

<!-- Häufigste Gegenstände und Anteil voll verzaubert, im Fenster beim Zeigen und beim Klick -->
{#snippet shares(s: BisSlot)}
	<p class="dim small">{t('bis.items')}</p>
	<ul class="items">
		{#each s.items as i (i.name)}
			<li><span>{i.name}</span><b class="num">{formatPct(i.share * 100)}</b></li>
		{/each}
	</ul>
	<p class="dim small">{t('bis.maxEnchant', { pct: formatPct(s.max_enchant * 100) })}</p>
{/snippet}

<Modal open={open !== null} onclose={() => (open = null)}>
	{#if open}
		<ItemTooltip item={open.item} lines={open.lines} onclose={() => (open = null)}>{@render shares(open)}</ItemTooltip>
	{/if}
</Modal>

<style>
	img {
		vertical-align: -5px;
		margin-right: 6px;
	}
	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 14px;
		margin: 14px 0 18px;
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
