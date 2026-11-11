<!-- Gegenstand wie im Spiel: Symbol vom NCSOFT-CDN im Rahmen der Seltenheit, Verzauberung und
     Durchbruch an den Ecken, Name als Tooltip. `filled`: Platz wie im Ausrüstungsfenster, mit der
     Farbe der Seltenheit hinterlegt. -->
<script lang="ts">
	import { gradeColor } from '../grades.ts';

	let {
		name,
		icon,
		grade = null,
		enchant = 0,
		exceed = 0,
		size = 48,
		filled = false
	}: {
		name: string;
		icon: string | null;
		grade?: string | null;
		enchant?: number;
		exceed?: number;
		size?: number;
		filled?: boolean;
	} = $props();

	const color = $derived(gradeColor(grade));
</script>

<span class="item" class:filled style:--grade={color} style:width="{size}px" style:height="{size}px" style:border-color={color} title={name}>
	{#if icon}
		<img src={icon} alt={name} width={size - 6} height={size - 6} loading="lazy" referrerpolicy="no-referrer" />
	{/if}
	{#if enchant}<span class="enchant">+{enchant}</span>{/if}
	{#if exceed}<span class="exceed">{exceed}</span>{/if}
</span>

<style>
	.item {
		position: relative;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: 2px solid;
		border-radius: 10px;
		background: rgba(0, 0, 0, 0.32);
		flex-shrink: 0;
	}
	img {
		object-fit: contain;
		border-radius: 7px;
	}
	.enchant,
	.exceed {
		position: absolute;
		font-size: 11px;
		font-weight: 700;
		line-height: 1;
		padding: 2px 4px;
		border-radius: 6px;
		background: rgba(0, 0, 0, 0.75);
	}
	.enchant {
		right: 1px;
		bottom: 1px;
	}
	.exceed {
		left: 1px;
		top: 1px;
		color: var(--warn);
	}
	/* Platz im Ausrüstungsfenster: eckig, Seltenheit als Verlauf, Zahlen ohne Kasten */
	.filled {
		border-width: 1.5px;
		border-radius: 2px;
		background: radial-gradient(circle at 40% 30%, color-mix(in srgb, var(--grade) 62%, #000),
			color-mix(in srgb, var(--grade) 28%, #000));
	}
	.filled img {
		border-radius: 0;
	}
	.filled .enchant {
		right: 5px;
		bottom: 3px;
		padding: 0;
		background: none;
		font-size: 15px;
		color: #fff;
		text-shadow: 0 1px 3px #000, 0 0 2px #000;
	}
	.filled .exceed {
		top: auto;
		left: 5px;
		bottom: 5px;
		display: grid;
		place-items: center;
		width: 20px;
		height: 20px;
		padding: 0;
		border-radius: 50%;
		background: #2ec4c9;
		color: #fff;
		font-size: 12px;
	}
</style>
