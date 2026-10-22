<!-- Armory-Charaktere als Raster aus Karten. In der Armory und in der Übersicht. -->
<script lang="ts">
	import type { ArmoryItem } from '../api.ts';
	import CharacterCard from './CharacterCard.svelte';

	let { characters }: { characters: ArmoryItem[] } = $props();
</script>

<div class="grid">
	{#each characters as c (c.id)}<CharacterCard {c} />{/each}
</div>

<style>
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 12px;
	}
</style>
