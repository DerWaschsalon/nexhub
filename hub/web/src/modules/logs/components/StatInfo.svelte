<!-- „Stat Info“ wie im Spiel, kompakt: Reiter Fortschritt (Titel, Daevanion, Arkana), Hauptwerte (Kreis +
     Summen) und Nebenwerte (Summen als Liste). Den Weg zu Best in Slot zeigt das Gegenstandsfenster. -->
<script lang="ts">
	import Tabs from '#lib/components/Tabs.svelte';
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
	<Tabs underline tabs={TABS.map((id) => ({ id, label: t(LABELS[id]) }))} active={tab}
		onselect={(id) => (tab = id as Tab)} />
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
	.body {
		padding: 0 12px 12px;
	}
</style>
