<!-- Aufbau wie das Charakterfenster im Spiel: links `main` (Armory: Stat Info, BiS-Listen: Skills), in der
     Mitte die Figur der Klasse im Klassenlicht, rechts die Ausrüstung (`doll`), darunter wahlweise `below`
     über die ganze Breite (Armory: Skills). Umbrüche nach der Breite des Inhalts, nicht des Fensters (im Hub
     nimmt die Seitenleiste Platz weg): mittelbreit ohne Figur, schmal untereinander mit der Ausrüstung zuerst. -->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { classInfo } from '../classes.ts';

	let {
		cls,
		main,
		doll,
		below
	}: { cls: string | null; main: Snippet; doll: Snippet; below?: Snippet } = $props();

	const info = $derived(classInfo(cls));
	// Für manche Klassen gibt es noch keine Figur (Faustkämpfer): dann bleibt die Mitte leer
	const hide = (e: Event) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden');
</script>

<div class="frame">
	<div class="layout">
		<div class="main">{@render main()}</div>
		<div class="figure" style:--glow={info?.color ?? 'transparent'} aria-hidden="true">
			{#if info}<img src={info.figure} alt="" onerror={hide} />{/if}
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
	/* Figur über die volle Spaltenbreite, beim Blättern sichtbar; Licht in der Klassenfarbe dahinter */
	.figure {
		position: sticky;
		top: 18px;
		padding-top: 30px;
		background: radial-gradient(ellipse 55% 40% at 50% 60%, color-mix(in srgb, var(--glow) 30%, transparent), transparent);
	}
	.figure img {
		display: block;
		width: 100%;
		height: auto;
		filter: drop-shadow(0 0 24px color-mix(in srgb, var(--glow) 40%, transparent));
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
