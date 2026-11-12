<!-- Figur der Klasse im Klassenlicht, der eine große Effekt der Seite, mit den Stellen der Ausrüstung
     (data/figureZones.ts). Zeigen oder Fokus wählt eine Stelle und ihren Platz (`active`, gemeinsam mit den
     Platzspalten), ein Klick meldet den Platz (onPick). Stellen gibt es nur für Plätze mit Gegenstand
     (`names`: Platz → Name des Gegenstands, für Screenreader); kleine liegen über großen.
     Hat ein Platz eine eigene Ebene (SLOT_LAYERS), leuchtet der Gegenstand selbst statt eines Rechtecks, und
     die Maus trifft ihn pixelgenau (Deckkraft der Ebene); seine Rechtecke bleiben nur für die Tastatur. -->
<script lang="ts">
	import { classInfo, figureLayer } from '../classes.ts';
	import { FIGURE_ZONES, SLOT_LAYERS } from '../data/figureZones.ts';
	import { FigureMasks } from '../figureMasks.ts';

	let {
		cls,
		names,
		active = $bindable(null),
		onPick
	}: {
		cls: string | null;
		names: Map<string, string>;
		active?: string | null;
		onPick: (slot: string) => void;
	} = $props();

	const info = $derived(classInfo(cls));
	const zones = $derived(
		[...((cls && FIGURE_ZONES[cls]) || [])]
			.filter((z) => names.has(z.slot))
			.sort((a, b) => b.w * b.h - a.w * a.h)
	);
	const layers = $derived(
		cls
			? (SLOT_LAYERS[cls] ?? [])
					.filter((slot) => names.has(slot))
					.map((slot): [string, string] => [slot, figureLayer(cls, slot)])
			: []
	);
	const hasLayer = (slot: string) => layers.some(([s]) => s === slot);
	// Für manche Klassen gibt es noch keine Figur (Faustkämpfer): dann bleibt die Mitte leer
	const hide = (e: Event) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden');

	// Deckkraft jeder Ebene, einmal je Klasse gelesen; bis dahin reagiert nur die Tastatur auf diese Plätze
	let masks = $state<FigureMasks | null>(null);
	$effect(() => {
		let stale = false;
		FigureMasks.load(layers).then((read) => {
			if (!stale) masks = read;
		});
		return () => (stale = true);
	});

	/** Platz unter dem Zeiger (nur Plätze mit Ebene), sonst null */
	let hover = $state<string | null>(null);
	function slotAt(e: PointerEvent | MouseEvent): string | null {
		const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
		return masks?.slotAt((e.clientX - box.left) / box.width, (e.clientY - box.top) / box.height) ?? null;
	}
	// Rechtecke ohne Ebene (Schmuck) liegen obenauf und haben Vorrang
	const onRect = (e: Event) => !!(e.target as HTMLElement).closest('.zone:not(.own)');

	// Das Klassenlicht um die Figur wandert ins gezeigte Teil (show) und beim Verlassen der Figur zurück.
	// Jede Änderung von `active` (Figur, Platzspalten, Tastatur) zeigt das Teil; nicht schon beim ersten Aufbau.
	let show = $state(false);
	let seen: string | null | undefined;
	$effect(() => {
		const now = active;
		if (seen !== undefined && now !== seen) show = true;
		seen = now;
	});
	const lit = (slot: string) => show && active === slot;
	const focus = $derived(show && !!active && hasLayer(active));

	function leave() {
		hover = null;
		show = false;
	}
	function move(e: PointerEvent) {
		hover = onRect(e) ? null : slotAt(e);
		if (hover) active = hover;
	}
	function click(e: MouseEvent) {
		if (onRect(e)) return;
		const slot = slotAt(e);
		if (slot) onPick(slot);
	}
</script>

