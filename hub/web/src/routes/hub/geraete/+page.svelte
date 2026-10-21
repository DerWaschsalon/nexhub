<!-- Geräte: NexBoards per Code koppeln und gekoppelte entfernen.
     Der Daemon verlinkt hierher mit ?code=…, dann ist das Feld schon ausgefüllt. -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api, type Device } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import { formatDateTime } from '#lib/format.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	let code = $state(page.url.searchParams.get('code') ?? '');
	let name = $state('');
	let busy = $state(false);
	let error = $state('');
	let paired = $state('');

	async function approve(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = paired = '';
		try {
			const r = await api<{ name: string }>('/api/devices/pair/approve', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ code, name: name.trim() || null })
			});
			paired = r.name;
			code = name = '';
			// Der Daemon holt sein Token beim nächsten Nachfragen (alle 5 s), dann erscheint er unten
			setTimeout(invalidateAll, 6000);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	async function remove(device: Device) {
		if (!confirm(`${device.name} entfernen? Das Gerät muss danach neu gekoppelt werden.`)) return;
		try {
			await api<void>(`/api/devices/${device.id}`, { method: 'DELETE' });
			await invalidateAll();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

<header class="page-head">
	<h1>Geräte</h1>
	<p>NexBoards, die mit deinem Konto verbunden sind.</p>
</header>

<section class="glass pad pair">
	<h2>Gerät koppeln</h2>
	<p class="dim">
		In NexBoard das Modul „NexHub“ öffnen und auf „Koppeln“ klicken. Den angezeigten Code hier
		eingeben.
	</p>
	<form onsubmit={approve}>
		<label>
			<span>Code</span>
			<input class="code" bind:value={code} placeholder="BCDF-GHJK" autocomplete="off" spellcheck="false" required />
		</label>
		<label>
			<span>Name (optional)</span>
			<input bind:value={name} placeholder="z. B. Gaming-PC" maxlength="64" />
		</label>
		<button class="btn primary" disabled={busy || !code.trim()}>Koppeln</button>
	</form>
	{#if paired}
		<p class="notice ok" role="status">„{paired}“ ist bestätigt. NexBoard meldet sich in wenigen Sekunden.</p>
	{/if}
	{#if error}
		<p class="notice error" role="alert">{error}</p>
	{/if}
</section>

{#if data.devices.length}
	<section class="glass pad table-wrap">
		<table class="table">
			<thead>
				<tr>
					<th>Gerät</th>
					<th>Gekoppelt</th>
					<th>Zuletzt gesehen</th>
					<th>Version</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{#each data.devices as device (device.id)}
					<tr>
						<td><span class="name"><Icon name="device" /> {device.name}</span></td>
						<td class="dim">{formatDateTime(device.created_at)}</td>
						<td class="dim">{device.last_seen_at ? formatDateTime(device.last_seen_at) : '–'}</td>
						<td class="dim">{device.version ?? '–'}</td>
						<td class="actions">
							<button class="btn small danger" onclick={() => remove(device)}>Entfernen</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>
{:else}
	<p class="dim empty">Noch kein Gerät gekoppelt.</p>
{/if}

<style>
	.pair {
		margin-bottom: 18px;
	}
	h2 {
		font-size: 18px;
		margin-bottom: 4px;
	}
	.pair > p {
		margin: 0 0 16px;
	}
	form {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		align-items: flex-end;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 6px;
		flex: 1 1 200px;
		font-size: 13px;
		color: var(--dim);
	}
	input {
		font: inherit;
		font-size: 16px;
		color: var(--text);
		background: rgba(0, 0, 0, 0.3);
		border: 1px solid var(--edge);
		border-radius: var(--radius-sm);
		padding: 10px 12px;
	}
	input.code {
		letter-spacing: 0.08em;
	}
	input:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 3px rgba(106, 211, 255, 0.18);
	}
	.notice {
		margin: 16px 0 0;
	}
	.notice.ok {
		border-color: rgba(74, 222, 128, 0.4);
		background: rgba(74, 222, 128, 0.1);
	}
	.name {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		font-weight: 600;
	}
	.actions {
		text-align: right;
	}
	.empty {
		padding: 0 4px;
	}
</style>
