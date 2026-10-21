<!-- Login-Seite. Die API schickt Fehler als ?fehler=… hierher zurück. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const MESSAGES: Record<string, string> = {
		abgelaufen: 'Die Anmeldung hat zu lange gedauert. Bitte noch einmal versuchen.',
		abgebrochen: 'Die Anmeldung bei Discord wurde abgebrochen.',
		ungueltig: 'Die Anmeldung war ungültig. Bitte noch einmal versuchen.',
		discord: 'Discord hat nicht geantwortet. Bitte später noch einmal versuchen.',
		nicht_freigeschaltet: 'Dein Discord-Konto ist noch nicht freigeschaltet.',
		gesperrt: 'Dein Konto ist gesperrt. Wende dich an einen Admin.'
	};

	const params = $derived(page.url.searchParams);
	const error = $derived(params.get('fehler'));
	const next = $derived(params.get('next') ?? '/hub');

	// Schon angemeldet: direkt weiter
	$effect(() => {
		if (data.me) goto(next, { replaceState: true });
	});
</script>

<section class="glass pad card">
	<h1>Anmelden</h1>
	<p class="dim">NexHub nutzt dein Discord-Konto. Zugang haben die freigeschalteten Mitglieder.</p>

	{#if error}
		<div class="notice error" role="alert">
			<p>{MESSAGES[error] ?? 'Die Anmeldung ist fehlgeschlagen.'}</p>
			{#if error === 'nicht_freigeschaltet' && params.get('id')}
				<p class="dim">Gib diese Discord-ID an einen Admin weiter:</p>
				<code>{params.get('id')}</code>
			{/if}
		</div>
	{/if}

	{#if data.info.login}
		<a class="btn primary large" href="/api/auth/login?next={encodeURIComponent(next)}">
			Mit Discord anmelden
		</a>
	{:else}
		<p class="notice">Der Discord-Login ist auf diesem Server noch nicht eingerichtet.</p>
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
