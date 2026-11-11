<!-- Figur der Klasse im Klassenlicht mit den Stellen der Ausrüstung (data/figureZones.ts): Zeigen auf eine
     Stelle hebt sie und ihren Platz hervor (`active`, gemeinsam mit der Ausrüstungsspalte), ein Klick meldet
     den Platz (onPick). Stellen gibt es nur für Plätze mit Gegenstand (`slots`); kleine liegen über großen. -->
<script lang="ts">
	import { classInfo } from '../classes.ts';
	import { FIGURE_ZONES } from '../data/figureZones.ts';

	let {
		cls,
		slots,
		active = $bindable(null),
		onPick
	}: { cls: string | null; slots: Set<string>; active?: string | null; onPick: (slot: string) => void } = $props();

	const info = $derived(classInfo(cls));
	const zones = $derived(
		[...((cls && FIGURE_ZONES[cls]) || [])]
			.filter((z) => slots.has(z.slot))
			.sort((a, b) => b.w * b.h - a.w * a.h)
	);
	// Für manche Klassen gibt es noch keine Figur (Faustkämpfer): dann bleibt die Mitte leer
	const hide = (e: Event) => ((e.currentTarget as HTMLImageElement).style.visibility = 'hidden');
</script>

{#if info}
	<div class="stage" style:--glow={info.color}>
		<div class="figure">
			<img src={info.figure} alt="" onerror={hide} />
			{#each zones as z, i (i)}
				<button
					class="zone"
					class:lit={active === z.slot}
					style:left="{z.x}%"
					style:top="{z.y}%"
					style:width="{z.w}%"
					style:height="{z.h}%"
					aria-label={z.slot}
					onmouseenter={() => (active = z.slot)}
					onmouseleave={() => (active = null)}
					onclick={() => onPick(z.slot)}
				></button>
			{/each}
		</div>
	</div>
{/if}

<style>
	/* Licht in der Klassenfarbe hinter der Figur */
	.stage {
		padding-top: 30px;
		background: radial-gradient(ellipse 55% 40% at 50% 60%, color-mix(in srgb, var(--glow) 30%, transparent), transparent);
	}
	/* Die Stellen sind in Prozent des Bildes angegeben: der Rahmen ist genau so groß wie das Bild */
	.figure {
		position: relative;
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
	.zone:hover,
	.zone.lit,
	.zone:focus-visible {
		background: color-mix(in srgb, var(--glow) 18%, transparent);
		outline: 1px solid color-mix(in srgb, var(--glow) 70%, #fff);
		box-shadow: 0 0 14px color-mix(in srgb, var(--glow) 60%, transparent);
	}
</style>
