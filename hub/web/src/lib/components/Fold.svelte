<!-- Akkordeon-Abschnitt: Die Überschrift bleibt stehen, ein Klick zeigt den Inhalt darunter. Mit `id` merkt
     sich der Browser, ob der Abschnitt offen war. Aussehen aus tokens.css (details.fold). -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	const KEY = 'nexhub.fold';

	let { title, hint, id, open = false, children }:
		{ title: string; hint?: string; id?: string; open?: boolean; children: Snippet } = $props();

	const states = (): Record<string, boolean> => JSON.parse(localStorage.getItem(KEY) ?? '{}');
	// nur der Anfangszustand: danach führt der Browser das <details> selbst
	const wasOpen = (fallback: boolean) => (id ? (states()[id] ?? fallback) : fallback);

	function remember(event: Event) {
		if (id) localStorage.setItem(KEY, JSON.stringify({ ...states(), [id]: (event.currentTarget as HTMLDetailsElement).open }));
	}
</script>

<details class="glass fold" open={wasOpen(open)} ontoggle={remember}>
	<summary>
		<span class="head">
			<strong>{title}</strong>
			{#if hint}<small class="dim">{hint}</small>{/if}
		</span>
	</summary>
	<div class="body">{@render children()}</div>
</details>

<style>
	details {
		padding: 0;
	}
	summary {
		padding: 16px 20px;
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 4px 12px;
		min-width: 0;
	}
	strong {
		font-family: var(--font-heading);
		font-size: 15px;
		font-weight: 600;
	}
	.body {
		padding: 0 20px 20px;
	}
</style>
