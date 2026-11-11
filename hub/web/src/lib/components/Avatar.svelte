<!-- Discord-Avatar; ohne Bild der erste Buchstabe auf Glas. -->
<script lang="ts">
	let { name, url, size = 32 }: { name: string; url: string | null; size?: number } = $props();
</script>

{#if url}
	<img src={url} alt="" width={size} height={size} style:--size="{size}px" />
{:else}
	<span style:--size="{size}px" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>
{/if}

<style>
	img,
	span {
		width: var(--size);
		height: var(--size);
		border-radius: 50%;
		flex-shrink: 0;
		border: 1px solid var(--edge);
	}
	span {
		display: inline-grid;
		place-items: center;
		font-weight: 650;
		font-size: calc(var(--size) * 0.45);
		background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 35%, transparent), color-mix(in srgb, var(--accent-2) 35%, transparent));
	}
</style>
