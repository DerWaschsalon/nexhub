<!-- Übersicht (Startseite), Kachel Runs: nur der heutige Tag. Zahlen des Tages, beste Parses der Gilde, heute
     gespielte Dungeons und die Runs von heute. Alles Ältere steht unter „Runs“ (Zeitraum Woche oder Alle). -->
<script lang="ts">
	import { api } from '#lib/api.ts';
	import type { LegionsOut, TopParse } from '#lib/api-types.ts';
	import { formatDuration } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import ParseValue from '#modules/parses/components/ParseValue.svelte';
	import type { RunListItem } from '../api.ts';
	import { classInfo } from '../classes.ts';
	import { dungeonHref, dungeonHue, groupDungeons, killRate, sinceMs, type DungeonStat } from '../dungeons.ts';
	import RunRow from './RunRow.svelte';

	const TOP = 6;
	const since = sinceMs('heute')!;
	// Parses und Legion sind ein eigenes Modul: fehlen sie, bleibt die Kachel ohne
	const optional = <T,>(p: Promise<T>) => p.catch(() => null);

	const load = Promise.all([
		api<RunListItem[]>(`/api/runs?since_ms=${since}&limit=50`),
		api<DungeonStat[]>(`/api/runs/dungeons?since_ms=${since}`),
		optional(api<TopParse[]>(`/api/parses/top?since_ms=${since}&limit=${TOP}`)),
		optional(api<LegionsOut>('/api/parses/legions'))
	]);
</script>

{#await load then [runs, stats, top, legions]}
	{@const kills = stats.reduce((s, x) => s + x.kills, 0)}
	{@const rate = killRate(kills, stats.reduce((s, x) => s + x.wipes, 0))}
	{@const minutes = Math.round(runs.reduce((s, r) => s + r.end_ms - r.start_ms, 0) / 60_000)}
	{@const played = groupDungeons(stats, stats)}
	<div class="today">
		<p class="kicker">
			{legions?.legions.length ? t('logs.today.label', { guild: legions.legions.join(', ') }) : t('logs.today.labelNoGuild')}
		</p>
		<div class="kpis">
			<div><b class="num">{runs.length}</b><small>{t('logs.today.runs')}</small></div>
			<div><b class="num ok">{kills}</b><small>{t('logs.today.kills')}</small></div>
			<div><b class="num accent">{rate != null ? `${rate} %` : '–'}</b><small>{t('logs.today.rate')}</small></div>
			<div>
				<b class="num">{minutes >= 60 ? `${(minutes / 60).toFixed(1).replace('.', ',')} h` : `${minutes} min`}</b>
				<small>{t('logs.today.time')}</small>
			</div>
		</div>

		{#if runs.length}
			<div class="cols">
				{#if top}
					<section>
						<h3>{t('logs.today.top')} <small>{t('logs.today.topHint')}</small></h3>
						{#each top as p, i (p.name)}
							{@const info = classInfo(p.cls)}
							<a class="top" href="/hub/runs/{p.run_id}/kampf/{encodeURIComponent(p.fight)}">
								<span class="rank num">{i + 1}</span>
								<span class="value"><ParseValue value={p.eu} /></span>
								{#if info}<img src={info.icon} alt={info.label} width="28" height="28" />{/if}
								<span class="who">
									<strong style:color={info?.color}>{p.name}</strong>
									<small>{p.boss} · {p.dungeon}</small>
								</span>
							</a>
						{:else}
							<p class="dim small">{t('logs.today.noTop')}</p>
						{/each}
					</section>
				{/if}
				<section>
					<h3>{t('logs.today.played')}</h3>
					<div class="played">
						{#each played as g (g.name)}
							<a class="dungeon" href={dungeonHref(g.name, 'heute')} style:--hue={dungeonHue(g.name)}>
								<span class="glow" aria-hidden="true"></span>
								<strong>{g.name}</strong>
								<span class="meta">
									<span>{t('logs.today.runsToday', { n: g.runs })}</span>
									{#if g.fastest_ms != null}<span class="num ok">{t('logs.today.bestToday', { d: formatDuration(g.fastest_ms) })}</span>{/if}
								</span>
							</a>
						{/each}
					</div>
				</section>
			</div>
			<section>
				<h3>{t('logs.today.runList')} <a class="all" href="/hub/runs">{t('logs.today.all')} →</a></h3>
				<div class="runs">
					{#each runs as run (run.id)}<RunRow {run} title={run.dungeon} />{/each}
				</div>
			</section>
		{:else}
			<p class="dim">{t('logs.today.none')} <a href="/hub/runs?zeit=woche">{t('logs.period.woche')} →</a></p>
		{/if}
	</div>
{:catch e}
	<p class="notice error" role="alert">{e.message}</p>
{/await}

<style>
	.today {
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.kicker {
		margin: 0;
		font-size: 12px;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--accent);
		font-weight: 600;
	}
	.kpis {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
		gap: 10px;
	}
	.kpis > div {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 14px 16px;
		border-radius: 14px;
		background: var(--fill);
		border: 1px solid var(--edge-soft);
	}
	.kpis b {
		font-size: 26px;
		font-weight: 600;
	}
	b.ok,
	.ok {
		color: var(--ok);
	}
	b.accent {
		color: var(--accent);
	}
	small {
		font-size: 12px;
		color: var(--faint);
		font-weight: 400;
	}
	.cols {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
		gap: 18px;
	}
	h3 {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 6px 10px;
		font-size: 15px;
		margin: 0 0 10px;
	}
	.all {
		margin-left: auto;
		font-size: 13px;
		font-weight: 400;
	}
	.top {
		display: grid;
		grid-template-columns: 20px 44px 28px minmax(0, 1fr);
		gap: 10px;
		align-items: center;
		padding: 8px 10px;
		border-radius: 10px;
		color: var(--text);
		text-decoration: none;
	}
	.top:hover {
		background: var(--fill);
	}
	.rank {
		font-size: 12px;
		color: var(--faint);
	}
	.value {
		text-align: center;
		font-size: 22px;
		font-weight: 700;
	}
	.top img {
		border-radius: 8px;
		border: 1px solid var(--edge);
		object-fit: contain;
	}
	.who {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.who small {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.played {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
		gap: 10px;
	}
	.dungeon {
		position: relative;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-height: 96px;
		padding: 16px;
		border-radius: 14px;
		border: 1px solid var(--edge);
		background: var(--fill);
		color: var(--text);
		text-decoration: none;
		transition: transform 0.25s var(--ease);
	}
	.dungeon:hover {
		transform: translateY(-3px);
	}
	.dungeon .glow {
		position: absolute;
		inset: -60% -30% auto auto;
		width: 200px;
		height: 200px;
		border-radius: 50%;
		pointer-events: none;
		background: radial-gradient(circle, hsl(var(--hue) 90% 62% / 0.32), transparent 65%);
		filter: blur(10px);
	}
	.dungeon strong {
		position: relative;
		font-family: var(--font-heading);
		font-weight: 600;
		font-size: 14px;
		line-height: 1.3;
	}
	.meta {
		position: relative;
		margin-top: auto;
		display: flex;
		justify-content: space-between;
		gap: 8px;
		font-size: 12px;
		color: var(--faint);
	}
	.runs {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.small {
		font-size: 13px;
	}
	@media (prefers-reduced-motion: reduce) {
		.dungeon {
			transition: none;
		}
		.dungeon:hover {
			transform: none;
		}
	}
</style>
