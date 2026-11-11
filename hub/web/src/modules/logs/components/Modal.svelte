<!-- Fenster über der Seite (<dialog>): offen, solange `open` gilt. Escape oder ein Klick daneben rufen
     onclose; den Inhalt bringt der Aufrufer mit. -->
<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		open,
		onclose,
		width = 480,
		children
	}: { open: boolean; onclose: () => void; width?: number; children: Snippet } = $props();
	let dialog: HTMLDialogElement | undefined = $state();

	$effect(() => {
		if (open && !dialog?.open) dialog?.showModal();
		if (!open && dialog?.open) dialog.close();
	});

	// Ein Klick auf den abgedunkelten Rand trifft den <dialog> selbst, nicht seinen Inhalt
	function closeOnBackdrop(e: MouseEvent) {
		if (e.target === dialog) onclose();
	}
</script>

<dialog bind:this={dialog} style:--width="{width}px" onclick={closeOnBackdrop} onclose={onclose}>
	{#if open}{@render children()}{/if}
</dialog>

<style>
	dialog {
		padding: 0;
		border: 0;
		background: none;
		color: inherit;
		width: min(var(--width), calc(100vw - 32px));
		max-height: calc(100vh - 48px);
	}
	dialog::backdrop {
		background: rgba(0, 0, 0, 0.45);
	}
</style>
