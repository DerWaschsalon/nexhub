<!-- Login-Seite. Die API schickt Fehler als ?fehler=… hierher zurück. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { t } from '#lib/i18n.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Fehlercodes der API (?fehler=…), Texte in lib/texts.ts
	const ERRORS = ['abgelaufen', 'abgebrochen', 'ungueltig', 'discord', 'nicht_freigeschaltet', 'gesperrt'];

	const params = $derived(page.url.searchParams);
	const error = $derived(params.get('fehler'));
	const next = $derived(params.get('next') ?? '/hub');

	// Schon angemeldet: direkt weiter
	$effect(() => {
		if (data.me) goto(next, { replaceState: true });
	});
</script>

<section class="glass pad card">
	<h1>{t('login.title')}</h1>
	<p class="dim">{t('login.text')}</p>

	{#if error}
		<div class="notice error" role="alert">
			<p>{t(ERRORS.includes(error) ? `login.err.${error}` : 'login.err.other')}</p>
			{#if error === 'nicht_freigeschaltet' && params.get('id')}
				<p class="dim">{t('login.giveId')}</p>
				<code>{params.get('id')}</code>
			{/if}
		</div>
	{/if}

	{#if data.info.login}
		<a class="btn primary large" href="/api/auth/login?next={encodeURIComponent(next)}">
			{t('login.button')}
		</a>
	{:else}
		<p class="notice">{t('login.off')}</p>
	{/if}
</section>

<style>
	.card {
		max-width: 440px;
		margin: 6vh auto 0;
		text-align: center;
		padding: 36px 28px;
	}
	h1 {
		font-size: 28px;
	}
	.card > p {
		margin: 8px 0 24px;
	}
	.notice {
		text-align: left;
		margin: 0 0 20px;
	}
	.notice p {
		margin: 0 0 6px;
	}
	.notice p:last-child {
		margin: 0;
	}
	code {
		display: block;
		user-select: all;
		padding: 8px 10px;
		border-radius: 8px;
		background: rgba(0, 0, 0, 0.35);
	}
	.btn.large {
		width: 100%;
	}
</style>
