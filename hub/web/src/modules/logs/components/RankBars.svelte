<!-- Rangliste: Balken in Klassenfarbe, längster Balken = meister Schaden. Mit onSelect anklickbar. -->
<script lang="ts">
	import { formatCompact, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { playerId, type Player } from '../api.ts';
	import { classColor } from '../classes.ts';
	import PlayerName from './PlayerName.svelte';

	let {
		players,
		selected = null,
		onSelect
	}: { players: (Player & { actor?: number })[]; selected?: string | null; onSelect?: (id: string) => void } = $props();

	const max = $derived(players[0]?.damage || 1);
	const total = $derived(players.reduce((s, p) => s + p.damage, 0) || 1);
</script>

{#snippet body(p: Player, i: number)}
	{@const color = classColor(p.cls)}
	<span class="rank num">{i + 1}</span>
	<PlayerName name={p.name} cls={p.cls} />
	<span class="bar" aria-hidden="true">
		<span style:width="{(100 * p.damage) / max}%" style:background={color} style:box-shadow="0 0 18px -4px {color}"></span>
	</span>
	<span class="value num" title="{formatNumber(p.damage)} {t('logs.skills.col.damage')}">
		{formatCompact(p.damage)}<small>{Math.round((100 * p.damage) / total)} %</small>
	</span>
	<span class="dps num">{formatNumber(p.dps)}<small>/s</small></span>
{/snippet}

<ol class="ranks">
	{#each players as p, i (playerId(p))}
		<li class:selected={selected === playerId(p)}>
			{#if onSelect}
				<button type="button" class="row" aria-pressed={selected === playerId(p)} onclick={() => onSelect(playerId(p))}>
					{@render body(p, i)}
				</button>
			{:else}
				<div class="row">{@render body(p, i)}</div>
			{/if}
		</li>
	{/each}
</ol>

<style>
	.ranks {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.row {
		display: grid;
		grid-template-columns: 26px minmax(110px, 200px) minmax(60px, 1fr) 96px 84px;
		align-items: center;
		gap: 14px;
		width: 100%;
		padding: 8px 10px;
		border-radius: var(--radius-sm);
		border: 1px solid transparent;
		background: none;
		color: var(--text);
		font: inherit;
		text-align: left;
	}
	button.row {
		cursor: pointer;
	}
	button.row:hover {
		background: rgba(255, 255, 255, 0.05);
	}
	.selected .row {
		background: rgba(255, 255, 255, 0.08);
		border-color: var(--edge-soft);
	}
	.rank {
		color: var(--faint);
		font-weight: 600;
		text-align: right;
	}
	.bar {
		display: block;
		height: 12px;
		border-radius: 999px;
		background: rgba(0, 0, 0, 0.35);
		overflow: hidden;
	}
	.bar > span {
		display: block;
		height: 100%;
		border-radius: inherit;
		transition: width 0.4s ease;
	}
	.value,
	.dps {
		text-align: right;
		font-weight: 600;
		white-space: nowrap;
	}
	small {
		margin-left: 6px;
		font-weight: 450;
		color: var(--faint);
	}
	@media (max-width: 720px) {
		.row {
			grid-template-columns: 20px minmax(0, 1fr) 80px;
			grid-template-areas: 'rank name value' 'bar bar bar';
			gap: 6px 10px;
		}
		.rank {
			grid-area: rank;
		}
		.row > :global(.player) {
			grid-area: name;
		}
		.value {
			grid-area: value;
		}
		.bar {
			grid-area: bar;
		}
		.dps {
			display: none;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.bar > span {
			transition: none;
		}
	}
</style>
