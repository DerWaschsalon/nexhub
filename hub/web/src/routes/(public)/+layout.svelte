<!-- Öffentlicher Bereich: ohne Login sichtbar. Hier landen später geteilte Runs. -->
<script lang="ts">
	import { page } from '$app/state';
	import Brand from '#lib/components/Brand.svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
</script>

<header class="glass">
	<Brand />
	{#if data.me}
		<a class="btn primary small" href="/hub">Zum Hub</a>
	{:else if page.url.pathname !== '/login'}
		<a class="btn small" href="/login">Anmelden</a>
	{/if}
</header>

<main>
	{@render children()}
</main>

<style>
	header {
		position: sticky;
		top: 12px;
		z-index: 10;
		display: flex;
		align-items: center;
		justify-content: space-between;
		max-width: 1100px;
		margin: 12px auto 0;
		min-height: 56px;
		padding: 10px 12px 10px 18px;
		border-radius: 999px;
	}
	main {
		max-width: 1100px;
		margin: 0 auto;
		padding: 48px 16px;
	}
	@media (max-width: 1132px) {
		header {
			margin: 12px 16px 0;
		}
	}
</style>
