<!-- DPS über die Zeit: eine Linie je Spieler, Fadenkreuz mit allen Werten beim Überfahren.
     `values` sind DPS je Zeitschritt (`stepMs`), schon geglättet. -->
<script lang="ts">
	import { formatCompact, formatDuration, formatNumber } from '#lib/format.ts';

	type Series = { name: string; color: string; values: number[] };
	let { series, stepMs }: { series: Series[]; stepMs: number } = $props();

	const HEIGHT = 300;
	const M = { l: 64, r: 16, t: 14, b: 30 };
	let width = $state(800);
	let hover = $state<number | null>(null);

	const n = $derived(Math.max(2, ...series.map((s) => s.values.length)));
	const top = $derived(niceMax(Math.max(1, ...series.flatMap((s) => s.values))));
	const plotW = $derived(Math.max(1, width - M.l - M.r));
	const x = (i: number) => M.l + (i / (n - 1)) * plotW;
	const y = (v: number) => M.t + (1 - v / top) * (HEIGHT - M.t - M.b);
	const yTicks = $derived([0, 0.25, 0.5, 0.75, 1].map((f) => f * top));
	const xTicks = $derived.by(() => {
		// So viele Zeitmarken, wie mit gut 60 px Abstand in die Breite passen
		const total = ((n - 1) * stepMs) / 1000;
		const fit = Math.max(2, Math.floor(plotW / 64));
		const step = [10, 15, 30, 60, 120, 300].find((s) => total / s <= fit) ?? 600;
		const out = [];
		for (let t = 0; t <= total; t += step) out.push(t);
		return out;
	});
	// Bei Überfahren: alle Spieler zu dieser Sekunde, höchster Wert zuerst
	const rows = $derived(
		hover == null ? [] : series.map((s) => ({ ...s, v: s.values[hover!] ?? 0 })).sort((a, b) => b.v - a.v)
	);

	function niceMax(v: number): number {
		const p = 10 ** Math.floor(Math.log10(v));
		return ([1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((f) => f * p >= v) ?? 10) * p;
	}

	const path = (values: number[]) =>
		values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');

	function move(e: PointerEvent) {
		const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
		const i = Math.round(((e.clientX - rect.left - M.l) / plotW) * (n - 1));
		hover = i >= 0 && i < n ? i : null;
	}
</script>

<ul class="legend">
	{#each series as s (s.name)}
		<li><span class="swatch" style:background={s.color}></span>{s.name}</li>
	{/each}
</ul>

<div class="chart" bind:clientWidth={width}>
	<svg
		width={width}
		height={HEIGHT}
		role="img"
		aria-label="DPS je Spieler über die Kampfzeit"
		onpointermove={move}
		onpointerleave={() => (hover = null)}
	>
		{#each yTicks as t (t)}
			<line class="grid" x1={M.l} x2={width - M.r} y1={y(t)} y2={y(t)} />
			<text class="axis" x={M.l - 8} y={y(t)} dy="0.32em" text-anchor="end">{formatCompact(t)}</text>
		{/each}
		{#each xTicks as t (t)}
			<text class="axis" x={x((t * 1000) / stepMs)} y={HEIGHT - 8} text-anchor="middle">{formatDuration(t * 1000)}</text>
		{/each}
		{#each series as s (s.name)}
			<path d={path(s.values)} stroke={s.color} />
		{/each}
		{#if hover != null}
			<line class="cross" x1={x(hover)} x2={x(hover)} y1={M.t} y2={HEIGHT - M.b} />
			{#each rows as r (r.name)}
				<circle cx={x(hover)} cy={y(r.v)} r="4" fill={r.color} />
			{/each}
		{/if}
		<!-- Unsichtbare Fläche, damit das Fadenkreuz überall im Diagramm reagiert -->
		<rect x={M.l} y={M.t} width={plotW} height={HEIGHT - M.t - M.b} fill="transparent" />
	</svg>

	{#if hover != null}
		<div class="tip glass" class:left={x(hover) > width * 0.6} style:left="{x(hover)}px">
			<strong>{formatDuration(hover * stepMs)}</strong>
			{#each rows as r (r.name)}
				<div class="tip-row">
					<span class="swatch" style:background={r.color}></span>
					<span class="tip-name">{r.name}</span>
					<span class="tip-v">{formatNumber(Math.round(r.v))}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.legend {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: 6px 16px;
		margin: 0 0 10px;
		padding: 0;
		font-size: 13px;
		color: var(--dim);
	}
	.legend li {
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.swatch {
		width: 10px;
		height: 10px;
		border-radius: 3px;
		flex-shrink: 0;
	}
	.chart {
		position: relative;
		touch-action: pan-y;
	}
	svg {
		display: block;
		overflow: visible;
	}
	path {
		fill: none;
		stroke-width: 2;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.grid {
		stroke: rgba(255, 255, 255, 0.07);
	}
	.axis {
		fill: var(--faint);
		font-size: 11px;
		font-variant-numeric: tabular-nums;
	}
	.cross {
		stroke: rgba(255, 255, 255, 0.35);
		stroke-dasharray: 3 3;
	}
	circle {
		stroke: #0b0d1c;
		stroke-width: 2;
	}
	.tip {
		position: absolute;
		top: 8px;
		transform: translateX(14px);
		min-width: 180px;
		padding: 10px 12px;
		border-radius: 12px;
		pointer-events: none;
		font-size: 13px;
		background: rgba(14, 16, 32, 0.88);
	}
	.tip.left {
		transform: translateX(calc(-100% - 14px));
	}
	.tip strong {
		display: block;
		margin-bottom: 6px;
	}
	.tip-row {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.tip-name {
		flex: 1;
		white-space: nowrap;
	}
	.tip-v {
		font-variant-numeric: tabular-nums;
	}
</style>
