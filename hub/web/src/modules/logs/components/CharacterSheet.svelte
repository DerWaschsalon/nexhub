<!-- Charakter wie im Spiel (Armory, Mitspieler eines Runs): oben das Charakterfenster (CharacterLayout:
     Ausrüstung um die Figur der Klasse, daneben der gewählte Gegenstand), darunter „Stat Info“ (Fortschritt,
     Hauptwerte, Nebenwerte) und die Skills nebeneinander; ein Klick auf Arkana öffnet alle Werte. `aside` steht im Kopf rechts
     neben dem Namen (Armory: der Verlauf). Mit `ratings` (rating.ts) Noten an den Plätzen, Rolls mit
     Höchstwert und Anteil und der Weg zu Best in Slot im Gegenstandsfenster. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import { localized, type CharacterItem, type CharacterListItem, type CharacterSnapshot } from '../api.ts';
	import { classFromName } from '../classes.ts';
	import { bySlot, type Ratings } from '../rating.ts';
	import { ARCANA } from '../slots.ts';
	import CharacterHeader from './CharacterHeader.svelte';
	import CharacterLayout from './CharacterLayout.svelte';
	import ItemDialog from './ItemDialog.svelte';
	import ItemTooltip from './ItemTooltip.svelte';
	import SkillGrid from './SkillGrid.svelte';
	import StatInfo from './StatInfo.svelte';

	let {
		character,
		data: snapshot,
		source,
		aside,
		ratings
	}: {
		character: CharacterListItem;
		data: CharacterSnapshot;
		source?: string;
		aside?: Snippet;
		ratings?: Ratings | null;
	} = $props();

	const data = $derived(localized(snapshot, i18n.lang));
	// Armory-Einträge kennen oft nur den Klassennamen der Website
	const cls = $derived(character.cls ?? classFromName(data.profile.class));
	const arcana = $derived(data.equipment.filter((e) => ARCANA.includes(e.slot_name)));
	const rated = $derived(bySlot(ratings));
	const items = $derived(new Map(data.equipment.map((e) => [e.slot_name, e])));
	let open: CharacterItem | null = $state(null);
	const show = (item: CharacterItem) => (open = item);
	const pick = (slot: string) => (open = items.get(slot) ?? null);
</script>

<CharacterHeader {character} {data} {aside} />

<CharacterLayout {cls} {data} ratings={rated} onOpen={pick}>
	{#snippet detail(slot)}
		{@const item = items.get(slot)}
		{#if item}<ItemTooltip {item} rating={rated.get(slot)} />{/if}
	{/snippet}
	<StatInfo {data} {cls} {arcana} onItem={show} />
	<section class="panel skills">
		<h3>{t('logs.char.skills')}</h3>
		<SkillGrid {data} />
	</section>
</CharacterLayout>

{#if source}<p class="dim small source">{source}</p>{/if}

<ItemDialog bind:item={open} ratings={rated} />

<style>
	.skills {
		padding: 14px;
	}
	.skills h3 {
		margin: 0 0 12px;
		font-family: var(--font-heading);
		font-size: 20px;
		font-weight: 400;
		text-align: center;
	}
	.source {
		margin-top: 12px;
		font-size: 12px;
	}
</style>
