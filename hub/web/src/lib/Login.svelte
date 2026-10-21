<script lang="ts">
	import { page } from '$app/state';
	import type { Health } from '#lib/api.ts';

	let { health }: { health: Health } = $props();

	const MESSAGES: Record<string, string> = {
		abgelaufen: 'Die Anmeldung hat zu lange gedauert. Bitte noch einmal versuchen.',
		abgebrochen: 'Die Anmeldung bei Discord wurde abgebrochen.',
		ungueltig: 'Die Anmeldung war ungültig. Bitte noch einmal versuchen.',
		discord: 'Discord hat nicht geantwortet. Bitte später noch einmal versuchen.',
		nicht_freigeschaltet: 'Dein Discord-Konto ist noch nicht freigeschaltet.'
	};

	const error = $derived(page.url.searchParams.get('fehler'));
	const discordId = $derived(page.url.searchParams.get('id'));
	const next = $derived(page.url.pathname === '/' ? '/' : page.url.pathname + page.url.search);
</script>

<main class="login">
	<section class="card">
		<h1>NexHub</h1>
		<p class="dim">Runs, Geräte und Ranglisten für den Waschsalon.</p>

		{#if error}
			<div class="notice" role="alert">
				<p>{MESSAGES[error] ?? 'Die Anmeldung ist fehlgeschlagen.'}</p>
				{#if error === 'nicht_freigeschaltet' && discordId}
					<p class="dim">Gib diese Discord-ID an einen Admin weiter:</p>
					<code>{discordId}</code>
				{/if}
			</div>
		{/if}

		{#if health.login}
			<a class="button" href="/api/auth/login?next={encodeURIComponent(next)}">Mit Discord anmelden</a>
		{:else}
			<p class="notice">
				{health.ok ? 'Der Discord-Login ist auf diesem Server noch nicht eingerichtet.' : 'Der Hub ist gerade nicht erreichbar.'}
			</p>
		{/if}
	</section>
</main>

<style>
	.login {
		min-height: 100vh;
		display: grid;
		place-items: center;
		padding: 16px;
	}
	.card {
		width: min(420px, 100%);
		text-align: center;
		padding: 36px 28px;
	}
	h1 {
		font-size: 28px;
		margin-bottom: 6px;
	}
	.dim {
		margin: 0 0 24px;
	}
	.notice {
		text-align: left;
		margin: 0 0 20px;
		padding: 12px 14px;
		border-radius: 10px;
		background: rgba(255, 159, 10, 0.12);
		border: 1px solid rgba(255, 159, 10, 0.35);
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
		font-size: 15px;
		padding: 8px 10px;
		border-radius: 8px;
		background: rgba(0, 0, 0, 0.3);
	}
	.button {
		display: block;
		width: 100%;
	}
</style>
