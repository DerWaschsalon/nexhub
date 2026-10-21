<!-- Benachrichtigungen: GitHub/YouTube-Quellen pausieren oder löschen. Neu anlegen geht in
     Discord, weil der Assistent dort eine Vorschau zeigt. -->
<script lang="ts">
	import { send } from '#lib/api.ts';
	import { BOT_API, type Feed } from '#modules/bot/api.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// svelte-ignore state_referenced_locally
	let feeds = $state<Feed[]>(data.feeds);
	let error = $state('');

	async function toggle(f: Feed) {
		error = '';
		try {
			feeds = await send<Feed[]>(`${BOT_API}/notifications/${f.id}/toggle`, 'POST');
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function remove(f: Feed) {
		if (!confirm(`${f.source} löschen?`)) return;
		error = '';
		try {
			await send<void>(`${BOT_API}/notifications/${f.id}`, 'DELETE');
			feeds = feeds.filter((x) => x.id !== f.id);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

<p class="dim lead">
	Neue Quellen legst du in Discord an: Einstellungen-Kanal, „Benachrichtigungen“, „Neue Benachrichtigung“.
</p>

{#if error}<p class="notice error" role="alert">{error}</p>{/if}

{#if feeds.length}
	<section class="glass pad table-wrap">
		<table class="table">
			<thead><tr><th>Quelle</th><th>Ereignisse</th><th>Kanal</th><th>Status</th><th></th></tr></thead>
			<tbody>
				{#each feeds as f (f.id)}
					<tr>
						<td><span class="dim">{f.kind}</span> <strong>{f.source}</strong></td>
						<td class="dim">{f.events.join(', ') || '–'}</td>
						<td>{f.channel ? `#${f.channel}` : 'Kanal gelöscht'}</td>
						<td>
							<span class="chip" class:ok={f.enabled && !f.error} class:danger={!!f.error}>
								{f.error ? 'Fehler' : f.enabled ? 'aktiv' : 'pausiert'}
							</span>
							{#if f.error}<div class="err">{f.error}</div>{/if}
						</td>
						<td class="actions">
							<button class="btn small" onclick={() => toggle(f)}>{f.enabled ? 'Pausieren' : 'Fortsetzen'}</button>
							<button class="btn small danger" onclick={() => remove(f)}>Löschen</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>
{:else}
	<p class="dim empty">Noch keine Benachrichtigung eingerichtet.</p>
{/if}

<style>
	.lead {
		margin: -6px 4px 16px;
	}
	.notice {
		margin: 0 0 16px;
	}
	.err {
		margin-top: 4px;
		font-size: 12px;
		color: var(--danger);
		max-width: 240px;
	}
	.actions {
		text-align: right;
		white-space: nowrap;
	}
	.empty {
		margin: 0 4px;
	}
</style>
