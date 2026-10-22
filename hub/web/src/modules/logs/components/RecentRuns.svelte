<!-- Übersicht: die neuesten Runs. -->
<script lang="ts">
	import { api } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { RunListItem } from '../api.ts';
	import RunTable from './RunTable.svelte';

	// Nur ein Ausschnitt; alle mit Suche und Filtern stehen unter „Runs“
	const COUNT = 5;
</script>

{#await api<RunListItem[]>(`/api/runs?limit=${COUNT}`) then runs}
	{#if runs.length}
		<div class="table-wrap"><RunTable {runs} /></div>
	{:else}
		<p class="dim">{t('logs.list.empty')}</p>
	{/if}
{:catch e}
	<p class="notice error" role="alert">{e.message}</p>
{/await}
