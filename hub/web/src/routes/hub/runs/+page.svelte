<!-- Modul Logs: Runs nach Dungeon. Oben Zeitraum (Heute, Woche, Alle) und Art (Gruppe, Solo), darunter je Dungeon
     eine Karte mit den Zahlen des Zeitraums; ein Klick zeigt nur dessen Runs (runs/dungeon/[name]). -->
<script lang="ts">
	import Tabs from '#lib/components/Tabs.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import DungeonCard from '#modules/logs/components/DungeonCard.svelte';
	import { groupDungeons, KINDS, matchesKind, PERIODS, type Kind, type Period } from '#modules/logs/dungeons.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let q = $state('');

	const groups = $derived(groupDungeons(data.all, data.inPeriod));
	const ofKind = $derived(groups.filter((g) => matchesKind(g, data.kind)));
	const shown = $derived(ofKind.filter((g) => g.name.toLocaleLowerCase().includes(q.trim().toLocaleLowerCase())));
	const when = $derived(t(`logs.when.${data.period}`));

	function href(period: Period, kind: Kind): string {
		const s = new URLSearchParams();
		if (period !== 'heute') s.set('zeit', period);
		if (kind !== 'gruppe') s.set('art', kind);
		const str = s.toString();
		return `/hub/runs${str ? `?${str}` : ''}`;
	}
</script>

<svelte:head><title>{t('logs.list.title')} · NexHub</title></svelte:head>

<header class="page-head head">
	<div>
		<h1>{t('logs.dungeons.title')}</h1>
		<p>{t('logs.dungeons.intro')}</p>
	</div>
	<div class="totals">
		<div class="glass total"><b class="num">{ofKind.reduce((s, g) => s + g.runs, 0)}</b><small>{t('logs.dungeons.runs', { when })}</small></div>
		<div class="glass total"><b class="num ok">{ofKind.reduce((s, g) => s + g.kills, 0)}</b><small>{t('logs.dungeons.kills')}</small></div>
		<div class="glass total"><b class="num">{ofKind.length}</b><small>{t('logs.dungeons.count')}</small></div>
	</div>
</header>

<div class="bar">
	<Tabs label={t('logs.dungeons.period')} active={data.period}
		tabs={PERIODS.map((p) => ({ id: p, label: t(`logs.period.${p}`), href: href(p, data.kind) }))} />
	<Tabs label={t('logs.dungeons.kind')} active={data.kind}
		tabs={KINDS.map((k) => ({ id: k, label: t(`logs.kind.${k}`), href: href(data.period, k) }))} />
	<label class="search">
		<span class="sr-only">{t('logs.dungeons.search')}</span>
		<input class="input" type="search" bind:value={q} placeholder={t('logs.dungeons.search')} />
	</label>
</div>

{#if shown.length}
	<section class="cards" aria-label={t('logs.dungeons.count')}>
		{#each shown as group (group.name)}
			<DungeonCard {group} period={data.period} />
		{/each}
	</section>
{:else}
	<p class="glass pad empty">{data.all.length ? t('logs.dungeons.none', { when }) : t('logs.list.empty')}</p>
{/if}

<style>
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		justify-content: space-between;
		gap: 18px;
	}
	.totals {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
	}
	.total {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 96px;
		padding: 12px 16px;
		border-radius: 12px;
	}
	.total b {
		font-size: 22px;
		font-weight: 600;
	}
	.total b.ok {
		color: var(--ok);
	}
	.total small {
		font-size: 12px;
		color: var(--faint);
	}
	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 12px;
		margin-bottom: 18px;
	}
	.search {
		margin-left: auto;
	}
	.search .input {
		width: 220px;
		max-width: 100%;
	}
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
		gap: 16px;
	}
	.empty {
		text-align: center;
		color: var(--dim);
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>
