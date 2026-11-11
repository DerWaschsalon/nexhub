<!-- „Stat Info“ wie im Spiel: Reiter Hauptwerte (Kreis + Summen), Nebenwerte (Summen als Liste),
     Fortschritt (Titel, Daevanion, Arkana) und mit `ratings` Upgrades (Weg zu S+ je Gegenstand). -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, CharacterItem } from '../api.ts';
	import type { Ratings } from '../rating.ts';
	import Progression from './Progression.svelte';
	import StatTotals from './StatTotals.svelte';
	import StatWheel from './StatWheel.svelte';
	import UpgradeList from './UpgradeList.svelte';

	let {
		data,
		cls,
		arcana,
		ratings,
		onItem
	}: {
		data: CharacterData;
		cls: string | null;
		arcana: CharacterItem[];
		ratings?: Ratings | null;
		onItem: (item: CharacterItem) => void;
	} = $props();

	type Tab = 'main' | 'sub' | 'progression' | 'upgrades';
	const LABELS: Record<Tab, string> = {
		main: 'logs.char.mainStat',
		sub: 'logs.char.subStats',
		progression: 'logs.char.progression',
		upgrades: 'logs.rating.upgrades'
	};
	// „Upgrades“ nur, wenn es eine Bewertung gibt
	const tabs = $derived<Tab[]>(ratings ? ['main', 'sub', 'progression', 'upgrades'] : ['main', 'sub', 'progression']);
	let tab: Tab = $state('main');
</script>

<section>
	<h3>{t('logs.char.statInfo')}</h3>
	<div class="tab-row" role="tablist">
		{#each tabs as name (name)}
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
		{:else if tab === 'progression'}
			<Progression {data} {cls} {arcana} {onItem} />
		{:else if ratings}
			<UpgradeList {ratings} equipment={data.equipment} {onItem} />
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
		grid-auto-columns: 1fr;
		grid-auto-flow: column;
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
