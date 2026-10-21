<!-- Fähigkeiten eines Spielers in einem Kampf, aufgebaut wie bei Warcraft Logs/AbyssLogs: eine Zeile je
     Fähigkeit, aufklappbar, wenn es mehr zu zeigen gibt (Spezialisierungen, Mehrfachtreffer). -->
<script lang="ts">
	import { SvelteSet } from 'svelte/reactivity';
	import { formatCompact, formatNumber, formatPct } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { FightPlayer, FightSkill } from '../api.ts';
	import { castsOf } from '../casts.ts';
	import { classColor } from '../classes.ts';
	import { skillName } from '../names.svelte.ts';
	import SkillIcon from './SkillIcon.svelte';

	let { player, boss }: { player: FightPlayer; boss: string } = $props();

	const ROMAN = ['I', 'II', 'III', 'IV', 'V'];
	const COLUMNS = ['hits', 'crit', 'min', 'max', 'avg', 'back', 'parry', 'perfect', 'double', 'multi'];

	const open = new SvelteSet<number>();
	const color = $derived(classColor(player.cls));
	const max = $derived(player.skills[0]?.damage || 1);
	const hits = $derived(player.skills.reduce((n, s) => n + s.hits, 0));
	const casts = $derived(castsOf(player).length);

	const rate = (v: number) => (v ? formatPct(v) : '–');
	const short = (v: number) => (v ? formatCompact(v) : '–');
	// Quoten der API in Prozent der Treffer, hier als Anzahl wie bei AbyssLogs
	const count = (v: number, of: number) => (v ? formatNumber(Math.round((v * of) / 100)) : '–');
	const expandable = (s: FightSkill) => s.specs.length > 0 || s.multi_hits > 0;
	const toggle = (i: number) => (open.has(i) ? open.delete(i) : open.add(i));
</script>

<header class="head">
	<h2>{t('logs.skills.against', { boss })}</h2>
	<span class="dim">
		{t('logs.skills.summary', { n: player.skills.length, c: formatNumber(casts), h: formatNumber(hits) })}
	</span>
</header>
<div class="table-wrap">
	<table class="table skills">
		<thead>
			<tr>
				<th>{t('logs.skills.col.skill')}</th>
				<th class="right">{t('logs.skills.col.damage')}</th>
				<th>{t('logs.skills.col.pct')}</th>
				{#each COLUMNS as c (c)}<th class="right">{t(`logs.skills.col.${c}`)}</th>{/each}
			</tr>
		</thead>
		<tbody>
			{#each player.skills as s, i (`${s.code}-${i}`)}
				{@const name = skillName(s.code, s.name)}
				{@const isOpen = open.has(i)}
				<tr class:open={isOpen}>
					<td>
						<span class="skill">
							{#if expandable(s)}
								<button type="button" class="caret" aria-expanded={isOpen}
									aria-label={t('logs.skills.expand', { name })} onclick={() => toggle(i)}>›</button>
							{:else}
								<span class="caret" aria-hidden="true"></span>
							{/if}
							<SkillIcon code={s.code} />
							<span class="skill-name">
								{name}
								{#if s.dot}<span class="chip">DoT</span>{/if}
								{#if s.specs.length}<span class="specs">{t('logs.skills.specs', { n: s.specs.length })}</span>{/if}
							</span>
						</span>
					</td>
					<td class="right num" title={formatNumber(s.damage)}>{formatCompact(s.damage)}</td>
					<td>
						<span class="share">
							<span class="bar" aria-hidden="true"><span style:width="{(100 * s.damage) / max}%" style:background={color}></span></span>
							<span class="num">{formatPct(s.share)}</span>
						</span>
					</td>
					<td class="right num">{formatNumber(s.hits)}</td>
					<td class="right num">{rate(s.crit)}</td>
					<td class="right num">{short(s.min)}</td>
					<td class="right num">{short(s.max)}</td>
					<td class="right num">{short(s.avg)}</td>
					<td class="right num">{count(s.back, s.hits)}</td>
					<td class="right num">{count(s.parry, s.hits)}</td>
					<td class="right num">{count(s.perfect, s.hits)}</td>
					<td class="right num">{count(s.double, s.hits)}</td>
					<td class="right num">{s.multi_hits ? `${s.multi_hits}× (${formatCompact(s.multi_damage)})` : '–'}</td>
				</tr>
				{#if isOpen}
					<tr class="detail">
						<td colspan={3 + COLUMNS.length}>
							<div class="detail-body">
								<div>
									<span class="dim">{t('logs.skills.specsActive')}</span>
									{#if s.specs.length}
										<span class="slots">
											{#each ROMAN as r, k (r)}<span class:on={s.specs.includes(k + 1)}>{r}</span>{/each}
										</span>
									{:else}
										<span>{t('logs.skills.noSpecs')}</span>
									{/if}
								</div>
								{#if s.multi_hits > 0}
									<div class="dim">
										{t('logs.skills.multiDetail', { n: formatNumber(s.multi_hits), d: formatNumber(s.multi_damage) })}
									</div>
								{/if}
							</div>
						</td>
					</tr>
				{/if}
			{/each}
		</tbody>
	</table>
</div>

<style>
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 4px 14px;
		margin-bottom: 12px;
	}
	h2 {
		font-size: 17px;
	}
	.head span {
		font-size: 14px;
	}
	.skills td,
	.skills th {
		padding-left: 8px;
		padding-right: 8px;
		white-space: nowrap;
	}
	.skill {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		font-weight: 550;
	}
	.caret {
		width: 18px;
		flex-shrink: 0;
		border: 0;
		background: none;
		color: var(--dim);
		font-size: 18px;
		line-height: 1;
		padding: 0;
		cursor: pointer;
		transition: transform 0.15s;
	}
	.caret[aria-expanded='true'] {
		transform: rotate(90deg);
		color: var(--text);
	}
	.skill-name {
		display: inline-flex;
		flex-direction: column;
		gap: 1px;
	}
	.skill-name .chip {
		align-self: flex-start;
		margin: 2px 0 0;
	}
	.specs {
		font-size: 12px;
		color: var(--accent);
		font-weight: 550;
	}
	.share {
		display: inline-flex;
		align-items: center;
		gap: 10px;
	}
	.bar {
		display: block;
		height: 6px;
		width: 90px;
		flex-shrink: 0;
		border-radius: 999px;
		background: rgba(0, 0, 0, 0.35);
		overflow: hidden;
	}
	.bar > span {
		display: block;
		height: 100%;
		border-radius: inherit;
	}
	tr.open td,
	tr.detail td {
		background: rgba(255, 255, 255, 0.04);
	}
	tr.detail td {
		border-top: 0;
		padding-top: 0;
	}
	.detail-body {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 28px;
		padding: 4px 0 6px 64px;
		font-size: 14px;
	}
	.detail-body > div {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.slots {
		display: inline-flex;
		gap: 4px;
	}
	.slots span {
		min-width: 30px;
		text-align: center;
		padding: 2px 6px;
		border-radius: 7px;
		font-size: 12px;
		font-weight: 650;
		color: var(--faint);
		border: 1px solid var(--edge-soft);
	}
	.slots span.on {
		color: #071019;
		background: var(--accent);
		border-color: transparent;
	}
	@media (max-width: 900px) {
		.detail-body {
			padding-left: 0;
		}
	}
</style>
