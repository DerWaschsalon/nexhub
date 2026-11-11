<!-- Charakterfenster wie im Spiel: links die Spalte Waffen und Rüstung, in der Mitte die Figur der Klasse,
     rechts der Schmuck, daneben das Fenster des gewählten Gegenstands (`detail`). Gewählt wird durch Zeigen
     oder Fokus an Figur oder Platz; zu Beginn die Waffe. Darunter der Inhalt der Seite (`children`, z. B.
     Stat Info und Skills) nebeneinander. Umbrüche nach der Breite des Inhalts, nicht des Fensters: mittelbreit
     ohne Detailfenster (ein Klick öffnet es dann als Dialog, onOpen), schmal ohne Figur.
     Profil der Armory, Mitspieler eines Runs und BiS-Listen nutzen ihn. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { CharacterData } from '../api.ts';
	import type { Rating } from '../rating.ts';
	import { LEFT, RIGHT } from '../slots.ts';
	import ClassFigure from './ClassFigure.svelte';
	import EquipmentPanel from './EquipmentPanel.svelte';

	let {
		cls,
		data,
		ratings,
		detail,
		onOpen,
		children
	}: {
		cls: string | null;
		data: Pick<CharacterData, 'equipment' | 'wing' | 'pet'>;
		ratings?: Map<string, Rating>;
		detail: Snippet<[string]>;
		onOpen: (slot: string) => void;
		children: Snippet;
	} = $props();

	const names = $derived(new Map(data.equipment.map((e) => [e.slot_name, e.name])));
	let active: string | null = $state(null);
	const shown = $derived(active ?? (names.has('MainHand') ? 'MainHand' : null));
	let pane: HTMLElement | undefined = $state();

	// Ist das Detailfenster ausgeblendet (mittelbreit), zeigt ein Klick den Gegenstand als Dialog
	function pick(slot: string) {
		active = slot;
		if (!pane?.offsetParent) onOpen(slot);
	}
</script>

<div class="frame">
	<div class="window">
		<!-- Spalten und Figur für sich: die Figur richtet sich nur nach den Spalten, nicht nach dem
		     Detailfenster, dessen Höhe mit jedem Gegenstand wechselt -->
		<div class="doll">
			<EquipmentPanel {data} slots={LEFT} {ratings} bind:active onPick={pick} extras />
			<div class="figure"><ClassFigure {cls} {names} bind:active onPick={pick} /></div>
			<EquipmentPanel {data} slots={RIGHT} {ratings} bind:active onPick={pick} />
		</div>
		<div class="detail" bind:this={pane}>{#if shown}{@render detail(shown)}{/if}</div>
	</div>
	<div class="below">{@render children()}</div>
</div>

<style>
	.frame {
		container-type: inline-size;
	}
	.window {
		display: grid;
		grid-template-columns: minmax(0, 648px) minmax(0, 440px);
		gap: 18px;
		justify-content: center;
		align-items: start;
	}
	.doll {
		display: grid;
		grid-template-columns: 64px minmax(200px, 480px) 64px;
		gap: 18px;
		justify-content: center;
		align-items: center;
	}
	.detail {
		position: sticky;
		top: 16px;
	}
	/* Darunter: die Teile der Seite nebeneinander, so viele wie mit 460 px Platz haben */
	.below {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr));
		gap: 18px;
		align-items: start;
		margin-top: 28px;
	}
	@container (max-width: 1100px) {
		.window {
			grid-template-columns: minmax(0, 648px);
		}
		.detail {
			display: none;
		}
	}
	@container (max-width: 480px) {
		.doll {
			grid-template-columns: 64px 64px;
		}
		.figure {
			display: none;
		}
	}
</style>
