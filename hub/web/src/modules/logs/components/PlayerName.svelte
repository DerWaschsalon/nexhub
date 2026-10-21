<!-- Spielername in Klassenfarbe mit Klassensymbol davor; ohne bekannte Klasse ein neutraler Punkt. -->
<script lang="ts">
	import { classInfo } from '../classes.ts';

	let { name, cls, size = 22 }: { name: string; cls: string | null; size?: number } = $props();
	const info = $derived(classInfo(cls));
</script>

<span class="player">
	{#if info}
		<img src={info.icon} alt={info.label} title={info.label} width={size} height={size} />
	{:else}
		<span class="dot" style:width="{size}px" style:height="{size}px" aria-hidden="true"></span>
	{/if}
	<span class="name" style:color={info?.color}>{name}</span>
</span>

<style>
	.player {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font-weight: 600;
		min-width: 0;
	}
	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	img {
		flex-shrink: 0;
		object-fit: contain;
	}
	.dot {
		flex-shrink: 0;
		border-radius: 50%;
		background: rgba(255, 255, 255, 0.12);
	}
</style>
