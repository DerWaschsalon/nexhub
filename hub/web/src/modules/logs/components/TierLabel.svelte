<!-- Name einer Schwierigkeit: von Abyss Logs oder aus der Aufnahme (übersetzt), sonst „Stufe n“. Schwer in Orange,
     leicht in Grün. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import { tierName, tierTone, type Tier } from '../dungeons.ts';

	let { tier }: { tier: Tier } = $props();
	const tone = $derived(tierTone(tier.difficulty));
</script>

<span class:hard={tone === 'hard'} class:easy={tone === 'easy'}>
	{tier.difficulty
		? tierName(tier.difficulty)
		: tier.only
			? t('logs.difficulty.only')
			: t('logs.difficulty.stage', { n: tier.stage })}
</span>

<style>
	.hard {
		color: var(--game-amplify, #f0a030);
	}
	.easy {
		color: var(--ok);
	}
</style>
