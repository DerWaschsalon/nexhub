<!-- Fenster für einen Gegenstand (ItemTooltip). Offen, solange `item` gesetzt ist. -->
<script lang="ts">
	import type { CharacterItem } from '../api.ts';
	import ItemTooltip from './ItemTooltip.svelte';
	import Modal from './Modal.svelte';

	let { item = $bindable() }: { item: CharacterItem | null } = $props();
	const close = () => (item = null);
</script>

<Modal open={item !== null} onclose={close}>
	{#if item}<ItemTooltip {item} onclose={close} />{/if}
</Modal>
