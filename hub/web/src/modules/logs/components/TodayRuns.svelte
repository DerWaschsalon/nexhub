<!-- Übersicht (Startseite), Kachel Runs: oben die Bestenliste ab Lila (dauerhaft, über alle Runs), darunter nur der
     heutige Tag, kompakt: Zahlen in einer Zeile und drei schmale Spalten (beste Parses der Gilde, gespielte Dungeons,
     neueste Runs). Ältere unter „Runs“. Parses rechnet der Hub alle 5 Minuten im Hintergrund (parses/hall.py). -->
<script lang="ts">
	import { api } from '#lib/api.ts';
	import type { Hall, LegionsOut, TopParse } from '#lib/api-types.ts';
	import { formatDuration } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import ParseValue from '#modules/parses/components/ParseValue.svelte';
	import type { RunListItem } from '../api.ts';
	import { classInfo } from '../classes.ts';
	import { dungeonHref, dungeonHue, groupDungeons, killRate, sinceMs, type DungeonStat } from '../dungeons.ts';
	import TierLabel from './TierLabel.svelte';

	const TOP = 3;
	const RUNS = 4;
	const since = sinceMs('heute')!;
	// Parses und Legion sind ein eigenes Modul: fehlen sie, bleibt die Kachel ohne
	const optional = <T,>(p: Promise<T>) => p.catch(() => null);

	const load = Promise.all([
		api<RunListItem[]>(`/api/runs?since_ms=${since}&limit=50`),
		api<DungeonStat[]>('/api/runs/dungeons'),
		api<DungeonStat[]>(`/api/runs/dungeons?since_ms=${since}`),
		optional(api<TopParse[]>(`/api/parses/top?since_ms=${since}&limit=${TOP}`)),
		optional(api<LegionsOut>('/api/parses/legions')),
		optional(api<Hall>('/api/parses/hall'))
	]);
	const date = (ms: number) => new Date(ms).toLocaleDateString(i18n.locale, { day: '2-digit', month: '2-digit' });
	const time = (ms: number) => new Date(ms).toLocaleTimeString(i18n.locale, { hour: '2-digit', minute: '2-digit' });
</script>

