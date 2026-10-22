<!-- Übersicht: die eigenen Charaktere aus der Armory. -->
<script lang="ts">
	import { api } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { ArmoryItem } from '../api.ts';
	import CharacterGrid from './CharacterGrid.svelte';

	// Die API liefert alle Charaktere im Hub, hier zählen nur die eigenen
	const mine = (characters: ArmoryItem[]) => characters.filter((c) => c.mine);
</script>

{#await api<ArmoryItem[]>('/api/armory') then characters}
	{#if mine(characters).length}
		<CharacterGrid characters={mine(characters)} />
	{:else}
		<p class="dim">{t('armory.mineNone')}</p>
	{/if}
{:catch e}
	<p class="notice error" role="alert">{e.message}</p>
{/await}
