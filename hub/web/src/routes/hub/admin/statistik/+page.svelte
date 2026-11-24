<!-- Statistik für Admins: Summen als Kacheln, Runs und neue Konten je Tag als Verlauf, darunter die
     NexBoards nach Version und der BiS-Bestand je Klasse. Gezählt aus den vorhandenen Tabellen. -->
<script lang="ts">
	import DayChart from '#lib/components/DayChart.svelte';
	import { formatDateTime, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import { classInfo } from '#modules/logs/classes.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const s = $derived(data.stats);
	const series = (values: number[]) => s.days.map((day, i) => ({ day, value: values[i] }));
	const versions = $derived(Object.entries(s.devices_by_version).sort(([a], [b]) => b.localeCompare(a)));
</script>

<svelte:head><title>{t('stats.title')} · NexHub</title></svelte:head>

<header class="page-head">
	<h1>{t('stats.title')}</h1>
	<p>{t('stats.intro')}</p>
</header>

<section class="tiles">
	<div class="glass pad tile"><span class="label">{t('stats.runs')}</span><strong class="num">{formatNumber(s.total_runs)}</strong></div>
	<div class="glass pad tile"><span class="label">{t('stats.accounts')}</span><strong class="num">{formatNumber(s.total_accounts)}</strong></div>
	<div class="glass pad tile"><span class="label">{t('stats.characters')}</span><strong class="num">{formatNumber(s.characters)}</strong></div>
	<div class="glass pad tile">
		<span class="label">{t('stats.devices')}</span>
		<strong class="num">{formatNumber(s.devices)}</strong>
		<span class="dim">{t('stats.devicesActive', { n: s.devices_active, days: s.days.length })}</span>
	</div>
</section>

<section class="charts">
	<div class="glass pad"><DayChart title={t('stats.runsPerDay')} days={series(s.runs)} color="var(--accent)" fromZero /></div>
	<div class="glass pad"><DayChart title={t('stats.accountsPerDay')} days={series(s.accounts)} color="var(--game-green)" fromZero /></div>
</section>

<section class="tables">
	<div class="glass pad">
		<h2>{t('stats.versions')}</h2>
		<table class="table">
			<thead><tr><th>{t('stats.col.version')}</th><th class="right">{t('stats.col.count')}</th></tr></thead>
			<tbody>
				{#each versions as [version, count] (version)}
					<tr><td>{version}</td><td class="right num">{count}</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
	<div class="glass pad">
		<h2>{t('stats.bis')}</h2>
		<table class="table">
			<thead>
				<tr><th>{t('stats.col.class')}</th><th class="right">{t('stats.col.players')}</th><th class="right">{t('stats.col.counted')}</th></tr>
			</thead>
			<tbody>
				{#each s.bis as pool (pool.cls)}
					<tr>
						<td>{classInfo(pool.cls)?.label ?? pool.cls}</td>
						<td class="right num">{pool.players}</td>
						<td class="right dim">{pool.counted_at ? formatDateTime(pool.counted_at) : t('stats.never')}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>

<style>
	section {
		margin-bottom: 14px;
	}
	.charts,
	.tables {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
		gap: 14px;
	}
	h2 {
		font-size: 17px;
		margin: 0 0 10px;
	}
</style>
