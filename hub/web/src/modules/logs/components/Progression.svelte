<!-- Fortschritt: angelegte Titel (Sammlung und Effekte beim Zeigen), Daevanion-Bretter als Ring mit
     Prozent (Klick öffnet das Brett) und die Arkana (ArcanaRow). Jede Gruppe
     eine Reihe, die bei Bedarf umbricht. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, CharacterItem } from '../api.ts';
	import { CHARACTER_ART } from '../assets.ts';
	import { gradeColor } from '../grades.ts';
	import ArcanaRow from './ArcanaRow.svelte';
	import DaevanionBoard from './DaevanionBoard.svelte';
	import Modal from './Modal.svelte';

	let {
		data,
		cls,
		arcana,
		onItem
	}: {
		data: CharacterData;
		cls: string | null;
		arcana: CharacterItem[];
		onItem?: (item: CharacterItem) => void;
	} = $props();

	// Gewähltes Brett im Fenster; im Fenster lässt es sich über die Reiter wechseln
	let showBoard = $state(false);
	let chosen = $state(0);
	function openBoard(i: number) {
		chosen = i;
		showBoard = true;
	}

	const percent = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);
	const titleIcon = (category: string) => `${CHARACTER_ART}/info/title_icon_${category.toLowerCase()}.png`;
</script>

{#if data.titles.equipped.length}
	<section>
		<h4>{t('logs.char.titleGroup')}</h4>
		<div class="row">
			{#each data.titles.equipped as title (title.name)}
				<article class="title" style:--grade={gradeColor(title.grade)}>
					{#if title.category}<img src={titleIcon(title.category)} alt="" width="40" height="40" loading="lazy" referrerpolicy="no-referrer" />{/if}
					<strong>{title.name}</strong>
					{#if title.total}<small>{percent(title.owned ?? 0, title.total)}%</small>{/if}
					<div class="tip" role="tooltip">
						<h5>{title.name}</h5>
						<p><span>{t('logs.char.grade')}</span><b>{title.grade}</b></p>
						{#if title.total}
							<p><span>{t('logs.char.owned')}</span><b>{title.owned}/{title.total} ({percent(title.owned ?? 0, title.total)}%)</b></p>
						{/if}
						{#if title.collection?.length}
							<h6>{t('logs.char.collectionEffect')}</h6>
							{#each title.collection as line, i (i)}<p class="effect">{line}</p>{/each}
						{/if}
						<h6>{t('logs.char.equippedEffect')}</h6>
						{#each title.effects as line, i (i)}<p class="equipped">{line}</p>{/each}
					</div>
				</article>
			{/each}
		</div>
	</section>
{/if}

{#if data.daevanion.length}
	<section>
		<h4>{t('logs.char.daevanion')}</h4>
		<div class="row">
			{#each data.daevanion as board, i (board.id)}
				{@const p = percent(board.open_nodes, board.total_nodes)}
				<button class="board" class:closed={!board.open} onclick={() => openBoard(i)}
					title={t('logs.char.nodes', { o: board.open_nodes, t: board.total_nodes })}>
					<span class="ring" style:--progress="{p}%">
						{#if board.icon}<img src={board.icon} alt="" loading="lazy" referrerpolicy="no-referrer" />{/if}
					</span>
					<strong class="num">{p}%</strong>
					<small>{board.name}</small>
				</button>
			{/each}
		</div>
	</section>

	<Modal open={showBoard} onclose={() => (showBoard = false)} width={980}>
		<div class="board-window">
			<button class="close" onclick={() => (showBoard = false)} aria-label={t('logs.char.close')}>×</button>
			<DaevanionBoard boards={data.daevanion} {cls} bind:chosen />
		</div>
	</Modal>
{/if}

<ArcanaRow {arcana} {onItem} />

<style>
	section {
		margin-bottom: 18px;
	}
	h4 {
		font-size: 15px;
		margin: 0 0 10px;
		color: #fff;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
	}
	article,
	.board {
		flex: 0 0 auto;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		width: 100px;
		padding: 10px 6px;
		background: rgba(255, 255, 255, 0.05);
		border: 1px solid rgba(255, 255, 255, 0.08);
		text-align: center;
		color: inherit;
		font: inherit;
	}
	.title {
		position: relative;
		border-top: 2px solid var(--grade);
		outline: none;
	}
	.title strong,
	.board small {
		font-size: 12px;
		line-height: 1.25;
	}
	small {
		color: var(--dim);
	}
	/* Tooltip wie im Spiel: beim Zeigen auf die Karte darunter */
	.tip {
		display: none;
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
		z-index: 20;
		width: 260px;
		padding: 12px 14px;
		text-align: left;
		background: #141a24;
		border: 1px solid rgba(255, 255, 255, 0.14);
		box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6);
	}
	.title:hover .tip,
	.title:focus-within .tip {
		display: block;
	}
	.tip h5 {
		margin: 0 0 8px;
		font-size: 14px;
		color: var(--grade);
	}
	.tip h6 {
		margin: 10px 0 4px;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--faint);
	}
	.tip p {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		margin: 2px 0;
		font-size: 13px;
	}
	.tip span {
		color: var(--dim);
	}
	.effect {
		color: #3fd6e8;
	}
	.equipped {
		color: #f2d55f;
	}
	.ring {
		display: grid;
		place-items: center;
		width: 52px;
		height: 52px;
		border-radius: 50%;
		background: conic-gradient(#3fd6e8 var(--progress), rgba(255, 255, 255, 0.1) 0);
	}
	.ring img {
		width: 44px;
		height: 44px;
		padding: 7px;
		border-radius: 50%;
		background: #141a24;
		object-fit: contain;
	}
	.closed {
		opacity: 0.45;
	}
	.board {
		cursor: pointer;
	}
	.board-window {
		position: relative;
		padding: 18px;
		background: #1c2432;
		border: 1px solid rgba(255, 255, 255, 0.12);
		box-shadow: 0 16px 50px rgba(0, 0, 0, 0.6);
	}
	.close {
		position: absolute;
		top: 8px;
		right: 10px;
		z-index: 1;
		border: 0;
		background: none;
		color: #fff;
		font-size: 30px;
		line-height: 1;
		cursor: pointer;
	}
</style>
