<!-- „Stat Info“ wie im Spiel: Reiter Hauptwerte (Kreis + Summen), Nebenwerte (Summen als Liste) und
     Fortschritt (Titel, Daevanion, Arkana). -->
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

	const TABS = ['main', 'sub', 'progression'] as const;
	const LABELS = { main: 'logs.char.mainStat', sub: 'logs.char.subStats', progression: 'logs.char.progression' };
	let tab: (typeof TABS)[number] = $state('main');
</script>

<section>
	<h3>{t('logs.char.statInfo')}</h3>
	<div class="tab-row" role="tablist">
		{#each TABS as name (name)}
			<button role="tab" aria-selected={tab === name} class:active={tab === name} onclick={() => (tab = name)}>
				{t(LABELS[name])}
			</button>
		{/each}
	</div>
	<div class="body">
		{#if tab === 'main'}
			<StatWheel stats={data.stats} />
			<StatTotals stats={data.stats} />
		{:else if tab === 'sub'}
			<StatTotals stats={data.stats} columns={1} />
		{:else}
			<Progression {data} {cls} {arcana} {onItem} />
		{/if}
	</div>
</section>

<style>
	section {
		background: linear-gradient(#1c2433, #171e2a);
		border: 1px solid rgba(255, 255, 255, 0.1);
	}
	h3 {
		margin: 0;
		padding: 14px 0 10px;
		text-align: center;
		font-family: Georgia, 'Times New Roman', serif;
		font-size: 28px;
		font-weight: 400;
		color: #fff;
	}
	.tab-row {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		border-top: 1px solid rgba(255, 255, 255, 0.1);
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
	}
	button {
		padding: 14px 6px;
		border: 0;
		border-bottom: 3px solid transparent;
		background: none;
		color: rgba(255, 255, 255, 0.45);
		font: inherit;
		font-size: 16px;
		font-weight: 700;
		cursor: pointer;
	}
	button.active {
		color: #fff;
		border-bottom-color: #c9dcf5;
	}
	.body {
		padding: 0 14px 14px;
	}
</style>
