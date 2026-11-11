<!-- Aufbau wie das Charakterfenster im Spiel: links `main` (Armory: Stat Info, BiS-Listen: Skills), in der
     Mitte die Figur der Klasse (ClassFigure), rechts die Ausrüstung (`doll`), darunter wahlweise `below` über
     die ganze Breite (Armory: Skills). Zeigt man auf eine Stelle der Figur oder einen Platz der Ausrüstung
     (`active`, beide Seiten setzen es), erscheint `tip` für diesen Platz links neben der Figur. Umbrüche nach
     der Breite des Inhalts, nicht des Fensters (im Hub nimmt die Seitenleiste Platz weg): mittelbreit ohne
     Figur, schmal untereinander mit der Ausrüstung zuerst. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import ClassFigure from './ClassFigure.svelte';

	let {
		cls,
		slots,
		active = $bindable(null),
		onPick,
		tip,
		main,
		doll,
		below
	}: {
		cls: string | null;
		slots: Set<string>;
		active?: string | null;
		onPick: (slot: string) => void;
		tip: Snippet<[string]>;
		main: Snippet;
		doll: Snippet;
		below?: Snippet;
	} = $props();
</script>

<div class="frame">
	<div class="layout">
		<div class="main">{@render main()}</div>
		<div class="figure">
			<ClassFigure {cls} {slots} bind:active {onPick} />
			{#if active}<div class="tip">{@render tip(active)}</div>{/if}
		</div>
		<div class="doll">{@render doll()}</div>
		{#if below}<div class="below">{@render below()}</div>{/if}
	</div>
</div>

<style>
	.frame {
		container-type: inline-size;
	}
	.layout {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 280px auto;
		gap: 18px;
		align-items: start;
	}
	.below {
		grid-column: 1 / -1;
	}
	/* Figur beim Blättern sichtbar */
	.figure {
		position: sticky;
		top: 18px;
	}
	/* Gegenstandsfenster beim Zeigen: links neben der Figur über den Werten, damit die leuchtende Stelle
	   sichtbar bleibt; nur zum Ansehen */
	.tip {
		position: absolute;
		top: 0;
		right: calc(100% + 12px);
		z-index: 10;
		width: 440px;
		pointer-events: none;
	}
	@container (max-width: 820px) {
		.layout {
			grid-template-columns: minmax(0, 1fr) auto;
		}
		.figure {
			display: none;
		}
	}
	@container (max-width: 560px) {
		.layout {
			grid-template-columns: 1fr;
		}
		.doll {
			order: -1;
		}
	}
</style>