{#await load then [runs, all, stats, top, legions, hall]}
	{@const kills = stats.reduce((s, x) => s + x.kills, 0)}
	{@const rate = killRate(kills, stats.reduce((s, x) => s + x.wipes, 0))}
	{@const minutes = Math.round(runs.reduce((s, r) => s + r.end_ms - r.start_ms, 0) / 60_000)}
	<div class="today">
		<div class="line1">
			<span class="label">
				{legions?.legions.length ? t('logs.today.label', { guild: legions.legions.join(', ') }) : t('logs.today.labelNoGuild')}
			</span>
			<span class="chips">
				<span class="chip"><b class="num">{runs.length}</b> {t('logs.today.runs')}</span>
				<span class="chip"><b class="num ok">{kills}</b> {t('logs.today.kills')}</span>
				{#if rate != null}<span class="chip"><b class="num accent">{rate} %</b></span>{/if}
				<span class="chip"><b class="num">{minutes >= 60 ? (minutes / 60).toFixed(1).replace('.', ',') : minutes}</b> {minutes >= 60 ? 'h' : 'min'}</span>
			</span>
		</div>

		{#if hall?.entries.length}
			<section class="hall" aria-label={t('logs.today.hall')}>
				<h3>{t('logs.today.hall')} <span class="hint">{t('logs.today.hallHint')}</span></h3>
				<div class="hall-list">
					{#each hall.entries as p, i (p.name)}
						{@const info = classInfo(p.cls)}
						<a class="fame" href="/hub/runs/{p.run_id}/kampf/{encodeURIComponent(p.fight)}">
							<span class="place num">{i + 1}</span>
							<b class="big"><ParseValue value={p.eu} /></b>
							<span class="two">
								<strong style:color={info?.color}>
									{#if info}<img src={info.icon} alt={info.label} width="16" height="16" />{/if}{p.name}
								</strong>
								<small>{p.boss}</small>
								<small>{p.dungeon} · {date(p.start_ms)}</small>
							</span>
						</a>
					{/each}
				</div>
			</section>
		{/if}

		{#if runs.length}
			<div class="cols">
				{#if top}
					<section>
						<h3>{t('logs.today.topShort')}</h3>
						{#each top as p (p.name)}
							{@const info = classInfo(p.cls)}
							<a class="row parse" href="/hub/runs/{p.run_id}/kampf/{encodeURIComponent(p.fight)}">
								<b class="value"><ParseValue value={p.eu} /></b>
								{#if info}<img src={info.icon} alt={info.label} width="20" height="20" />{:else}<span></span>{/if}
								<span class="two">
									<strong style:color={info?.color}>{p.name}</strong>
									<small>{p.boss} · {p.dungeon}</small>
								</span>
							</a>
						{:else}
							<p class="none">{t('logs.today.noTopShort')}</p>
						{/each}
					</section>
				{/if}
				<section>
					<h3>{t('logs.today.played')}</h3>
					{#each groupDungeons(all, stats) as g (g.name)}
						<a class="row dungeon" href={dungeonHref(g.name, 'heute')}>
							<i style:--hue={dungeonHue(g.name)} aria-hidden="true"></i>
							<span class="two">
								<strong>{g.name}</strong>
								<small>{#each g.tiers as tier, i (tier.dungeon_id)}{i ? ', ' : ''}<TierLabel {tier} />{/each}</small>
							</span>
							<span class="two end">
								<span class="num">{t('logs.today.runsN', { n: g.runs })}</span>
								{#if g.fastest_ms != null}<small class="num ok">{formatDuration(g.fastest_ms)}</small>{/if}
							</span>
						</a>
					{/each}
				</section>
				<section>
					<h3>{t('logs.today.latest')}</h3>
					{#each runs.slice(0, RUNS) as run (run.id)}
						<a class="row run" href="/hub/runs/{run.id}">
							<small class="num">{time(run.start_ms)}</small>
							<span class="name">{run.dungeon}</span>
							<span class="pips">
								{#each run.results as killed, i (i)}<i class:kill={killed}></i>{/each}
							</span>
							<span class="num dur">{formatDuration(run.end_ms - run.start_ms)}</span>
						</a>
					{/each}
					{#if runs.length > RUNS}
						<a class="more" href="/hub/runs">{t('logs.today.more', { n: runs.length - RUNS })} →</a>
					{/if}
				</section>
			</div>
		{:else}
			<p class="none">{t('logs.today.none')} <a href="/hub/runs?zeit=woche">{t('logs.period.woche')} →</a></p>
		{/if}
	</div>
{:catch e}
	<p class="notice error" role="alert">{e.message}</p>
{/await}

<style>
	.today {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.line1 {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 12px;
	}
	.label {
		font-size: 12px;
		color: var(--faint);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-left: auto;
	}
	.chips .chip {
		font-size: 12px;
		color: var(--dim);
	}
	.chips b {
		color: var(--text);
		font-weight: 600;
	}
	.ok,
	.chips b.ok {
		color: var(--ok);
	}
	.chips b.accent {
		color: var(--accent);
	}
	.hall {
		padding: 0;
	}
	.hall h3 .hint {
		text-transform: none;
		letter-spacing: 0;
		font-weight: 400;
	}
	.hall-list {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
		gap: 8px;
	}
	.fame {
		position: relative;
		display: grid;
		grid-template-columns: 14px 52px minmax(0, 1fr);
		gap: 8px;
		align-items: center;
		padding: 10px 12px;
		border-radius: 12px;
		border: 1px solid var(--edge-soft);
		background: var(--fill);
		color: var(--text);
		text-decoration: none;
	}
	.fame:hover {
		border-color: var(--edge);
	}
	.place {
		font-size: 11px;
		color: var(--faint);
	}
	.big {
		font-size: 24px;
		text-align: center;
	}
	.fame strong {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}
	.fame img {
		border-radius: 4px;
		object-fit: contain;
	}
	.cols {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
		border-top: 1px solid var(--edge-soft);
	}
	section {
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 12px 14px 0;
		min-width: 0;
	}
	section + section {
		border-left: 1px solid var(--edge-soft);
	}
	h3 {
		margin: 0 0 6px;
		font-size: 12px;
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--faint);
	}
	.row {
		display: grid;
		gap: 10px;
		align-items: center;
		padding: 5px 6px;
		border-radius: 8px;
		color: var(--text);
		text-decoration: none;
	}
	.row:hover {
		background: var(--fill);
	}
	.parse {
		grid-template-columns: 30px 20px minmax(0, 1fr);
	}
	.value {
		font-size: 16px;
		text-align: center;
	}
	.parse img {
		border-radius: 6px;
		object-fit: contain;
	}
	.dungeon {
		grid-template-columns: 8px minmax(0, 1fr) auto;
	}
	.dungeon i {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: hsl(var(--hue) 90% 62%);
		box-shadow: 0 0 8px hsl(var(--hue) 90% 62%);
	}
	.run {
		grid-template-columns: 40px minmax(0, 1fr) auto 40px;
	}
	.two {
		display: flex;
		flex-direction: column;
		min-width: 0;
		line-height: 1.25;
	}
	.two.end {
		align-items: flex-end;
		font-size: 12px;
	}
	strong {
		font-size: 13px;
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	small {
		font-size: 11px;
		color: var(--faint);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.name {
		font-size: 13px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.pips {
		display: flex;
		gap: 3px;
	}
	.pips i {
		width: 8px;
		height: 8px;
		border-radius: 3px;
		background: var(--danger);
	}
	.pips i.kill {
		background: var(--ok);
	}
	.dur {
		font-size: 12px;
		text-align: right;
	}
	.more {
		margin-top: 4px;
		padding: 0 6px;
		font-size: 12px;
	}
	.none {
		margin: 0;
		font-size: 13px;
		color: var(--dim);
	}
	@media (max-width: 760px) {
		section + section {
			border-left: none;
			border-top: 1px solid var(--edge-soft);
		}
	}
</style>
