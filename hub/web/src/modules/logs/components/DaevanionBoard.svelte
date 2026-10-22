<!-- Daevanion wie im Spiel: je Gottheit ein Brett, Kacheln an ihrer Stelle im Raster 15×15 mit den
     Grafiken der offiziellen Charakterseite (Seltenheit, offen/gesperrt, Start mit Klassensymbol).
     Zeigen oder Antippen nennt den Effekt. Mit `compare` (Brett eines anderen Charakters) sind Knoten
     markiert, die der andere offen hat und dieser noch nicht. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, DaevanionNode } from '../api.ts';
	import { CHARACTER_ART } from '../assets.ts';

	let {
		boards,
		cls,
		compare,
		chosen = $bindable(0)
	}: {
		boards: CharacterData['daevanion'];
		cls: string | null;
		compare?: CharacterData['daevanion'];
		/** gewähltes Brett; beim Vergleich teilen sich beide Bretter die Auswahl */
		chosen?: number;
	} = $props();

	// Grafiken wie auf aion2.plaync.com/characters (static-aion2/characters/css/index.css)
	const ART = `${CHARACTER_ART}/daevanion`;
	// Klassen-Schlüssel des Hubs → Name der Startgrafik
	const START: Record<string, string> = { spiritmaster: 'elementalist', brawler: 'fighter' };

	let focused = $state<DaevanionNode | null>(null);
	const board = $derived(boards[Math.min(chosen, boards.length - 1)]);
	const nodes = $derived(board?.nodes ?? []);
	// Knoten, die der Vergleichs-Charakter auf demselben Brett offen hat
	const openThere = $derived(
		new Set((compare?.find((b) => b.id === board?.id)?.nodes ?? []).filter((n) => n.open).map((n) => `${n.row}:${n.col}`))
	);
	const missing = (n: DaevanionNode) => !n.open && openThere.has(`${n.row}:${n.col}`);
	// Ausschnitt auf die belegten Felder
	const r0 = $derived(Math.min(...nodes.map((n) => n.row)));
	const c0 = $derived(Math.min(...nodes.map((n) => n.col)));
	const rows = $derived(Math.max(...nodes.map((n) => n.row)) - r0 + 1);
	const cols = $derived(Math.max(...nodes.map((n) => n.col)) - c0 + 1);

	const art = (n: DaevanionNode) =>
		n.type === 'Start'
			? `${ART}/board_icon_start_${(cls && START[cls]) || cls || 'fighter'}.png`
			: `${ART}/board_icon_${n.grade.toLowerCase()}${n.open ? '_open' : ''}.png`;
	const label = (n: DaevanionNode) =>
		`${t(`logs.char.node.${n.type}`)} · ${n.open ? t('logs.char.node.open') : t('logs.char.node.closed')}` +
		(n.effects.length ? ` · ${n.effects.join(', ')}` : '');

	function pick(i: number) {
		chosen = i;
		focused = null;
	}
</script>

<div class="daevanion">
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
				<div class="board" style:--rows={rows} style:--cols={cols} role="group" aria-label={board.name}>
					{#each nodes as n (`${n.row}:${n.col}`)}
						<button
							type="button"
							class="node"
							class:open={n.open || n.type === 'Start'}
							class:focused={focused === n}
							class:missing={missing(n)}
							style:grid-row={n.row - r0 + 1}
							style:grid-column={n.col - c0 + 1}
							title={label(n)}
							aria-label={label(n)}
							onmouseenter={() => (focused = n)}
							onfocus={() => (focused = n)}
							onclick={() => (focused = n)}
						>
							<img src={art(n)} alt="" referrerpolicy="no-referrer" />
						</button>
					{/each}
				</div>
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
</div>

<style>
	/* richtet sich nach der eigenen Breite, damit zwei Bretter nebeneinander passen */
	.daevanion {
		container-type: inline-size;
	}
	.count {
		color: var(--faint);
		font-weight: 450;
		margin-left: 4px;
	}
	.layout {
		display: grid;
		grid-template-columns: minmax(0, 520px) minmax(0, 1fr);
		gap: 20px;
		margin-top: 12px;
		align-items: start;
	}
	@container (max-width: 820px) {
		.layout {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	/* wie die offizielle Seite: 140er Kacheln mit 10er Abstand, hier auf die Breite skaliert */
	.board {
		display: grid;
		grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
		grid-template-rows: repeat(var(--rows), auto);
		gap: clamp(2px, 0.7vw, 8px);
		padding: clamp(6px, 1.5vw, 14px);
		border-radius: var(--radius-sm);
		background: #111315;
	}
	.node {
		display: block;
		aspect-ratio: 1;
		padding: 0;
		border: 0;
		background: none;
		cursor: pointer;
		opacity: 0.5;
		transition: transform 0.1s ease-in-out;
	}
	.node.open {
		opacity: 1;
	}
	.node.missing {
		opacity: 0.9;
		outline: 2px solid var(--danger);
		outline-offset: -2px;
		border-radius: 10px;
	}
	.node img {
		display: block;
		width: 100%;
		height: 100%;
	}
	.node:hover,
	.node.focused,
	.node:focus-visible {
		transform: scale(1.12);
		position: relative;
		z-index: 1;
		outline: none;
		filter: drop-shadow(0 0 6px rgba(106, 211, 255, 0.7));
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
		.node {
			transition: none;
		}
	}
</style>
