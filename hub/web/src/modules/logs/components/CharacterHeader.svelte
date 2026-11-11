<!-- Kopf eines Charakterprofils: Bild, Name in Klassenfarbe, Klasse/Stufe/Server/Legion, Titel,
     Kampfkraft, Gegenstandsstufe und Stand. Für Profil (Runs) und Spielansicht (Armory). -->
<script lang="ts">
	import { formatDateTime, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, CharacterListItem } from '../api.ts';
	import PlayerName from './PlayerName.svelte';

	let { character, data }: { character: CharacterListItem; data: CharacterData } = $props();
</script>

<header class="glass pad head">
	{#if data.profile.image}
		<img class="portrait" src={data.profile.image} alt="" width="72" height="72" referrerpolicy="no-referrer" />
	{/if}
	<div class="who">
		<h2><PlayerName name={data.profile.name} cls={character.cls} size={26} /></h2>
		<p class="dim">
			{[data.profile.class, t('logs.char.level', { n: data.profile.level }), data.profile.server, data.profile.guild]
				.filter(Boolean)
				.join(' · ')}
		</p>
		{#if data.profile.title}<p class="dim">„{data.profile.title}“</p>{/if}
	</div>
	<div class="numbers">
		<div>
			<span class="label">{t('logs.char.combatPower')}</span>
			<strong class="num">{formatNumber(data.profile.combat_power)}</strong>
		</div>
		{#if character.item_level}
			<div>
				<span class="label">{t('logs.char.itemLevel')}</span>
				<strong class="num">{formatNumber(character.item_level)}</strong>
			</div>
		{/if}
		{#if character.fetched_at}
			<span class="dim small">{t('logs.char.asOf', { d: formatDateTime(character.fetched_at) })}</span>
		{/if}
	</div>
</header>

<style>
	.head {
		display: flex;
		gap: 16px;
		align-items: center;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}
	.who {
		min-width: 0;
	}
	.portrait {
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	.numbers {
		margin-left: auto;
		display: flex;
		gap: 20px;
		align-items: center;
		flex-wrap: wrap;
	}
	.numbers > div {
		display: flex;
		flex-direction: column;
	}
	.label {
		font-size: 12px;
		color: var(--dim);
	}
	.small {
		font-size: 12px;
	}
</style>
