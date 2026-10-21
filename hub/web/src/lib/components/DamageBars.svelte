<!-- Schaden je Spieler als Balken in Klassenfarbe, längster Balken = 100 %. -->
<script lang="ts">
	import type { RunPlayer } from '#lib/api.ts';
	import { CLASS_LABELS, classColor } from '#lib/classes.ts';
	import { formatNumber } from '#lib/format.ts';

	let { players }: { players: RunPlayer[] } = $props();
	const top = $derived(Math.max(1, ...players.map((p) => p.damage)));
	const total = $derived(players.reduce((sum, p) => sum + p.damage, 0) || 1);
</script>

<ol class="bars">
	{#each players as p (p.name + p.cls)}
		<li title={p.cls ? CLASS_LABELS[p.cls] : ''}>
			<span class="fill" style:width="{(p.damage / top) * 100}%" style:--c={classColor(p.cls)}></span>
			<span class="name">{p.name}</span>
			<span class="nums">
				<b>{formatNumber(p.dps)}</b> DPS
				<span class="dim">· {formatNumber(p.damage)} · {Math.round((p.damage / total) * 100)} %</span>
			</span>
		</li>
	{/each}
</ol>

<style>
	.bars {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	li {
		position: relative;
		display: flex;
		justify-content: space-between;
		gap: 12px;
		padding: 8px 12px;
		border-radius: 10px;
		background: rgba(255, 255, 255, 0.04);
		overflow: hidden;
		font-size: 14px;
	}
	.fill {
		position: absolute;
		inset: 0 auto 0 0;
		background: linear-gradient(90deg, color-mix(in srgb, var(--c) 45%, transparent), color-mix(in srgb, var(--c) 15%, transparent));
		border-right: 2px solid var(--c);
	}
	.name,
	.nums {
		position: relative;
		white-space: nowrap;
	}
	.name {
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.nums {
		font-variant-numeric: tabular-nums;
	}
	@media (max-width: 520px) {
		.nums .dim {
			display: none;
		}
	}
</style>
