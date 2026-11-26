<!-- Name einer Schwierigkeit: aus den Spieldaten (Schwer, Normal, Erkundung), sonst „Stufe n“. Schwer in Orange. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { Tier } from '../dungeons.ts';

	let { tier }: { tier: Tier } = $props();
</script>

<span class:hard={tier.difficultyKey === 'hard'} class:easy={tier.difficultyKey === 'exploration'}>
	{tier.difficultyKey
		? t(`logs.difficulty.${tier.difficultyKey}`)
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
