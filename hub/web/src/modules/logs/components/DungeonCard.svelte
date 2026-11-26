<!-- Ein Dungeon in der Übersicht der Runs: Glaskarte mit eigenem Farbschein, Schwierigkeiten, Runs, Bestzeit und
     Kill-Quote im gewählten Zeitraum. Ein Klick öffnet die Seite des Dungeons. -->
<script lang="ts">
	import { formatDuration } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import { dungeonHref, dungeonHue, killRate, type DungeonGroup, type Period } from '../dungeons.ts';
	import TierLabel from './TierLabel.svelte';

	let { group, period }: { group: DungeonGroup; period: Period } = $props();

	const rate = $derived(killRate(group.kills, group.wipes));
	const last = $derived(new Date(group.last_ms).toLocaleDateString(i18n.locale, { day: '2-digit', month: '2-digit', year: 'numeric' }));
</script>

<a class="card" href={dungeonHref(group.name, period)} aria-label={t('logs.dungeons.openAria', { name: group.name })}
	style:--hue={dungeonHue(group.name)}>
	<span class="glow" aria-hidden="true"></span>
	<span class="top">
		<strong class="name">{group.name}</strong>
		<span class="kind">{t(group.solo ? 'logs.kind.solo' : 'logs.kind.gruppe')}</span>
	</span>
	{#if group.tiers.length > 1 || !group.tiers[0].only}
		<span class="tiers">
			{#each group.tiers as tier (tier.dungeon_id)}
				<span class="tier"><TierLabel {tier} /> <span class="num">{tier.runs}</span></span>
			{/each}
		</span>
	{/if}
	<span class="stats">
		<span><b class="num">{group.runs}</b><small>{t('logs.dungeons.runsShort')}</small></span>
		<span><b class="num best">{group.fastest_ms != null ? formatDuration(group.fastest_ms) : '–'}</b><small>{t('logs.dungeons.best')}</small></span>
		<span><b class="num">{rate != null ? `${rate} %` : '–'}</b><small>{t('logs.dungeons.rate')}</small></span>
	</span>
	<span class="bar" aria-hidden="true"><span style:width="{rate ?? 0}%"></span></span>
	<span class="foot">
		<span>
			{period === 'alle'
				? t('logs.dungeons.last', { date: last })
				: t('logs.dungeons.players', { n: group.players, when: t(`logs.when.${period}`) })}
		</span>
		<span class="open">{t('logs.dungeons.open')} →</span>
	</span>
</a>

<style>
	.card {
		position: relative;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		gap: 16px;
		padding: 22px;
		border-radius: 18px;
		border: 1px solid var(--edge);
		background: var(--glass);
		backdrop-filter: blur(var(--glass-blur));
		-webkit-backdrop-filter: blur(var(--glass-blur));
		box-shadow: inset 0 1px 0 var(--glass-shine), 0 10px 30px var(--shade);
		color: var(--text);
		text-decoration: none;
		transition: transform 0.25s var(--ease), border-color 0.25s;
	}
	.card:hover {
		transform: translateY(-4px);
		border-color: color-mix(in srgb, var(--text) 28%, transparent);
	}
	.glow {
		position: absolute;
		inset: -40% -20% auto auto;
		width: 260px;
		height: 260px;
		border-radius: 50%;
		pointer-events: none;
		background: radial-gradient(circle, hsl(var(--hue) 90% 62% / 0.34), transparent 65%);
		filter: blur(10px);
	}
	.top,
	.tiers,
	.stats,
	.bar,
	.foot {
		position: relative;
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 12px;
	}
	.name {
		font-family: var(--font-heading);
		font-weight: 600;
		font-size: 18px;
		line-height: 1.25;
	}
	.kind {
		flex: none;
		font-size: 11px;
		padding: 4px 9px;
		border-radius: 999px;
		background: var(--fill-strong);
		color: var(--dim);
	}
	.tiers {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.tier {
		font-size: 12px;
		padding: 4px 10px;
		border-radius: 999px;
		border: 1px solid var(--edge);
	}
	.tier .num {
		color: var(--faint);
	}
	.stats {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 10px;
	}
	.stats > span {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	b {
		font-size: 26px;
		font-weight: 600;
	}
	b.best {
		color: var(--ok);
	}
	small {
		font-size: 12px;
		color: var(--faint);
	}
	.bar {
		display: block;
		height: 6px;
		border-radius: 999px;
		background: color-mix(in srgb, var(--danger) 35%, transparent);
		overflow: hidden;
	}
	.bar span {
		display: block;
		height: 100%;
		border-radius: 999px;
		background: linear-gradient(90deg, var(--ok), var(--accent));
	}
	.foot {
		display: flex;
		justify-content: space-between;
		gap: 10px;
		font-size: 12px;
		color: var(--faint);
	}
	.open {
		color: var(--accent);
	}
	@media (prefers-reduced-motion: reduce) {
		.card {
			transition: none;
		}
		.card:hover {
			transform: none;
		}
	}
</style>
