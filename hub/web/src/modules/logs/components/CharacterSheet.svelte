<!-- Charakter wie im Spiel (Armory): links die Skills, in der Mitte „Werte“ (Hauptwerte, Nebenwerte,
     Fortschritt), rechts die Ausrüstungsspalte; ein Klick auf Gegenstand oder Arkana öffnet alle Werte. -->
<script lang="ts">
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import { localized, type CharacterItem, type CharacterListItem, type CharacterSnapshot } from '../api.ts';
	import { ARCANA } from '../slots.ts';
	import CharacterHeader from './CharacterHeader.svelte';
	import EquipmentPanel from './EquipmentPanel.svelte';
	import ItemDialog from './ItemDialog.svelte';
	import SkillGrid from './SkillGrid.svelte';
	import StatInfo from './StatInfo.svelte';

	let {
		character,
		data: snapshot,
		source
	}: { character: CharacterListItem; data: CharacterSnapshot; source?: string } = $props();

	const data = $derived(localized(snapshot, i18n.lang));
	const arcana = $derived(data.equipment.filter((e) => ARCANA.includes(e.slot_name)));
	let open: CharacterItem | null = $state(null);
	const show = (item: CharacterItem) => (open = item);
</script>

<CharacterHeader {character} {data} />

<div class="frame">
	<div class="layout">
		<section class="skills">
			<h3>{t('logs.char.skills')}</h3>
			<SkillGrid {data} />
		</section>
		<StatInfo {data} cls={character.cls} {arcana} onItem={show} />
		<EquipmentPanel {data} onItem={show} />
	</div>
</div>

{#if source}<p class="dim small source">{source}</p>{/if}

<ItemDialog bind:item={open} />

<style>
	/* Umbrüche nach der Breite des Inhalts, nicht des Fensters: im Hub nimmt die Seitenleiste Platz weg */
	.frame {
		container-type: inline-size;
	}
	.layout {
		display: grid;
		grid-template-columns: 460px minmax(0, 1fr) auto;
		gap: 18px;
		align-items: start;
	}
	/* Mittelbreit: Skills unter die Werte; schmal: alles untereinander */
	@container (max-width: 1300px) {
		.layout {
			grid-template-columns: minmax(0, 1fr) auto;
		}
		.skills {
			grid-column: 1 / -1;
			order: 1;
		}
	}
	@container (max-width: 640px) {
		.layout {
			grid-template-columns: 1fr;
		}
	}
	.skills {
		padding: 14px;
		background: linear-gradient(#1c2433, #171e2a);
		border: 1px solid rgba(255, 255, 255, 0.1);
	}
	.skills h3 {
		margin: 0 0 12px;
		font-family: Georgia, 'Times New Roman', serif;
		font-size: 24px;
		font-weight: 400;
		text-align: center;
	}
	.source {
		margin-top: 12px;
		font-size: 12px;
	}
</style>
