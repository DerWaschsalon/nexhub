<!-- Ausrüstungsspalte wie im Spiel: zwei Spalten in der Reihenfolge des Ausrüstungsfensters, leere
     Plätze mit ihrem Namen, unten Flügel und Haustier. Ein Klick meldet den Gegenstand nach oben (onItem).
     Mit `ratings` trägt jeder bewertete Platz seine Note in der Ecke. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, CharacterItem } from '../api.ts';
	import type { Rating } from '../rating.ts';
	import { GAME_ORDER } from '../slots.ts';
	import ItemIcon from './ItemIcon.svelte';
	import RatingBadge from './RatingBadge.svelte';

	let {
		data,
		ratings,
		onItem
	}: {
		data: Pick<CharacterData, 'equipment' | 'wing' | 'pet'>;
		ratings?: Map<string, Rating>;
		onItem: (item: CharacterItem) => void;
	} = $props();

	const bySlot = $derived(new Map(data.equipment.map((e) => [e.slot_name, e])));
	// „Brooch1“ → „Brooch“: die Nummer unterscheidet nur die beiden gleichen Plätze
	const slotLabel = (slot: string) => slot.replace(/\d+$/, '');
</script>

<aside>
	<div class="crest" aria-hidden="true">✦</div>
	<div class="grid">
		{#each GAME_ORDER as slot (slot)}
			{@const item = bySlot.get(slot)}
			{#if item}
				<button onclick={() => onItem(item)} aria-label={item.name}>
					<ItemIcon name={item.name} icon={item.icon} grade={item.grade} enchant={item.enchant} exceed={item.exceed} size={64} filled />
					{#if ratings?.get(slot)}<span class="note"><RatingBadge letter={ratings.get(slot)!.letter} small /></span>{/if}
				</button>
			{:else}
				<span class="empty">{slotLabel(slot)}</span>
			{/if}
		{/each}
	</div>
	{#if data.wing || data.pet}
		<div class="grid extra">
			{#if data.wing}
				<ItemIcon name="{t('logs.char.wing')}: {data.wing.name}" icon={data.wing.icon} grade={data.wing.grade}
					enchant={data.wing.enchant} size={64} filled />
			{/if}
			{#if data.pet}<ItemIcon name="{t('logs.char.pet')}: {data.pet.name}" icon={data.pet.icon} size={64} filled />{/if}
		</div>
	{/if}
</aside>

<style>
	aside {
		padding: 0 12px 14px;
		background: linear-gradient(#1a2130, #141a25);
		border: 1px solid rgba(255, 255, 255, 0.12);
	}
	.crest {
		display: grid;
		place-items: center;
		height: 64px;
		margin-bottom: 12px;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		font-size: 26px;
		color: #e8fbff;
		text-shadow: 0 0 10px #7fe6ff;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, 64px);
		gap: 5px;
		justify-content: center;
	}
	.extra {
		margin-top: 12px;
		padding-top: 12px;
		border-top: 1px solid rgba(255, 255, 255, 0.1);
	}
	button {
		position: relative;
		padding: 0;
		border: 0;
		background: none;
		cursor: pointer;
		line-height: 0;
	}
	button:hover,
	button:focus-visible {
		filter: brightness(1.2);
		outline: 1px solid #fff;
	}
	.note {
		position: absolute;
		top: 2px;
		right: 2px;
		line-height: 1;
	}
	.empty {
		display: grid;
		place-items: center;
		width: 64px;
		height: 64px;
		background: rgba(255, 255, 255, 0.03);
		border: 1px solid rgba(255, 255, 255, 0.06);
		color: rgba(255, 255, 255, 0.18);
		font-size: 11px;
	}
</style>
