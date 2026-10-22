<!-- Daevanion wie im Spiel: je Gottheit ein Brett (Raster 15×15), Knoten nach Seltenheit gefärbt,
     freigeschaltete leuchten, Nachbarn sind verbunden. Zeigen oder Antippen nennt den Effekt. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, DaevanionNode } from '../api.ts';
	import { gradeColor } from '../grades.ts';

	let { boards }: { boards: CharacterData['daevanion'] } = $props();

	const CELL = 30;
	const SIZE = 15;
	let chosen = $state(0);
	let focused = $state<DaevanionNode | null>(null);
	const board = $derived(boards[Math.min(chosen, boards.length - 1)]);
	const nodes = $derived(board?.nodes ?? []);
	const at = $derived(new Map(nodes.map((n) => [`${n.row}:${n.col}`, n])));
	// Der Start zählt als offen (NC meldet ihn mit open 0, im Spiel leuchtet er immer)
	const lit = (n: DaevanionNode) => n.open || n.type === 'Start';
	// Ausschnitt auf die belegten Felder, mit einer halben Zelle Rand
	const box = $derived.by(() => {
		const rows = nodes.map((n) => n.row);
		const cols = nodes.map((n) => n.col);
		if (!rows.length) return `0 0 ${SIZE * CELL} ${SIZE * CELL}`;
		const [r0, c0] = [Math.min(...rows) - 1, Math.min(...cols) - 1];
		const [h, w] = [Math.max(...rows) - r0, Math.max(...cols) - c0];
		return `${c0 * CELL - CELL / 2} ${r0 * CELL - CELL / 2} ${(w + 1) * CELL} ${(h + 1) * CELL}`;
	});
	// Verbindungen zu den Nachbarn rechts und unten; leuchtet, wenn beide Enden offen sind
	const links = $derived(
		nodes.flatMap((n) =>
			[at.get(`${n.row}:${n.col + 1}`), at.get(`${n.row + 1}:${n.col}`)]
				.filter((m): m is DaevanionNode => !!m)
				.map((m) => ({ a: n, b: m, lit: lit(n) && lit(m) }))
		)
	);
	const x = (n: DaevanionNode) => (n.col - 0.5) * CELL;
	const y = (n: DaevanionNode) => (n.row - 0.5) * CELL;
	const color = (n: DaevanionNode) => (n.type === 'Start' ? '#f4f5fa' : gradeColor(n.grade, '#9aa0a6'));
	const label = (n: DaevanionNode) =>
		`${t(`logs.char.node.${n.type}`)} · ${n.open ? t('logs.char.node.open') : t('logs.char.node.closed')}` +
		(n.effects.length ? ` · ${n.effects.join(', ')}` : '');

	function pick(i: number) {
		chosen = i;
		focused = null;
	}
</script>

<div class="tabs" role="tablist">
	{#each boards as b, i (b.id)}
		<button type="button" role="tab" class:active={i === chosen} aria-selected={i === chosen} onclick={() => pick(i)}>
			{b.name} <span class="count">{b.open_nodes}/{b.total_nodes}</span>
		</button>
	{/each}
</div>

{#if board}
	<div class="layout">
		{#if nodes.length}
			<svg class="board" viewBox={box} role="img" aria-label={board.name}>
				{#each links as l (`${l.a.row}:${l.a.col}-${l.b.row}:${l.b.col}`)}
					<line x1={x(l.a)} y1={y(l.a)} x2={x(l.b)} y2={y(l.b)} class:lit={l.lit} />
				{/each}
				{#each nodes as n (`${n.row}:${n.col}`)}
					<g
						class="node"
						class:open={lit(n)}
						class:focused={focused === n}
						style:--c={color(n)}
						transform="translate({x(n)} {y(n)})"
						role="button"
						tabindex="0"
						aria-label={label(n)}
						onmouseenter={() => (focused = n)}
						onfocus={() => (focused = n)}
						onclick={() => (focused = n)}
						onkeydown={(e) => e.key === 'Enter' && (focused = n)}
					>
						<title>{label(n)}</title>
						{#if n.type === 'Start'}
							<circle r="12" />
						{:else if n.type === 'SkillLevel'}
							<rect x="-7.5" y="-7.5" width="15" height="15" rx="2" transform="rotate(45)" />
						{:else}
							<circle r="7" />
						{/if}
					</g>
				{/each}
			</svg>
		{/if}

		<div class="side">
			<p class="info" aria-live="polite">
				{#if focused}
					<strong>{t(`logs.char.node.${focused.type}`)}</strong>
					<span class="dim">· {focused.open ? t('logs.char.node.open') : t('logs.char.node.closed')}</span><br />
					{focused.effects.join(', ') || '–'}
				{:else}
					<span class="dim">{t('logs.char.node.hint')}</span>
				{/if}
			</p>
			{#if board.stats.length || board.skills.length}
				<h4>{t('logs.char.board.effects')}</h4>
				<ul class="effects">
					{#each [...board.stats, ...board.skills] as e (e)}<li>{e}</li>{/each}
				</ul>
			{/if}
		</div>
	</div>
{/if}

<style>
	.count {
		color: var(--faint);
		font-weight: 450;
		margin-left: 4px;
	}
	.layout {
		display: grid;
		grid-template-columns: minmax(0, 460px) minmax(0, 1fr);
		gap: 20px;
		margin-top: 12px;
		align-items: start;
	}
	@media (max-width: 820px) {
		.layout {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	.board {
		width: 100%;
		height: auto;
		border-radius: var(--radius-sm);
		background: radial-gradient(circle at 50% 50%, rgba(106, 211, 255, 0.08), rgba(0, 0, 0, 0.35) 70%);
	}
	line {
		stroke: rgba(255, 255, 255, 0.12);
		stroke-width: 2;
	}
	line.lit {
		stroke: rgba(106, 211, 255, 0.55);
		stroke-width: 2.5;
	}
	.node {
		cursor: pointer;
		outline: none;
	}
	.node circle,
	.node rect {
		fill: rgba(5, 6, 13, 0.85);
		stroke: var(--c);
		stroke-width: 2;
		stroke-opacity: 0.4;
		transition: transform 0.15s ease;
	}
	.node.open circle,
	.node.open rect {
		fill: var(--c);
		stroke-opacity: 1;
		filter: drop-shadow(0 0 4px var(--c));
	}
	.node:hover circle,
	.node:hover rect,
	.node.focused circle,
	.node.focused rect,
	.node:focus-visible circle,
	.node:focus-visible rect {
		stroke: #fff;
		stroke-opacity: 1;
		stroke-width: 2.5;
	}
	.info {
		min-height: 3.2em;
		margin-bottom: 14px;
	}
	h4 {
		font-size: 13px;
		color: var(--dim);
		margin-bottom: 8px;
	}
	.effects {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.effects li {
		font-size: 12px;
		padding: 3px 9px;
		border-radius: 999px;
		border: 1px solid var(--edge-soft);
		background: rgba(255, 255, 255, 0.04);
	}
	@media (prefers-reduced-motion: reduce) {
		.node circle,
		.node rect {
			transition: none;
		}
	}
</style>
