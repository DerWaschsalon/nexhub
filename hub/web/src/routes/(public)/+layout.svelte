<!-- Öffentlicher Bereich: ohne Login sichtbar (Startseite, Login, geteilte Runs). -->
<script lang="ts">
	import { page } from '$app/state';
	import Brand from '#lib/components/Brand.svelte';
	import LangSwitch from '#lib/components/LangSwitch.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
</script>

<header class="glass">
	<Brand />
	<div class="right">
		<LangSwitch />
		{#if data.me}
			<a class="btn primary small" href="/hub">{t('shell.toHub')}</a>
		{:else if page.url.pathname !== '/login'}
			<a class="btn small" href="/login">{t('shell.login')}</a>
		{/if}
	</div>
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
	.right {
		display: flex;
		align-items: center;
		gap: 10px;
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
