<!-- DPS-Verlauf je Spieler in Klassenfarbe; zwei Spieler derselben Klasse: der zweite gestrichelt.
     Breite = echte Breite der Karte, damit die Schrift auf dem Handy nicht mitschrumpft. -->
<script lang="ts">
	import { formatCompact, formatDuration, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { Fight } from '../api.ts';
	import { classColor } from '../classes.ts';

	let { fight, highlight = null }: { fight: Fight; highlight?: string | null } = $props();

	const H = 260;
	const PAD = { l: 56, r: 12, t: 12, b: 28 };
	const SMOOTH_S = 5; // gleitender Mittelwert über 5 Sekunden, sonst zackt jeder Treffer

	let width = $state(900);
	let hover = $state<number | null>(null);
	const W = $derived(Math.max(280, Math.round(width)));

	const series = $derived.by(() => {
		const tl = fight.timeline;
		if (!tl) return [];
		const seen = new Map<string, number>();
		return tl.players.map((s) => {
			const p = fight.players.find((x) => x.actor === s.actor);
			const cls = p?.cls ?? null;
			const nth = seen.get(cls ?? '') ?? 0;
			seen.set(cls ?? '', nth + 1);
			const perSec = s.damage.map((d) => (d * 1000) / tl.bucket_ms);
			const values = perSec.map((_, i) => {
				const win = perSec.slice(Math.max(0, i - SMOOTH_S + 1), i + 1);
				return win.reduce((a, b) => a + b, 0) / win.length;
			});
			return { id: `#${s.actor}`, name: p?.name ?? `#${s.actor}`, color: classColor(cls), dashed: nth > 0, values };
		});
	});

	const bucket = $derived(fight.timeline?.bucket_ms ?? 1000);
	const n = $derived(Math.max(0, ...series.map((s) => s.values.length)));
	const max = $derived(Math.max(1, ...series.flatMap((s) => s.values)));
	const x = (i: number) => PAD.l + (i / Math.max(1, n - 1)) * (W - PAD.l - PAD.r);
	const y = (v: number) => H - PAD.b - (v / max) * (H - PAD.t - PAD.b);
	const yTicks = $derived([0, 0.25, 0.5, 0.75, 1].map((f) => f * max));
	const xTicks = $derived.by(() => {
		const steps = W < 520 ? 3 : 5;
		return Array.from({ length: steps + 1 }, (_, k) => Math.round((k / steps) * (n - 1)));
	});
	const hoverRows = $derived(
		hover === null ? [] : series.map((s) => ({ ...s, v: s.values[hover!] ?? 0 })).sort((a, b) => b.v - a.v)
	);

	function move(e: PointerEvent) {
		const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
		const px = ((e.clientX - box.left) / box.width) * W;
		const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1));
		hover = i >= 0 && i < n ? i : null;
	}
</script>

{#if !series.length}
	<p class="dim">{t('logs.chart.none')}</p>
{:else}
	<figure class="chart" bind:clientWidth={width}>
		<svg viewBox="0 0 {W} {H}" role="img" aria-label={t('logs.chart.label', { d: formatDuration((n - 1) * bucket) })}
			onpointermove={move} onpointerleave={() => (hover = null)}>
			{#each yTicks as v (v)}
				<line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} class="grid" />
				<text x={PAD.l - 8} y={y(v) + 4} text-anchor="end" class="axis">{formatCompact(v)}</text>
			{/each}
			{#each xTicks as i (i)}
				<text x={x(i)} y={H - 8} text-anchor="middle" class="axis">{formatDuration(i * bucket)}</text>
			{/each}
			{#each series as s (s.id)}
				<polyline fill="none" stroke={s.color} stroke-width={highlight === s.id ? 3 : 1.8}
					stroke-dasharray={s.dashed ? '6 4' : undefined} stroke-linejoin="round"
					opacity={highlight && highlight !== s.id ? 0.25 : 1}
					points={s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')} />
			{/each}
			{#if hover !== null}
				<line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} class="cursor" />
			{/if}
		</svg>
		{#if hover !== null}
			<div class="tip glass" style:left="{(x(hover) / W) * 100}%">
				<strong>{formatDuration(hover * bucket)}</strong>
				{#each hoverRows as r (r.id)}
					<span><i style:background={r.color}></i>{r.name}<b class="num">{formatNumber(r.v)}</b></span>
				{/each}
			</div>
		{/if}
		<figcaption class="legend">
			{#each series as s (s.id)}
				<span><i class:dashed={s.dashed} style:background={s.dashed ? 'none' : s.color} style:border-color={s.color}></i>{s.name}</span>
			{/each}
		</figcaption>
	</figure>
{/if}

<style>
	.chart {
		position: relative;
		margin: 0;
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
	.cursor {
		stroke: rgba(255, 255, 255, 0.4);
		stroke-dasharray: 3 3;
	}
	.tip {
		position: absolute;
		top: 8px;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		gap: 3px;
		padding: 10px 12px;
		border-radius: var(--radius-sm);
		font-size: 13px;
		pointer-events: none;
		min-width: 180px;
		background: rgba(12, 14, 28, 0.88);
	}
	.tip span,
	.legend span {
		display: inline-flex;
		align-items: center;
		gap: 8px;
	}
	.tip b {
		margin-left: auto;
		font-weight: 600;
	}
	i {
		width: 10px;
		height: 10px;
		border-radius: 3px;
		flex-shrink: 0;
		border: 2px solid transparent;
	}
	i.dashed {
		border-style: dashed;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 6px 16px;
		margin-top: 10px;
		font-size: 13px;
		color: var(--dim);
	}
</style>
