<!-- Fenster für einen Gegenstand (ItemTooltip). Offen, solange `item` gesetzt ist; mit `ratings` samt
     Bewertung des Platzes. -->
<script lang="ts">
	import type { CharacterItem } from '../api.ts';
	import type { Rating } from '../rating.ts';
	import ItemTooltip from './ItemTooltip.svelte';
	import Modal from './Modal.svelte';

	let { item = $bindable(), ratings }: { item: CharacterItem | null; ratings?: Map<string, Rating> } = $props();
	const close = () => (item = null);
</script>

<Modal open={item !== null} onclose={close}>
	{#if item}<ItemTooltip {item} rating={ratings?.get(item.slot_name)} onclose={close} />{/if}
</Modal>
