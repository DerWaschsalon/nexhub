<!-- Verlauf eines Werts je Tag als eine Linie (Armory: Kampfkraft, Item-Level; Statistik: Zählungen). -->
<script lang="ts" module>
	/** Ein Tag (ISO-Datum) mit Wert; Tage ohne Wert (null) fallen weg. */
	export type DayValue = { day: string; value: number | null };
</script>

<script lang="ts">
	import { formatNumber } from '#lib/format.ts';
	import { i18n } from '#lib/i18n.svelte.ts';
	import LineChart from './LineChart.svelte';

	let {
		title,
		days,
		color,
		fromZero = false
	}: {
		title: string;
		days: DayValue[];
		color: string;
		/** Zählungen beginnen bei 0; Werte, die sich nur wenig ändern, zeigt die Achse eng um die Werte */
		fromZero?: boolean;
	} = $props();

	const known = $derived(days.filter((d) => d.value !== null));
	const points = $derived(known.map((d, i): [number, number] => [i, d.value as number]));
	const dayLabel = (i: number) =>
		new Date(`${known[i].day}T00:00:00Z`).toLocaleDateString(i18n.lang, { day: 'numeric', month: 'short', timeZone: 'UTC' });
</script>

{#if points.length}
	<LineChart {title} series={[{ id: title, label: title, color, points }]} xFormat={dayLabel} height={150}
		{fromZero} dots
		description="{title}: {formatNumber(points[0][1])} → {formatNumber(points[points.length - 1][1])}" />
{/if}
