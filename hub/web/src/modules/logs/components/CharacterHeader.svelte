<!-- Kopf eines Charakters wie im Spiel: Titel, Stufe im Kreis, Name groß, Klasse · Server · Legion,
     Gegenstandsstufe und Kampfkraft in Gold, Stand. Rechts Platz für mehr (`aside`, z. B. den Verlauf
     in der Armory). Für Run-Profil und Armory. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { formatDateTime, formatNumber } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { CharacterData, CharacterListItem } from '../api.ts';
	import { classInfo } from '../classes.ts';

	let {
		character,
		data,
		aside
	}: { character: CharacterListItem; data: CharacterData; aside?: Snippet } = $props();
	const info = $derived(classInfo(character.cls));
</script>

<header class="head">
	<div class="who">
		{#if data.profile.title}<p class="title">{data.profile.title}</p>{/if}
		<div class="line">
			<span class="level" title={t('logs.char.level', { n: data.profile.level })}>{data.profile.level}</span>
			<div>
				<h2>
					{#if info}<img src={info.icon} alt={info.label} title={info.label} width="34" height="34" />{/if}
					{data.profile.name}
				</h2>
				<p class="dim">{[data.profile.class, data.profile.server, data.profile.guild].filter(Boolean).join(' · ')}</p>
			</div>
			<dl>
				{#if character.item_level}
					<div><dt>{t('logs.char.itemLevel')}</dt><dd class="num">{formatNumber(character.item_level)}</dd></div>
				{/if}
				<div><dt>{t('logs.char.combatPower')}</dt><dd class="num">{formatNumber(data.profile.combat_power)}</dd></div>
			</dl>
		</div>
		{#if character.fetched_at}
			<p class="dim small">{t('logs.char.asOf', { d: formatDateTime(character.fetched_at) })}</p>
		{/if}
	</div>
	{#if aside}<div class="aside">{@render aside()}</div>{/if}
</header>

<style>
	.head {
		display: flex;
		flex-wrap: wrap;
		gap: 18px 28px;
		align-items: center;
		margin-bottom: 18px;
	}
	.who {
		min-width: 0;
	}
	.aside {
		flex: 1 1 380px;
		min-width: 0;
	}
	.title {
		margin: 0 0 4px;
		color: var(--game-green);
		letter-spacing: 0.12em;
		text-transform: uppercase;
		font-size: 13px;
	}
	.line {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 12px 18px;
	}
	.level {
		display: grid;
		place-items: center;
		width: 62px;
		height: 62px;
		border: 2px solid rgba(255, 255, 255, 0.5);
		border-radius: 50%;
		font-weight: 700;
	}
	h2 {
		display: flex;
		align-items: center;
		gap: 10px;
		margin: 0;
		font-family: var(--font-heading);
		font-size: 48px;
		font-weight: 400;
		line-height: 1.05;
	}
	.line p {
		margin: 4px 0 0;
	}
	dl {
		display: flex;
		gap: 26px;
		margin: 0;
	}
	dt {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--dim);
	}
	dd {
		margin: 0;
		font-size: 28px;
		color: var(--game-gold);
	}
	.small {
		margin: 8px 0 0;
		font-size: 12px;
	}
</style>
