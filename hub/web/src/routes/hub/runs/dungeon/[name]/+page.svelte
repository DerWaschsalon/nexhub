<!-- Modul Logs: ein Dungeon. Schwierigkeit wählen, Kennzahlen im Zeitraum, darunter nur die Runs dieses Dungeons. -->
<script lang="ts">
	import Tabs from '#lib/components/Tabs.svelte';
	import { formatDuration } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import RunRow from '#modules/logs/components/RunRow.svelte';
	import TierLabel from '#modules/logs/components/TierLabel.svelte';
	import { dungeonHref, dungeonHue, killRate, PERIODS, tierName, type Tier } from '#modules/logs/dungeons.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let q = $state('');

	const tierText = (x: Tier) =>
		x.difficulty ? tierName(x.difficulty) : x.only ? t('logs.difficulty.only') : t('logs.difficulty.stage', { n: x.stage });

	const when = $derived(t(`logs.when.${data.period}`));
	const stat = $derived(data.stats.get(data.tier.dungeon_id));
	const rate = $derived(stat ? killRate(stat.kills, stat.wipes) : null);
	const runs = $derived.by(() => {
		const needle = q.trim().toLocaleLowerCase();
		return needle ? data.runs.filter((r) => r.players.some((p) => p.toLocaleLowerCase().includes(needle))) : data.runs;
	});
	const back = $derived(data.period === 'heute' ? '/hub/runs' : `/hub/runs?zeit=${data.period}`);
	const kpis = $derived([
		{ value: String(stat?.runs ?? 0), label: t('logs.dungeons.runs', { when }) },
		{ value: String(stat?.complete ?? 0), label: t('logs.dungeon.complete') },
		{ value: stat?.fastest_ms != null ? formatDuration(stat.fastest_ms) : '–', label: t('logs.dungeons.best'), tone: 'ok' },
		{ value: rate != null ? `${rate} %` : '–', tone: 'accent',
			label: t('logs.dungeon.rateDetail', { k: stat?.kills ?? 0, w: stat?.wipes ?? 0 }) },
		{ value: String(stat?.players ?? 0), label: t('logs.dungeon.players') }
	]);
</script>

<svelte:head><title>{data.group.name} · NexHub</title></svelte:head>

<a class="btn small back" href={back}>← {t('logs.dungeon.back')}</a>

<header class="hero glass" style:--hue={dungeonHue(data.group.name)}>
	<span class="glow" aria-hidden="true"></span>
	<div class="title">
		<span class="kicker">
			{t(data.group.solo ? 'logs.kind.solo' : 'logs.kind.gruppe')} · {t('logs.dungeon.tiers', { n: data.group.tiers.length })}
		</span>
		<h1>{data.group.name}</h1>
	</div>
	<div class="switches">
		{#if data.group.tiers.length > 1}
			<Tabs label={t('logs.dungeon.difficulty')} active={String(data.tier.dungeon_id)}
				tabs={data.group.tiers.map((x) => ({ id: String(x.dungeon_id), label: tierText(x), tier: x,
					href: dungeonHref(data.group.name, data.period, x.dungeon_id) }))}>
				{#snippet tab(x)}
					<TierLabel tier={x.tier} /> <span class="count num">{data.stats.get(x.tier.dungeon_id)?.runs ?? 0}</span>
				{/snippet}
			</Tabs>
		{/if}
		<Tabs label={t('logs.dungeons.period')} active={data.period}
			tabs={PERIODS.map((p) => ({ id: p, label: t(`logs.period.${p}`), href: dungeonHref(data.group.name, p, data.tier.dungeon_id) }))} />
	</div>
</header>

<section class="kpis" aria-label={t('logs.dungeons.count')}>
	{#each kpis as k (k.label)}
		<div class="glass kpi">
			<b class="num" class:ok={k.tone === 'ok'} class:accent={k.tone === 'accent'}>{k.value}</b>
			<small>{k.label}</small>
		</div>
	{/each}
</section>

<section class="list" aria-label={t('logs.list.title')}>
	<div class="list-head">
		<h2>{t('logs.dungeon.list', { tier: '' })}<TierLabel tier={data.tier} /></h2>
		<span class="note">
			{(stat?.runs ?? 0) > data.runs.length
				? t('logs.dungeon.shown', { n: data.runs.length, t: stat?.runs ?? 0, when })
				: t('logs.dungeon.listNote', { n: data.runs.length, when })}
		</span>
		<label class="search">
			<span class="sr-only">{t('logs.dungeon.filter')}</span>
			<input class="input" type="search" bind:value={q} placeholder={t('logs.dungeon.filter')} />
		</label>
	</div>
	{#each runs as run (run.id)}
		<RunRow {run} best={run.complete && run.end_ms - run.start_ms === stat?.fastest_ms} />
	{:else}
		<p class="glass pad empty">{q ? t('logs.list.noMatch') : t('logs.dungeon.empty', { when })}</p>
	{/each}
</section>

<style>
	.back {
		align-self: flex-start;
		margin-bottom: 16px;
	}
	.hero {
		position: relative;
		overflow: hidden;
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		justify-content: space-between;
		gap: 18px;
		padding: 28px;
		border-radius: 20px;
		margin-bottom: 16px;
	}
	.glow {
		position: absolute;
		inset: -60% auto auto -10%;
		width: 520px;
		height: 420px;
		border-radius: 50%;
		pointer-events: none;
		background: radial-gradient(circle, hsl(var(--hue) 90% 62% / 0.3), transparent 65%);
		filter: blur(14px);
	}
	.title,
	.switches {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.switches {
		align-items: flex-end;
	}
	.count {
		opacity: 0.6;
	}
	.kicker {
		font-size: 12px;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--accent);
		font-weight: 600;
	}
	h1 {
		font-size: clamp(26px, 4vw, 36px);
		letter-spacing: -0.02em;
	}
	.kpis {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: 12px;
		margin-bottom: 22px;
	}
	.kpi {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 16px 18px;
		border-radius: 12px;
	}
	.kpi b {
		font-size: 26px;
		font-weight: 600;
	}
	.kpi b.ok {
		color: var(--ok);
	}
	.kpi b.accent {
		color: var(--accent);
	}
	.kpi small {
		font-size: 12px;
		color: var(--faint);
	}
	.list {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.list-head {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 8px 16px;
	}
	h2 {
		font-size: 18px;
		margin: 0;
	}
	.note {
		font-size: 13px;
		color: var(--faint);
	}
	.search {
		margin-left: auto;
	}
	.search .input {
		width: 200px;
		max-width: 100%;
	}
	.empty {
		text-align: center;
		color: var(--dim);
	}
	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
	@media (max-width: 760px) {
		.switches {
			align-items: flex-start;
		}
	}
</style>
