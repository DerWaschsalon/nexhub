<!-- „Zuerst verbessern“: Hinweise des Ratgebers (ratgeber.py) zu einem Armory-Charakter, je Gegenstand
     mit Symbol. Reihenfolge kommt von der API, von schnell erledigt bis teuer. -->
<script lang="ts">
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import ItemIcon from '#modules/logs/components/ItemIcon.svelte';
	import type { ArmoryHint } from '../api.ts';

	let { hints }: { hints: Record<string, ArmoryHint[]> } = $props();
	const list = $derived(hints[i18n.lang] ?? hints.en ?? []);

	function text(h: ArmoryHint): string {
		switch (h.art) {
			case 'sockel':
				return t('armory.hints.sockel', { n: h.frei });
			case 'verzaubern':
				return t('armory.hints.verzaubern', { n: h.stufe, werte: h.werte.join(', ') });
			case 'stein':
			case 'nebenwert':
				return t(`armory.hints.${h.art}`, { werte: h.werte.join(', ') });
			case 'set':
				return t('armory.hints.set', { set: h.set, hat: h.hat, braucht: h.braucht });
		}
	}
</script>

<section class="glass pad">
	<h2>{t('armory.hints.title')}</h2>
	<p class="dim small">{t('armory.hints.intro')}</p>
	{#if list.length}
		<ul>
			{#each list as h, i (i)}
				<li>
					{#if h.art !== 'set'}<ItemIcon name={h.item} icon={h.icon} grade={h.grade} size={32} />{/if}
					<span>
						{#if h.art !== 'set'}<b>{h.item}</b>{/if}
						<span class="dim">{text(h)}</span>
					</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p>{t('armory.hints.none')}</p>
	{/if}
</section>

<style>
	ul {
		list-style: none;
		margin: 10px 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	li {
		display: flex;
		align-items: center;
		gap: 10px;
		font-size: 14px;
	}
	li > span {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.small {
		font-size: 12px;
	}
</style>
