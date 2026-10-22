<!-- Verlauf einer Kennzahl je Tag (Kampfkraft oder Item-Level), eine Linie in der Klassenfarbe.
     Aufbau wie modules/logs/components/DpsChart.svelte: echte Kartenbreite, Fadenkreuz mit Tooltip. -->
<script lang="ts">
	import { formatCompact, formatNumber } from '#lib/format.ts';
	import { i18n } from '#lib/i18n.svelte.ts';
	import type { ArmoryDay } from '../api.ts';

	let { title, days, key, color }: { title: string; days: ArmoryDay[]; key: 'combat_power' | 'item_level'; color: string } =
		$props();

	const H = 150;
	const PAD = { l: 56, r: 14, t: 12, b: 26 };

	let width = $state(420);
	let hover = $state<number | null>(null);
	const W = $derived(Math.max(240, Math.round(width)));

	const points = $derived(days.filter((d) => d[key] !== null).map((d) => ({ day: d.day, v: d[key] as number })));
	const n = $derived(points.length);
	// Keine Null-Linie: die Werte ändern sich von Tag zu Tag um wenige Prozent, ab 0 wäre alles flach
	const lo = $derived(Math.min(...points.map((p) => p.v)));
	const hi = $derived(Math.max(...points.map((p) => p.v)));
	const span = $derived(hi - lo || Math.max(1, hi * 0.02));
	const min = $derived(lo - span * 0.15);
	const max = $derived(hi + span * 0.15);
	const x = (i: number) => (n === 1 ? (PAD.l + W - PAD.r) / 2 : PAD.l + (i / (n - 1)) * (W - PAD.l - PAD.r));
	const y = (v: number) => H - PAD.b - ((v - min) / (max - min)) * (H - PAD.t - PAD.b);
	const yTicks = $derived([0, 0.5, 1].map((f) => min + f * (max - min)));
	const xTicks = $derived.by(() => {
		if (n <= 1) return n ? [0] : [];
		const steps = Math.min(n - 1, W < 360 ? 2 : 4);
		return [...new Set(Array.from({ length: steps + 1 }, (_, k) => Math.round((k / steps) * (n - 1))))];
	});
	const dayLabel = (iso: string) =>
		new Date(`${iso}T00:00:00Z`).toLocaleDateString(i18n.lang, { day: 'numeric', month: 'short', timeZone: 'UTC' });

	function move(e: PointerEvent) {
		const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
		const px = ((e.clientX - box.left) / box.width) * W;
		hover = n === 1 ? 0 : Math.min(n - 1, Math.max(0, Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1))));
	}
</script>

{#if n}
	<figure class="chart" bind:clientWidth={width}>
		<figcaption>{title}</figcaption>
		<svg viewBox="0 0 {W} {H}" role="img" aria-label="{title}: {formatNumber(points[0].v)} → {formatNumber(points[n - 1].v)}"
			onpointermove={move} onpointerleave={() => (hover = null)}>
			{#each yTicks as v (v)}
				<line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} class="grid" />
				<text x={PAD.l - 8} y={y(v) + 4} text-anchor="end" class="axis">{formatCompact(v)}</text>
			{/each}
			{#each xTicks as i (i)}
				<text x={x(i)} y={H - 6} class="axis"
					text-anchor={n > 1 && i === 0 ? 'start' : n > 1 && i === n - 1 ? 'end' : 'middle'}>{dayLabel(points[i].day)}</text>
			{/each}
			{#if n > 1}
				<polyline fill="none" stroke={color} stroke-width="2" stroke-linejoin="round" stroke-linecap="round"
					points={points.map((p, i) => `${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')} />
			{/if}
			{#if n <= 60}
				{#each points as p, i (p.day)}
					<circle cx={x(i)} cy={y(p.v)} r={hover === i ? 5 : 4} fill={color} class="dot" />
				{/each}
			{/if}
			{#if hover !== null}
				<line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} class="cursor" />
			{/if}
		</svg>
		{#if hover !== null}
			<div class="tip glass" style:left="{(x(hover) / W) * 100}%">
				<span class="dim">{dayLabel(points[hover].day)}</span>
				<b class="num">{formatNumber(points[hover].v)}</b>
			</div>
		{/if}
	</figure>
{/if}

<style>
	.chart {
		position: relative;
		margin: 0;
	}
	figcaption {
		font-size: 13px;
		color: var(--dim);
		margin-bottom: 6px;
	}
	svg {
		width: 100%;
		height: auto;
		display: block;
		touch-action: pan-y;
	}
	.grid {
		stroke: var(--edge-soft);
	}
	.axis {
		fill: var(--faint);
		font-size: 11px;
	}
	.dot {
		stroke: var(--bg);
		stroke-width: 2;
	}
	.cursor {
		stroke: rgba(255, 255, 255, 0.4);
		stroke-dasharray: 3 3;
	}
	.tip {
		position: absolute;
		top: 22px;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 8px 10px;
		border-radius: var(--radius-sm);
		font-size: 13px;
		pointer-events: none;
		white-space: nowrap;
		background: rgba(12, 14, 28, 0.88);
	}
	.tip b {
		font-weight: 600;
	}
</style>
