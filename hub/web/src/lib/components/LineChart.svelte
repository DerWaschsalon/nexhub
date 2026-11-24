<!-- Liniendiagramm für den ganzen Hub: eine oder mehrere Linien über gemeinsamen x-Werten, Fadenkreuz mit
     Werten, Legende ab zwei Linien. Breite = echte Breite der Karte, damit die Schrift auf dem Handy nicht
     mitschrumpft. Bedienbar ohne Maus: Das Diagramm ist ein Schieberegler, die Pfeiltasten gehen von Punkt
     zu Punkt, Screenreader lesen die Werte der Stelle vor. -->
<script lang="ts" module>
	/** Eine Linie; `points` sind [x, y]. Alle Linien eines Diagramms teilen sich die x-Werte der längsten. */
	export type Series = { id: string; label: string; color: string; dashed?: boolean; points: [number, number][] };
</script>

<script lang="ts">
	import { domain, linear, nearest, spread } from '#lib/chart.ts';
	import { formatCompact, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';

	let {
		series,
		description,
		title,
		xFormat,
		yFormat = formatNumber,
		yAxisFormat = formatCompact,
		height = 260,
		fromZero = true,
		dots = false,
		highlight = null
	}: {
		series: Series[];
		/** Ein Satz, was das Diagramm zeigt (für Screenreader) */
		description: string;
		title?: string;
		xFormat: (x: number) => string;
		/** Wert im Fadenkreuz */
		yFormat?: (y: number) => string;
		/** Wert an der Achse, darf kürzer sein */
		yAxisFormat?: (y: number) => string;
		height?: number;
		/** y-Achse ab 0; sonst eng um die Werte */
		fromZero?: boolean;
		/** jeden Punkt zeichnen (bei wenigen Punkten) */
		dots?: boolean;
		/** diese Linie hervorheben, die anderen blasser */
		highlight?: string | null;
	} = $props();

	const PAD = { l: 56, r: 14, t: 12, b: 28 };
	const MIN_WIDTH = 240;
	const MAX_DOTS = 60;

	let width = $state(600);
	let hover = $state<number | null>(null);
	const W = $derived(Math.max(MIN_WIDTH, Math.round(width)));

	const longest = $derived(series.reduce((a, b) => (b.points.length > a.points.length ? b : a), series[0]));
	const xs = $derived(longest?.points.map(([px]) => px) ?? []);
	const n = $derived(xs.length);
	const x = $derived(linear([xs[0] ?? 0, xs[n - 1] ?? 0], [PAD.l, W - PAD.r]));
	const range = $derived(domain(series.flatMap((s) => s.points.map(([, py]) => py)), fromZero));
	const y = $derived(linear(range, [height - PAD.b, PAD.t]));
	// niedrige Diagramme bekommen drei Achsenmarken, hohe fünf
	const tickCount = $derived(height < 200 ? 3 : 5);
	const yTicks = $derived(
		Array.from({ length: tickCount }, (_, k) => range[0] + (k / (tickCount - 1)) * (range[1] - range[0]))
	);
	const xTicks = $derived(spread(n, W < 520 ? 3 : 5));
	// Werte aller Linien an der gewählten Stelle, der größte zuerst
	const rows = $derived.by(() => {
		if (hover === null) return [];
		const at = hover;
		const here = series.filter((s) => s.points[at]).map((s) => ({ ...s, value: s.points[at][1] }));
		return here.sort((a, b) => b.value - a.value);
	});
	const readout = $derived(
		hover === null ? '' : `${xFormat(xs[hover])}: ${rows.map((r) => `${r.label} ${yFormat(r.value)}`).join(', ')}`
	);

	function move(e: PointerEvent) {
		const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
		const px = ((e.clientX - box.left) / box.width) * W;
		const at = xs[0] + ((px - PAD.l) / (W - PAD.l - PAD.r)) * (xs[n - 1] - xs[0]);
		hover = nearest(xs, at);
	}

	const KEYS: Record<string, (i: number) => number> = {
		ArrowLeft: (i) => i - 1,
		ArrowRight: (i) => i + 1,
		Home: () => 0,
		End: () => n - 1
	};

	function key(e: KeyboardEvent) {
		if (e.key === 'Escape') hover = null;
		const step = KEYS[e.key];
		if (!step) return;
		e.preventDefault();
		hover = Math.min(n - 1, Math.max(0, step(hover ?? -1)));
	}

	const anchor = (i: number) => (n > 1 && i === 0 ? 'start' : n > 1 && i === n - 1 ? 'end' : 'middle');
</script>

{#if n}
	<figure class="chart" bind:clientWidth={width}>
		{#if title}<figcaption class="title">{title}</figcaption>{/if}
		<div class="plot" role="slider" tabindex="0" aria-label={description} title={t('chart.keys')}
			aria-valuemin={0} aria-valuemax={n - 1} aria-valuenow={hover ?? 0} aria-valuetext={readout || description}
			onpointermove={move} onpointerleave={() => (hover = null)} onkeydown={key} onblur={() => (hover = null)}>
			<svg viewBox="0 0 {W} {height}" aria-hidden="true">
				{#each yTicks as v (v)}
					<line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} class="grid" />
					<text x={PAD.l - 8} y={y(v) + 4} text-anchor="end" class="axis">{yAxisFormat(v)}</text>
				{/each}
				{#each xTicks as i (i)}
					<text x={x(xs[i])} y={height - 8} text-anchor={anchor(i)} class="axis">{xFormat(xs[i])}</text>
				{/each}
				{#each series as s (s.id)}
					{#if s.points.length > 1}
						<polyline fill="none" stroke={s.color} stroke-width={highlight === s.id ? 3 : 2}
							stroke-dasharray={s.dashed ? '6 4' : undefined} stroke-linejoin="round" stroke-linecap="round"
							opacity={highlight && highlight !== s.id ? 0.25 : 1}
							points={s.points.map(([px, py]) => `${x(px).toFixed(1)},${y(py).toFixed(1)}`).join(' ')} />
					{/if}
					{#if dots && s.points.length <= MAX_DOTS}
						{#each s.points as [px, py], i (px)}
							<circle cx={x(px)} cy={y(py)} r={hover === i ? 5 : 4} fill={s.color} class="dot" />
						{/each}
					{/if}
				{/each}
				{#if hover !== null}
					<line x1={x(xs[hover])} x2={x(xs[hover])} y1={PAD.t} y2={height - PAD.b} class="cursor" />
				{/if}
			</svg>
		</div>
		{#if hover !== null}
			<div class="tip glass" style:left="{(x(xs[hover]) / W) * 100}%">
				<strong>{xFormat(xs[hover])}</strong>
				{#each rows as r (r.id)}
					<span>
						{#if series.length > 1}<i style:background={r.color}></i>{r.label}{/if}
						<b class="num">{yFormat(r.value)}</b>
					</span>
				{/each}
			</div>
		{/if}
		{#if series.length > 1}
			<div class="legend">
				{#each series as s (s.id)}
					<span><i class:dashed={s.dashed} style:background={s.dashed ? 'none' : s.color} style:border-color={s.color}></i>{s.label}</span>
				{/each}
			</div>
		{/if}
	</figure>
{/if}

<style>
	.chart {
		position: relative;
		margin: 0;
	}
	.title {
		font-size: 13px;
		color: var(--dim);
		margin-bottom: 6px;
	}
	.plot {
		border-radius: var(--radius-sm);
		touch-action: pan-y;
	}
	svg {
		width: 100%;
		height: auto;
		display: block;
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
		stroke: var(--faint);
		stroke-dasharray: 3 3;
	}
	.tip {
		position: absolute;
		top: 22px;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		gap: 3px;
		padding: 8px 12px;
		border-radius: var(--radius-sm);
		font-size: 13px;
		pointer-events: none;
		white-space: nowrap;
		background: var(--surface);
	}
	.tip strong {
		font-weight: 450;
		color: var(--dim);
	}
	.tip span,
	.legend span {
		display: inline-flex;
		align-items: center;
		gap: 8px;
	}
	.tip b {
		margin-left: auto;
		padding-left: 16px;
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
