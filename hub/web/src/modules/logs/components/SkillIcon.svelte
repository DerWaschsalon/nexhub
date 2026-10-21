<!-- Symbol einer Fähigkeit (code, vom Spiel-CDN, siehe skillIcons.ts) oder eines Buffs (src).
     Standardangriffe bekommen gekreuzte Schwerter wie im Meter, Unbekanntes ein leeres Feld. -->
<script lang="ts">
	import { skillIcon } from '../skillIcons.ts';

	let { code = null, src, size = 28 }: { code?: number | null; src?: string | null; size?: number } = $props();

	const icon = $derived(src !== undefined ? src : skillIcon(code));
	let broken = $state(false);
</script>

{#if icon && icon !== 'auto' && !broken}
	<img class="icon" src={icon} width={size} height={size} alt="" loading="lazy" referrerpolicy="no-referrer"
		onerror={() => (broken = true)} />
{:else}
	<span class="icon fallback" style:width="{size}px" style:height="{size}px" aria-hidden="true">
		{#if icon === 'auto'}
			<!-- Lucide „swords“ -->
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<path d="M14.5 17.5 3 6V3h3l11.5 11.5M13 19l6-6M16 16l4 4M19 21l2-2M14.5 6.5 18 3h3v3l-3.5 3.5M5 14l4 4M7 17l-3 3M3 19l2 2" />
			</svg>
		{/if}
	</span>
{/if}

<style>
	.icon {
		flex-shrink: 0;
		border-radius: 7px;
		border: 1px solid var(--edge-soft);
		background: rgba(0, 0, 0, 0.35);
	}
	.fallback {
		display: inline-grid;
		place-items: center;
		color: var(--dim);
	}
	svg {
		width: 60%;
		height: 60%;
	}
</style>
