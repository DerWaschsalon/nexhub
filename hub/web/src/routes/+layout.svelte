<script lang="ts">
	import '../app.css';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<title>NexHub</title>
	<link rel="icon" href="/favicon.svg" />
</svelte:head>

<div class="backdrop" aria-hidden="true"><span></span><span></span><span></span></div>
{@render children()}
