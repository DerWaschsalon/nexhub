<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<section class="hero">
	<h1>{t('home.title')}</h1>
	<p class="dim">{t('home.text')}</p>
	<div class="actions">
		{#if data.me}
			<a class="btn primary large" href="/hub">{t('shell.toHub')}</a>
		{:else}
			<a class="btn primary large" href="/login">{t('home.login')}</a>
		{/if}
	</div>
</section>

<style>
	.hero {
		max-width: 720px;
		margin: 8vh auto 0;
		text-align: center;
	}
	h1 {
		font-size: clamp(32px, 6vw, 54px);
		line-height: 1.08;
		letter-spacing: -0.03em;
		background: linear-gradient(135deg, #fff 30%, var(--accent) 70%, var(--accent-2));
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
	}
	p {
		font-size: 17px;
		margin: 20px auto 32px;
		max-width: 560px;
	}
</style>
