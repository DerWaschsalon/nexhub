<!-- Ein Charakter in der Armory-Liste: Porträt, Name in Klassenfarbe, Kampfkraft und Item-Level. -->
<script lang="ts">
	import { formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import PlayerName from '#modules/logs/components/PlayerName.svelte';
	import { classFromName } from '#modules/logs/classes.ts';
	import type { ArmoryItem } from '../api.ts';

	let { c }: { c: ArmoryItem } = $props();
</script>

<a class="card glass" href="/hub/armory/{c.id}">
	{#if c.image}
		<img class="portrait" src={c.image} alt="" width="52" height="52" referrerpolicy="no-referrer" loading="lazy" />
	{:else}
		<span class="portrait empty" aria-hidden="true"></span>
	{/if}
	<span class="who">
		<PlayerName name={c.name} cls={c.cls ?? classFromName(c.class_name)} size={18} />
		<span class="dim small">{[c.class_name, c.server].filter(Boolean).join(' · ') || '–'}</span>
		{#if !c.mine}<span class="faint small">{t('armory.owner', { name: c.owner })}</span>{/if}
	</span>
	<span class="numbers">
		{#if c.status === 'offen'}
			<span class="dim small">{t('armory.loading')}</span>
		{:else}
			{#if c.combat_power !== null}
				<span><span class="label">{t('logs.char.combatPower')}</span><strong class="num">{formatNumber(c.combat_power)}</strong></span>
			{/if}
			{#if c.item_level !== null}
				<span><span class="label">{t('logs.char.itemLevel')}</span><strong class="num">{formatNumber(c.item_level)}</strong></span>
			{/if}
			{#if c.status !== 'ok'}<span class="warn small">{t('armory.failed')}</span>{/if}
		{/if}
	</span>
</a>

<style>
	.card {
		display: grid;
		grid-template-columns: 52px 1fr;
		align-items: center;
		gap: 10px 14px;
		padding: 14px 16px;
		border-radius: var(--radius-sm);
		color: inherit;
		text-decoration: none;
		transition: background 0.15s;
	}
	.card:hover {
		background: rgba(255, 255, 255, 0.06);
	}
	.portrait {
		width: 52px;
		height: 52px;
		border-radius: 12px;
		object-fit: cover;
		flex-shrink: 0;
	}
	.portrait.empty {
		background: var(--edge-soft);
	}
	.who {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	/* unter Porträt und Namen über die ganze Breite: Label über dem Wert, nebeneinander */
	.numbers {
		grid-column: 1 / -1;
		display: flex;
		flex-wrap: wrap;
		gap: 4px 22px;
		padding-top: 10px;
		border-top: 1px solid var(--edge-soft);
	}
	.numbers > span {
		display: flex;
		flex-direction: column;
	}
	.label {
		font-size: 11px;
		color: var(--faint);
	}
	.small {
		font-size: 12px;
	}
	.faint {
		color: var(--faint);
	}
	.warn {
		color: var(--warn);
	}
</style>
