<!-- Werte-Kreis wie im Spiel: innen die sechs Grundwerte, außen die zehn Lord-Werte, Speichen und
     ein leuchtender Kern. Lage aus stats.ts (WHEEL_*); die Einzel-Effekte stehen im Tooltip. -->
<script lang="ts">
	import type { CharacterData } from '../api.ts';
	import { WHEEL, WHEEL_BASE, WHEEL_LORDS, WHEEL_SPOKES, splitLord, statIcon } from '../stats.ts';

	type Stat = CharacterData['stats'][number];
	type Placed = { stat: Stat; left: number; top: number };

	let { stats }: { stats: CharacterData['stats'] } = $props();

	const CX = WHEEL.width / 2;
	const CY = WHEEL.height / 2;
	const SPOKE_LENGTH = 420;

	/** Werte an ihre feste Stelle setzen (in Prozent der Fläche); fehlende fallen weg */
	function place(layout: [string, number, number][]): Placed[] {
		const byType = new Map(stats.map((s) => [s.type, s]));
		const placed: Placed[] = [];
		for (const [type, x, y] of layout) {
			const stat = byType.get(type);
			if (stat) placed.push({ stat, left: (x / WHEEL.width) * 100, top: (y / WHEEL.height) * 100 });
		}
		return placed;
	}

	function spokeEnd(deg: number): { x: number; y: number } {
		const rad = (deg * Math.PI) / 180;
		return { x: CX + SPOKE_LENGTH * Math.cos(rad), y: CY + SPOKE_LENGTH * Math.sin(rad) };
	}

	const lords = $derived(place(WHEEL_LORDS));
	const base = $derived(place(WHEEL_BASE));
	const tooltip = (s: Stat) => [s.name, ...s.effects].join('\n');
</script>

<div class="wheel" style:aspect-ratio="{WHEEL.width} / {WHEEL.height}">
	<svg viewBox="0 0 {WHEEL.width} {WHEEL.height}" aria-hidden="true">
		<defs>
			<radialGradient id="wheel-core">
				<stop offset="0" stop-color="#e8fbff" />
				<stop offset="0.25" stop-color="#7fe6ff" stop-opacity="0.8" />
				<stop offset="1" stop-color="#3fd6e8" stop-opacity="0" />
			</radialGradient>
		</defs>
		{#each WHEEL_SPOKES as deg (deg)}
			{@const end = spokeEnd(deg)}
			<line x1={CX} y1={CY} x2={end.x} y2={end.y} />
		{/each}
		<circle cx={CX} cy={CY} r={WHEEL.outerRadius} />
		<circle cx={CX} cy={CY} r={WHEEL.innerRadius} />
		<circle class="core" cx={CX} cy={CY} r="16" />
	</svg>

	{#each lords as p (p.stat.type)}
		<div class="pos lord" style:left="{p.left}%" style:top="{p.top}%" title={tooltip(p.stat)}>
			<img src={statIcon(p.stat.type)} alt={splitLord(p.stat.name).name} loading="lazy" referrerpolicy="no-referrer" />
			<strong class="num">{p.stat.value}</strong>
		</div>
	{/each}

	{#each base as p (p.stat.type)}
		<div class="pos base" style:left="{p.left}%" style:top="{p.top}%" title={tooltip(p.stat)}>
			<img src={statIcon(p.stat.type)} alt="" loading="lazy" referrerpolicy="no-referrer" />
			<span>{p.stat.name}</span>
			<strong class="num">{p.stat.value}</strong>
		</div>
	{/each}
</div>

<style>
	.wheel {
		position: relative;
		width: 100%;
		overflow: hidden;
		container-type: inline-size;
	}
	svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		fill: none;
		stroke: rgba(160, 190, 220, 0.16);
		stroke-width: 2;
	}
	svg .core {
		fill: url(#wheel-core);
		stroke: none;
	}
	/* Der Punkt im Layout ist die Mitte der Zahl; Symbol und Name stehen darüber */
	.pos {
		position: absolute;
		transform: translate(-50%, calc(-100% + 1.6cqw));
		display: flex;
		flex-direction: column;
		align-items: center;
		line-height: 1.15;
		cursor: default;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
	}
	strong {
		color: #fff;
		font-size: max(13px, 2.7cqw);
		font-weight: 700;
	}
	.lord img {
		width: max(26px, 5.4cqw);
		height: max(26px, 5.4cqw);
		object-fit: contain;
		opacity: 0.75;
		margin-bottom: 0.6cqw;
	}
	.base img {
		width: max(20px, 4cqw);
		height: max(20px, 4cqw);
		object-fit: contain;
		opacity: 0.45;
		margin-bottom: 0.4cqw;
	}
	.base span {
		color: #3fd6e8;
		font-weight: 700;
		font-size: max(12px, 2.7cqw);
		white-space: nowrap;
		text-shadow: 0 0 8px rgba(63, 214, 232, 0.35), 0 1px 3px rgba(0, 0, 0, 0.8);
	}
</style>