{#if info}
	<!-- Maus pixelgenau auf den Ebenen; die Tastatur nimmt die Knöpfe darunter -->
	<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
	<div
		class="figure"
		class:focus
		class:pointing={hover}
		style:--glow={info.color}
		onpointermove={move}
		onpointerleave={leave}
		onclick={click}
	>
		<!-- je Ebene der Schein hinter der Figur (nur am Rand nach außen sichtbar, Hände und Beine bleiben frei)
		     und das aufgehellte Teil darüber -->
		{#each layers as [slot, src] (slot)}
			<img class="halo" class:lit={lit(slot)} {src} alt="" aria-hidden="true" onerror={hide} />
		{/each}
		<img class="base" src={info.figure} alt="" onerror={hide} />
		{#each layers as [slot, src] (slot)}
			<img class="layer" class:lit={lit(slot)} {src} alt="" aria-hidden="true" onerror={hide} />
			<div class="tint" class:lit={lit(slot)} style:--mask="url({src})" aria-hidden="true"></div>
		{/each}
		{#each zones as z, i (i)}
			<button
				class="zone"
				class:lit={active === z.slot}
				class:own={hasLayer(z.slot)}
				style:left="{z.x}%"
				style:top="{z.y}%"
				style:width="{z.w}%"
				style:height="{z.h}%"
				aria-label={names.get(z.slot)}
				onmouseenter={() => (active = z.slot)}
				onfocus={() => (active = z.slot)}
				onclick={() => onPick(z.slot)}
			></button>
		{/each}
	</div>
{/if}

<style>
	/* Die Stellen sind in Prozent des Bildes angegeben: der Rahmen ist genau so groß wie das Bild.
	   Licht in der Klassenfarbe dahinter */
	.figure {
		position: relative;
	}
	.figure::before {
		content: '';
		position: absolute;
		inset: 0;
		background: radial-gradient(ellipse 55% 40% at 50% 55%, color-mix(in srgb, var(--glow) 30%, transparent), transparent);
		transition: opacity 0.45s ease-in-out;
	}
	/* Licht wandert ins Teil: Klassenlicht um die Figur blendet aus, während sich der Schein am Teil zusammenzieht */
	.figure.focus::before {
		opacity: 0;
	}
	.base {
		transition: filter 0.45s ease-in-out;
	}
	.figure.focus .base {
		filter: drop-shadow(0 0 24px color-mix(in srgb, var(--glow) 0%, transparent));
	}
	.figure.pointing {
		cursor: pointer;
	}
	img {
		display: block;
		width: 100%;
		height: auto;
		filter: drop-shadow(0 0 24px color-mix(in srgb, var(--glow) 40%, transparent));
	}
	.zone {
		position: absolute;
		padding: 0;
		border: 0;
		border-radius: 6px;
		background: none;
		cursor: pointer;
	}
	/* Plätze mit Ebene: die Maus geht durch zur Figur, die Knöpfe bleiben für die Tastatur */
	.zone.own {
		pointer-events: none;
	}
	.zone:not(.own):hover,
	.zone.lit:not(.own),
	.zone:not(.own):focus-visible {
		background: color-mix(in srgb, var(--glow) 18%, transparent);
		outline: 1px solid color-mix(in srgb, var(--glow) 70%, #fff);
		box-shadow: 0 0 14px color-mix(in srgb, var(--glow) 60%, transparent);
	}
	.base {
		position: relative;
	}
	/* Ebenen eines Platzes genau über bzw. unter der Figur, nur beim Zeigen sichtbar */
	.halo,
	.layer,
	.tint {
		position: absolute;
		inset: 0;
		pointer-events: none;
		opacity: 0;
		filter: none;
		transition: opacity 0.35s ease-out;
	}
	.halo.lit,
	.layer.lit {
		opacity: 1;
	}
	/* Klassenfarbe im Teil selbst (Fläche in der Form der Ebene), sonst sähe man innen liegende Teile wie die
	   Brust kaum leuchten */
	.tint {
		background: var(--glow);
		mask: var(--mask) center / 100% 100% no-repeat;
		-webkit-mask: var(--mask) center / 100% 100% no-repeat;
		mix-blend-mode: screen;
	}
	.tint.lit {
		opacity: 0.32;
	}
	/* Licht in der Klassenfarbe, liegt hinter der Figur; aus weitem Schein zieht es sich ans Teil */
	.halo {
		filter: drop-shadow(0 0 30px color-mix(in srgb, var(--glow) 90%, #fff)) drop-shadow(0 0 60px var(--glow))
			drop-shadow(0 0 90px color-mix(in srgb, var(--glow) 60%, transparent));
		transition:
			opacity 0.35s ease-out,
			filter 0.5s ease-out;
	}
	.halo.lit {
		filter: drop-shadow(0 0 4px color-mix(in srgb, var(--glow) 90%, #fff)) drop-shadow(0 0 14px var(--glow))
			drop-shadow(0 0 30px color-mix(in srgb, var(--glow) 60%, transparent));
	}
	/* das Teil selbst nur aufgehellt, ohne Rand: ein Rand zeichnete die Schnittkanten zu den Nachbarteilen nach */
	.layer.lit {
		filter: brightness(1.3) saturate(1.1);
	}
	@media (prefers-reduced-motion: reduce) {
		.figure::before,
		.base,
		.halo,
		.layer,
		.tint {
			transition: none;
		}
	}
</style>
