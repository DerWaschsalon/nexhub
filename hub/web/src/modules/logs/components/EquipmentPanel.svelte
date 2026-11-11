<!-- Eine Spalte des Charakterfensters (CharacterLayout): die Plätze `slots` untereinander wie im Spiel, leere
     mit ihrem Namen, mit `extras` darunter Flügel und Haustier. Zeigen oder Fokus wählt den Platz (`active`,
     gemeinsam mit der Figur), ein Klick meldet ihn (onPick). Mit `ratings` trägt jeder bewertete Platz seine
     Note in der Ecke. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData } from '../api.ts';
	import type { Rating } from '../rating.ts';
	import ItemIcon from './ItemIcon.svelte';
	import RatingBadge from './RatingBadge.svelte';

	let {
		data,
		slots,
		ratings,
		active = $bindable(null),
		extras = false,
		onPick
	}: {
		data: Pick<CharacterData, 'equipment' | 'wing' | 'pet'>;
		slots: string[];
		ratings?: Map<string, Rating>;
		active?: string | null;
		extras?: boolean;
		onPick: (slot: string) => void;
	} = $props();

	const bySlot = $derived(new Map(data.equipment.map((e) => [e.slot_name, e])));
	// „Brooch1“ → „Brooch“: die Nummer unterscheidet nur die beiden gleichen Plätze
	const slotLabel = (slot: string) => slot.replace(/\d+$/, '');
</script>

<div class="column">
	{#each slots as slot (slot)}
		{@const item = bySlot.get(slot)}
		{#if item}
			<button
				class:lit={active === slot}
				onclick={() => onPick(slot)}
				onmouseenter={() => (active = slot)}
				onfocus={() => (active = slot)}
				aria-label={item.name}
			>
				<ItemIcon name={item.name} icon={item.icon} grade={item.grade} enchant={item.enchant} exceed={item.exceed} size={64} filled />
				{#if ratings?.get(slot)}<span class="note"><RatingBadge letter={ratings.get(slot)!.letter} small /></span>{/if}
			</button>
		{:else}
			<span class="empty">{slotLabel(slot)}</span>
		{/if}
	{/each}
	{#if extras && data.wing}
		<ItemIcon name="{t('logs.char.wing')}: {data.wing.name}" icon={data.wing.icon} grade={data.wing.grade}
			enchant={data.wing.enchant} size={64} filled />
	{/if}
	{#if extras && data.pet}<ItemIcon name="{t('logs.char.pet')}: {data.pet.name}" icon={data.pet.icon} size={64} filled />{/if}
</div>

<style>
	.column {
		display: grid;
		grid-template-columns: 64px;
		gap: 6px;
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
	button.lit,
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
		border-radius: 6px;
		background: var(--fill);
		border: 1px solid var(--fill);
		color: rgba(255, 255, 255, 0.25);
		font-size: 11px;
	}
</style>
