<!-- Fehlermeldung einer Seite (unbekannte Adresse, API antwortet nicht) mit dem Weg zurück. -->
<script lang="ts">
	import { page } from '$app/state';
	import { t } from '#lib/i18n.svelte.ts';

	let { home = '/' }: { home?: string } = $props();

	// SvelteKit meldet eine unbekannte Adresse auf Englisch; alles andere kommt von der API
	const message = $derived(page.status === 404 && page.error?.message === 'Not Found'
		? t('error.notFound')
		: (page.error?.message ?? t('error.fallback')));
</script>

<svelte:head><title>{page.status} · NexHub</title></svelte:head>

<section class="glass pad card">
	<h1>{page.status}</h1>
	<p class="dim">{message}</p>
	<a class="btn" href={home}>{t(home === '/' ? 'error.home' : 'error.overview')}</a>
</section>

<style>
	.card {
		max-width: 440px;
		margin: 14vh auto 0;
		text-align: center;
	}
	h1 {
		font-size: 44px;
	}
	p {
		margin: 6px 0 22px;
	}
</style>
