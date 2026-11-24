<!-- DPS-Verlauf je Spieler in Klassenfarbe; zwei Spieler derselben Klasse: der zweite gestrichelt.
     Breite = echte Breite der Karte, damit die Schrift auf dem Handy nicht mitschrumpft. -->
<script lang="ts">
	import LineChart, { type Series } from '#lib/components/LineChart.svelte';
	import { formatDuration } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { Fight } from '../api.ts';
	import { classColor } from '../classes.ts';

	let { fight, highlight = null }: { fight: Fight; highlight?: string | null } = $props();

	const SMOOTH_S = 5; // gleitender Mittelwert über 5 Sekunden, sonst zackt jeder Treffer

	const bucket = $derived(fight.timeline?.bucket_ms ?? 1000);
	const series = $derived.by((): Series[] => {
		const tl = fight.timeline;
		if (!tl) return [];
		const seen = new Map<string, number>();
		return tl.players.map((s) => {
			const p = fight.players.find((x) => x.actor === s.actor);
			const cls = p?.cls ?? null;
			const nth = seen.get(cls ?? '') ?? 0;
			seen.set(cls ?? '', nth + 1);
			const perSec = s.damage.map((d) => (d * 1000) / tl.bucket_ms);
			const points = perSec.map((_, i): [number, number] => {
				const win = perSec.slice(Math.max(0, i - SMOOTH_S + 1), i + 1);
				return [i * tl.bucket_ms, win.reduce((a, b) => a + b, 0) / win.length];
			});
			return { id: `#${s.actor}`, label: p?.name ?? `#${s.actor}`, color: classColor(cls), dashed: nth > 0, points };
		});
	});
	const duration = $derived(Math.max(0, ...series.map((s) => s.points.length - 1)) * bucket);
</script>

{#if !series.length}
	<p class="dim">{t('logs.chart.none')}</p>
{:else}
	<LineChart {series} {highlight} xFormat={formatDuration}
		description={t('logs.chart.label', { d: formatDuration(duration) })} />
{/if}
