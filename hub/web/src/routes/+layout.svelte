<script lang="ts">
	import '../app.css';
	import { i18n } from '#lib/i18n.svelte.ts';
	import '#lib/modules.ts'; // meldet Kern- und Modultexte an
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	$effect(() => {
		document.documentElement.lang = i18n.lang;
	});
</script>

<svelte:head>
	<title>NexHub</title>
	<link rel="icon" href="/favicon.svg" />
</svelte:head>

<div class="backdrop" aria-hidden="true"><span></span><span></span><span></span></div>
{@render children()}
