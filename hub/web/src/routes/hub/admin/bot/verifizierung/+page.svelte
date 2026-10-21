<!-- Verifizierung: Stand anzeigen und den Regel-Text im Panel ändern. Einrichten selbst geht nur
     in Discord, weil es Rechte auf dem ganzen Server umstellt. -->
<script lang="ts">
	import { BOT_API, send } from '#lib/api.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const v = $derived(data.verification);

	// svelte-ignore state_referenced_locally
	let text = $state(data.verification.text ?? '');
	let busy = $state(false);
	let error = $state('');
	let ok = $state('');

	async function save(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = ok = '';
		try {
			await send<void>(`${BOT_API}/verification/text`, 'PUT', { text });
			ok = 'Regel-Text im Panel geändert.';
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}
</script>

<p class="dim lead">Neue Mitglieder sehen erst die Regeln und schalten sich mit einem Klick frei.</p>

<section class="glass pad">
	<dl>
		<dt>Regel-Kanal</dt>
		<dd>{v.channel ? `#${v.channel}` : 'nicht eingerichtet'}</dd>
		<dt>Rolle nach dem Freischalten</dt>
		<dd>{v.role ?? 'nicht eingerichtet'}</dd>
	</dl>
	<p class="dim">Kanal, Rolle und Rechte richtest du mit <code>/setup verifizierung</code> in Discord ein.</p>
</section>

<form class="glass pad" onsubmit={save}>
	<label class="field">
		<span>Regel-Text im Panel</span>
		<textarea class="input" bind:value={text} maxlength="4096" rows="10" disabled={!v.panel}></textarea>
		{#if !v.panel}<span class="hint">Es gibt noch kein Panel. Erst in Discord einrichten.</span>{/if}
	</label>
	<div class="bar">
		<button class="btn primary" disabled={busy || !v.panel || !text.trim()}>Text ändern</button>
		{#if ok}<span class="notice ok" role="status">{ok}</span>{/if}
	</div>
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
</form>

<style>
	.lead {
		margin: -6px 4px 16px;
	}
	section {
		margin-bottom: 16px;
	}
	dl {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 8px 18px;
		margin: 0 0 12px;
	}
	dt {
		color: var(--dim);
	}
	dd {
		margin: 0;
		font-weight: 600;
	}
	section p {
		margin: 0;
	}
	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 14px;
		margin-top: 14px;
	}
	.bar .notice {
		padding: 6px 12px;
	}
	.notice.error {
		margin: 14px 0 0;
	}
</style>
