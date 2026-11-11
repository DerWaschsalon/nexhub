<!-- Die Würfel-Schritte eines Gegenstands: welche Zeile neu würfeln, Chance pro Versuch, Ziele in
     Stufen mit ihrem Zugewinn. Für den Reiter „Upgrades“ und das Gegenstandsfenster. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { RerollStep, RerollTarget } from '../rating.ts';

	let { steps }: { steps: RerollStep[] } = $props();

	const TIERS = ['best', 'good', 'fine'] as const;
	// „{line} neu würfeln“ / „Reroll {line}“: Text vor und nach dem Namen, der Name kommt fett dazwischen
	const sentence = () => t('logs.rating.reroll', { line: '\u0000' }).split('\u0000');
	// Zugewinn mit Vorzeichen: ein schlechter Wurf kann auch etwas kosten
	const signed = (n: number) => `${n < 0 ? '−' : '+'}${Math.abs(Math.round(n))}`;
	const span = (list: RerollTarget[]) =>
		`${signed(Math.min(...list.map((g) => g.gain_lo)))} – ${signed(Math.max(...list.map((g) => g.gain_hi)))}`;
</script>

<ol>
	{#each steps as s, i (i)}
		{@const [before, after] = sentence()}
		<li>
			<p>
				{before}<b>{s.line}</b>{after}
				<span class="chance">{t('logs.rating.chance', { n: Math.round(s.chance) })}</span>
			</p>
			{#each TIERS as tier (tier)}
				{@const list = s.tiers[tier]}
				{#if list?.length}
					<p class="tier">
						<span class="dim">{t(`logs.rating.tier.${tier}`)}</span>
						<span>{list.map((g) => g.name).join(', ')}</span>
						<span class="gain">{span(list)}</span>
					</p>
				{/if}
			{/each}
		</li>
	{/each}
</ol>
<p class="dim small">{t('logs.rating.bindAfter')}</p>

<style>
	ol {
		margin: 8px 0 0;
		padding-left: 20px;
		font-size: 13px;
	}
	li {
		margin-bottom: 8px;
	}
	p {
		margin: 2px 0;
	}
	.chance {
		margin-left: 6px;
		color: #f2c522;
		font-weight: 700;
	}
	.tier {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 8px;
	}
	.tier .dim {
		min-width: 74px;
	}
	.gain {
		color: var(--ok);
		font-weight: 600;
	}
	.small {
		font-size: 12px;
	}
</style>
