<!-- Charakter wie im Spiel (Armory, Mitspieler eines Runs): links „Stat Info“ (Fortschritt, Hauptwerte,
     Nebenwerte), in der Mitte die Figur der Klasse, rechts die Ausrüstungsspalte, darunter die Skills
     (CharacterLayout); ein Klick auf Gegenstand oder Arkana öffnet alle Werte. `aside` steht im Kopf rechts
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
	import EquipmentPanel from './EquipmentPanel.svelte';
	import ItemDialog from './ItemDialog.svelte';
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
	let open: CharacterItem | null = $state(null);
	const show = (item: CharacterItem) => (open = item);
</script>

<CharacterHeader {character} {data} {aside} />

<CharacterLayout {cls}>
	{#snippet main()}
		<StatInfo {data} {cls} {arcana} onItem={show} />
	{/snippet}
	{#snippet doll()}
		<EquipmentPanel {data} ratings={rated} onItem={show} />
	{/snippet}
	{#snippet below()}
		<section class="skills">
			<h3>{t('logs.char.skills')}</h3>
			<SkillGrid {data} />
		</section>
	{/snippet}
</CharacterLayout>

{#if source}<p class="dim small source">{source}</p>{/if}

<ItemDialog bind:item={open} ratings={rated} />

<style>
	.skills {
		padding: 14px;
		background: linear-gradient(#1c2433, #171e2a);
		border: 1px solid rgba(255, 255, 255, 0.1);
	}
	.skills h3 {
		margin: 0 0 12px;
		font-family: Georgia, 'Times New Roman', serif;
		font-size: 20px;
		font-weight: 400;
		text-align: center;
	}
	.source {
		margin-top: 12px;
		font-size: 12px;
	}
</style>
