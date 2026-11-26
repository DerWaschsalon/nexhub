<script lang="ts">
	import FightView from '#modules/logs/components/FightView.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import ParseBadge from '#modules/parses/components/ParseBadge.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	// Parses nur bei getöteten Bossen und nur, wenn die API sie geliefert hat
	const parses = $derived(data.fight.killed && data.parses ? data.parses : null);
</script>

{#key data.fight.fight}
	{#if parses}
		<FightView fight={data.fight}>
			{#snippet badge(p)}
				<ParseBadge parse={parses.fights[data.fight.fight]?.[p.name]} cls={p.cls} guildMin={parses.guild_min} />
			{/snippet}
		</FightView>
		<p class="how"><a href="/hub/bewertung#parses">{t('parses.how')}</a></p>
	{:else}
		<FightView fight={data.fight} />
	{/if}
{/key}

<style>
	.how {
		margin: 10px 0 0;
		font-size: 13px;
	}
</style>
