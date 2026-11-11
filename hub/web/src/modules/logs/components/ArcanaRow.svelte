<!-- Arkana als Reihe von Karten (Symbol, Verzauberung, Name); ein Klick meldet die Karte nach oben.
     Im Profil unter „Fortschritt“ (Progression), in den BiS-Listen unter den Skills. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterItem } from '../api.ts';
	import ItemIcon from './ItemIcon.svelte';

	let { arcana, onItem }: { arcana: CharacterItem[]; onItem?: (item: CharacterItem) => void } = $props();
</script>

{#if arcana.length}
	<section>
		<h4>{t('logs.char.arcana')}</h4>
		<div class="row">
			{#each arcana as card (card.slot_name)}
				<button class="arcana" onclick={() => onItem?.(card)}>
					<ItemIcon name={card.name} icon={card.icon} grade={card.grade} size={52} filled />
					<strong>+{card.enchant}</strong>
					<small>{card.name}</small>
				</button>
			{/each}
		</div>
	</section>
{/if}

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
	.arcana {
		flex: 0 0 auto;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		width: 100px;
		padding: 10px 6px;
		background: var(--fill);
		border: 1px solid var(--edge-soft);
		text-align: center;
		color: inherit;
		font: inherit;
		cursor: pointer;
	}
	.arcana strong {
		color: #fff;
	}
	.arcana small {
		font-size: 12px;
		line-height: 1.25;
		color: var(--dim);
	}
</style>
