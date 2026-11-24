<!-- Modul Beute: Dungeon wählen, dann je Boss die Gegenstände mit „bei wie vielen Siegen“ und, ab genug
     Siegen, der Rate „1 zu N“ mit dem Band, in dem die wahre Rate wahrscheinlich liegt. -->
<script lang="ts">
	import Tabs from '#lib/components/Tabs.svelte';
	import { formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { LootItem } from '#modules/loot/api.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const dungeons = $derived(data.loot.dungeons);
	let chosen = $state<string | null>(null);
	const dungeon = $derived(dungeons.find((d) => String(d.dungeon_id) === chosen) ?? dungeons[0]);
	const tabs = $derived(
		dungeons.map((d) => ({ id: String(d.dungeon_id), label: d.difficulty ? `${d.dungeon} · ${d.difficulty}` : d.dungeon }))
	);
	const band = (item: LootItem) =>
		t('loot.band', { low: formatNumber(item.one_in_low ?? 0), high: formatNumber(item.one_in_high ?? 0) });
</script>

<svelte:head><title>{t('loot.title')} · NexHub</title></svelte:head>

<header class="page-head">
	<h1>{t('loot.title')}</h1>
	<p class="dim">{t('loot.intro')}</p>
</header>

{#if !dungeon}
	<p class="notice">{t('loot.none')}</p>
{:else}
	<div class="pick">
		<Tabs {tabs} active={String(dungeon.dungeon_id)} onselect={(id) => (chosen = id)} label={t('loot.title')} />
		<span class="chip accent">{t('loot.runs', { n: dungeon.runs })}</span>
	</div>

	{#each dungeon.bosses as boss (boss.mob)}
		<section class="glass pad">
			<h2>{boss.name} <small class="dim">{t('loot.kills', { n: boss.kills })}</small></h2>
			{#if !boss.items.length}
				<p class="dim">{t('loot.noDrops')}</p>
			{:else}
				<div class="table-wrap">
					<table class="table">
						<thead>
							<tr>
								<th>{t('loot.col.item')}</th>
								<th class="right">{t('loot.col.drops')}</th>
								<th class="right">{t('loot.col.rate')}</th>
								<th class="right">{t('loot.col.band')}</th>
							</tr>
						</thead>
						<tbody>
							{#each boss.items as item (item.item_id)}
								<tr>
									<td>{t('loot.item', { id: item.item_id })}</td>
									<td class="right num">{item.drops} / {item.kills}</td>
									{#if item.one_in === null}
										<td class="right dim" colspan="2">{t('loot.tooFew', { n: data.loot.min_kills })}</td>
									{:else}
										<td class="right num">{t('loot.oneIn', { n: formatNumber(item.one_in) })}</td>
										<td class="right num dim">{band(item)}</td>
									{/if}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
	{/each}
{/if}

<style>
	.pick {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px;
		margin-bottom: 14px;
	}
	section {
		margin-bottom: 14px;
	}
	h2 {
		font-size: 17px;
		margin: 0 0 10px;
	}
	h2 small {
		margin-left: 8px;
		font-size: 13px;
		font-weight: 450;
	}
</style>
