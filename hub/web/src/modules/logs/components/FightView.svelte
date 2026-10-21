<!-- Ein Bosskampf: Reiter Schaden (Verlauf + Rangliste), Fähigkeiten, Zeitleiste, Tode. -->
<script lang="ts">
	import { formatDuration } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { playerId, type Fight } from '../api.ts';
	import BuffTimeline from './BuffTimeline.svelte';
	import DpsChart from './DpsChart.svelte';
	import PlayerName from './PlayerName.svelte';
	import RankBars from './RankBars.svelte';
	import SkillTable from './SkillTable.svelte';
	import SkillTimeline from './SkillTimeline.svelte';

	let { fight }: { fight: Fight } = $props();

	type Tab = 'damage' | 'skills' | 'timeline' | 'deaths';
	const TABS: Tab[] = ['damage', 'skills', 'timeline', 'deaths'];

	let tab = $state<Tab>('damage');
	let player = $state<string | null>(null);
	const selected = $derived(fight.players.find((p) => playerId(p) === player) ?? fight.players[0]);
</script>

{#snippet picker()}
	<div class="tabs pick" role="radiogroup" aria-label={t('logs.player.pick')}>
		{#each fight.players as p (p.actor)}
			<button type="button" role="radio" aria-checked={p.actor === selected.actor} class:active={p.actor === selected.actor}
				onclick={() => (player = playerId(p))}>
				<PlayerName name={p.name} cls={p.cls} />
			</button>
		{/each}
	</div>
{/snippet}

<div class="tabs" role="tablist">
	{#each TABS as id (id)}
		<button type="button" role="tab" aria-selected={tab === id} class:active={tab === id} onclick={() => (tab = id)}>
			{t(`logs.tab.${id}`, { n: fight.deaths.length })}
		</button>
	{/each}
	<span class="chip result" class:ok={fight.killed} class:danger={!fight.killed}>
		{t(fight.killed ? 'logs.fight.killed' : 'logs.fight.wipe')}
	</span>
</div>

{#if tab === 'damage'}
	<section class="glass pad">
		<h2>{t('logs.chart.title')}</h2>
		<DpsChart {fight} highlight={player} />
	</section>
	<section class="glass pad">
		<h2>{t('logs.rank.title')}</h2>
		<p class="dim hint">{t('logs.rank.hint')}</p>
		<RankBars players={fight.players} selected={player} onSelect={(n) => (player = player === n ? null : n)} />
	</section>
{:else if tab === 'skills' && selected}
	<section class="glass pad">
		{@render picker()}
		{#key selected.actor}<SkillTable player={selected} boss={fight.name} />{/key}
	</section>
{:else if tab === 'timeline' && selected}
	<section class="glass pad">
		{@render picker()}
		{#key selected.actor}<SkillTimeline player={selected} durationMs={fight.duration_ms} boss={fight.name} />{/key}
	</section>
	<section class="glass pad">
		<h2>{t('logs.timeline.buffs')}</h2>
		<BuffTimeline buffs={fight.buffs} actor={selected.actor} target={fight.target} playerName={selected.name}
			boss={fight.name} durationMs={fight.duration_ms} />
	</section>
{:else if tab === 'deaths'}
	<section class="glass pad">
		{#if fight.deaths.length === 0}
			<p class="dim">{t('logs.deaths.none')}</p>
		{:else}
			<div class="table-wrap">
				<table class="table">
					<thead>
						<tr>
							<th>{t('logs.deaths.time')}</th>
							<th>{t('logs.deaths.player')}</th>
							<th>{t('logs.deaths.revived')}</th>
						</tr>
					</thead>
					<tbody>
						{#each fight.deaths as d, i (i)}
							<tr>
								<td class="num">{formatDuration(d.t_ms)}</td>
								<td><PlayerName name={d.name} cls={fight.players.find((x) => x.name === d.name)?.cls ?? null} /></td>
								<td class="dim num">
									{d.revived_ms != null ? t('logs.deaths.after', { d: formatDuration(d.revived_ms - d.t_ms) }) : t('logs.deaths.no')}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
{/if}

<style>
	h2 {
		font-size: 17px;
		margin-bottom: 14px;
	}
	.hint {
		margin: -8px 0 12px;
		font-size: 13px;
	}
	.result {
		margin-left: auto;
	}
	.pick {
		flex-wrap: wrap;
		margin-bottom: 14px;
	}
</style>
