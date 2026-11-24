<!-- Ein Charakter der Armory: Ansicht wie im Spiel (CharacterSheet), im Kopf der Verlauf. -->
<script lang="ts">
	import DayChart from '#lib/components/DayChart.svelte';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import { classColor, classFromName } from '#modules/logs/classes.ts';
	import CharacterSheet from '#modules/logs/components/CharacterSheet.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const c = $derived(data.character);
	const cls = $derived(c.cls ?? classFromName(c.class_name));
</script>

{#if c.data}
	<CharacterSheet character={{ ...c, cls }} data={c.data} source={t('armory.source')} ratings={c.ratings[i18n.lang] ?? c.ratings.en}>
		{#snippet aside()}
			{#if c.days.length}
				<div class="charts">
					<DayChart title={t('logs.char.combatPower')} days={c.days.map((d) => ({ day: d.day, value: d.combat_power }))} color={classColor(cls)} />
					<DayChart title={t('logs.char.itemLevel')} days={c.days.map((d) => ({ day: d.day, value: d.item_level }))} color={classColor(cls)} />
				</div>
				{#if c.days.length === 1}<p class="dim small">{t('armory.historyStart')}</p>{/if}
			{/if}
		{/snippet}
	</CharacterSheet>
{:else if c.status !== 'offen'}
	<section class="glass pad">
		<h2>{c.name}</h2>
		<p>
			{c.status === 'nicht_gefunden'
				? t('logs.char.notFound', { why: c.error ?? '' })
				: t('logs.char.error', { why: c.error ?? '' })}
		</p>
	</section>
{/if}

<style>
	h2 {
		font-size: 17px;
		margin-bottom: 10px;
	}
	.charts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 14px;
	}
	.small {
		font-size: 12px;
		margin-top: 8px;
	}
</style>
