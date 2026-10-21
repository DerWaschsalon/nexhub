<!-- Geräte: NexBoards per Code koppeln und gekoppelte entfernen.
     Der Daemon verlinkt hierher mit ?code=…, dann ist das Feld schon ausgefüllt. -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import { formatDateTime } from '#lib/format.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import type { Device } from '#modules/devices/api.ts';
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
		if (!confirm(t('devices.confirmRemove', { name: device.name }))) return;
		try {
			await api<void>(`/api/devices/${device.id}`, { method: 'DELETE' });
			await invalidateAll();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

<header class="page-head">
	<h1>{t('devices.title')}</h1>
	<p>{t('devices.intro')}</p>
</header>

<section class="glass pad pair">
	<h2>{t('devices.pair')}</h2>
	<p class="dim">{t('devices.pairHow')}</p>
	<form onsubmit={approve}>
		<label>
			<span>{t('devices.code')}</span>
			<input class="code" bind:value={code} placeholder="BCDF-GHJK" autocomplete="off" spellcheck="false" required />
		</label>
		<label>
			<span>{t('devices.name')}</span>
			<input bind:value={name} placeholder={t('devices.namePlaceholder')} maxlength="64" />
		</label>
		<button class="btn primary" disabled={busy || !code.trim()}>{t('devices.pairButton')}</button>
	</form>
	{#if paired}
		<p class="notice ok" role="status">{t('devices.paired', { name: paired })}</p>
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
					<th>{t('devices.col.device')}</th>
					<th>{t('devices.col.paired')}</th>
					<th>{t('devices.col.seen')}</th>
					<th>{t('devices.col.version')}</th>
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
							<button class="btn small danger" onclick={() => remove(device)}>{t('devices.remove')}</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>
{:else}
	<p class="dim empty">{t('devices.none')}</p>
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
