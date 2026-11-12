<!-- Übersicht: die drei größten Bewegungen der letzten 24 h auf der eigenen Merkliste, beide Spiele. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import { GAMES, loadWatches, type Game, type PoeWatch, type PoeWatchList } from '../api.ts';
	import { changeColor, formatChange, formatPrice } from '../format.ts';

	const SHOWN = 3;

	type Move = PoeWatch & { game: Game; unit: string | null };

	/** Einträge mit Änderung aus beiden Spielen, die stärkste Bewegung (egal welche Richtung) zuerst */
	function biggest(lists: (PoeWatchList | null)[]): Move[] {
		const moves: Move[] = [];
		GAMES.forEach((game, i) => {
			const list = lists[i];
			if (!list) return;
			for (const w of list.watches) {
				if (w.price !== null && w.change_24h !== null) moves.push({ ...w, game, unit: list.unit });
			}
		});
		moves.sort((a, b) => Math.abs(b.change_24h ?? 0) - Math.abs(a.change_24h ?? 0));
		return moves.slice(0, SHOWN);
	}
</script>

{#await Promise.all(GAMES.map((g) => loadWatches(g))) then lists}
	{@const moves = biggest(lists)}
	{#if lists.every((l) => l === null)}
		<p class="dim">{t('poe.off')}</p>
	{:else if moves.length}
		<ul>
			{#each moves as m (m.id)}
				<li>
					{#if m.icon}<img src={m.icon} alt="" width="28" height="28" referrerpolicy="no-referrer" />{/if}
					<a href="/hub/poe?game={m.game}">{m.name}</a>
					<span class="dim">{t(`poe.game.${m.game}`)}</span>
					<span class="num">{formatPrice(m.price ?? 0, m.unit)}</span>
					<strong class="num" style:color={changeColor(m.change_24h)}>{formatChange(m.change_24h)}</strong>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="dim">{t('poe.noMoves')}</p>
	{/if}
{:catch e}
	<p class="notice error" role="alert">{e.message}</p>
{/await}

<style>
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 10px;
	}
	img {
		object-fit: contain;
	}
	a {
		color: var(--text);
		font-weight: 600;
		text-decoration: none;
	}
	.dim {
		font-size: 13px;
	}
</style>
