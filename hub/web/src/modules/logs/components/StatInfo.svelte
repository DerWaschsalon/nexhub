<!-- „Stat Info“ wie im Spiel, kompakt: Reiter Fortschritt (Titel, Daevanion, Arkana), Hauptwerte (Kreis +
     Summen) und Nebenwerte (Summen als Liste). Den Weg zu Best in Slot zeigt das Gegenstandsfenster. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, CharacterItem } from '../api.ts';
	import Progression from './Progression.svelte';
	import StatTotals from './StatTotals.svelte';
	import StatWheel from './StatWheel.svelte';

	let {
		data,
		cls,
		arcana,
		onItem
	}: {
		data: CharacterData;
		cls: string | null;
		arcana: CharacterItem[];
		onItem: (item: CharacterItem) => void;
	} = $props();

	type Tab = 'progression' | 'main' | 'sub';
	const LABELS: Record<Tab, string> = {
		progression: 'logs.char.progression',
		main: 'logs.char.mainStat',
		sub: 'logs.char.subStats'
	};
	const TABS = Object.keys(LABELS) as Tab[];
	let tab: Tab = $state('progression');
</script>

<section class="panel">
	<h3>{t('logs.char.statInfo')}</h3>
	<div class="tab-row" role="tablist">
		{#each TABS as name (name)}
			<button role="tab" aria-selected={tab === name} class:active={tab === name} onclick={() => (tab = name)}>
				{t(LABELS[name])}
			</button>
		{/each}
	</div>
	<div class="body">
		{#if tab === 'progression'}
			<Progression {data} {cls} {arcana} {onItem} />
		{:else if tab === 'main'}
			<StatWheel stats={data.stats} />
			<StatTotals stats={data.stats} />
		{:else}
			<StatTotals stats={data.stats} columns={1} />
		{/if}
	</div>
</section>

<style>
	h3 {
		margin: 0;
		padding: 10px 0 8px;
		text-align: center;
		font-family: var(--font-heading);
		font-size: 20px;
		font-weight: 400;
		color: #fff;
	}
	.tab-row {
		display: grid;
		grid-auto-columns: 1fr;
		grid-auto-flow: column;
		border-top: 1px solid rgba(255, 255, 255, 0.1);
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
	}
	button {
		padding: 8px 6px;
		border: 0;
		border-bottom: 2px solid transparent;
		background: none;
		color: rgba(255, 255, 255, 0.45);
		font: inherit;
		font-size: 13px;
		font-weight: 700;
		cursor: pointer;
	}
	button.active {
		color: #fff;
		border-bottom-color: #c9dcf5;
	}
	.body {
		padding: 0 12px 12px;
	}
</style>
