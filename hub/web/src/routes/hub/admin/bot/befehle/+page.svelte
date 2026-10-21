<!-- Eigene Befehle: „!name“ im Chat, der Bot antwortet mit festem Text. -->
<script lang="ts">
	import { send } from '#lib/api.ts';
	import { BOT_API, type CustomCommand } from '#modules/bot/api.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// svelte-ignore state_referenced_locally
	let items = $state<CustomCommand[]>(data.commands);
	let name = $state('');
	let response = $state('');
	let error = $state('');

	const clean = $derived(name.trim().toLowerCase().replace(/^!/, ''));
	const exists = $derived(items.some((c) => c.name === clean));

	function edit(c: CustomCommand) {
		name = c.name;
		response = c.response;
		document.getElementById('befehl-name')?.focus();
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		try {
			items = await send<CustomCommand[]>(`${BOT_API}/commands/${encodeURIComponent(clean)}`, 'PUT', { response });
			name = response = '';
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function remove(c: CustomCommand) {
		if (!confirm(`!${c.name} löschen?`)) return;
		error = '';
		try {
			await send<void>(`${BOT_API}/commands/${encodeURIComponent(c.name)}`, 'DELETE');
			items = items.filter((x) => x.name !== c.name);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

<p class="dim lead">Schreibt jemand <code>!name</code> in den Chat, antwortet der Bot mit dem Text.</p>

{#if items.length}
	<section class="glass pad table-wrap">
		<table class="table">
			<thead><tr><th>Befehl</th><th>Antwort</th><th></th></tr></thead>
			<tbody>
				{#each items as c (c.name)}
					<tr>
						<td><code>!{c.name}</code></td>
						<td class="resp">{c.response}</td>
						<td class="actions">
							<button class="btn small" onclick={() => edit(c)}>Bearbeiten</button>
							<button class="btn small danger" onclick={() => remove(c)}>Löschen</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>
{:else}
	<p class="dim empty">Noch keine eigenen Befehle.</p>
{/if}

<form class="glass pad" onsubmit={save}>
	<h2>{exists ? `!${clean} ändern` : 'Neuer Befehl'}</h2>
	<div class="grid">
		<label class="field">
			<span>Name ohne „!“</span>
			<input id="befehl-name" class="input" bind:value={name} pattern={'!?[A-Za-z0-9_\\-]{1,32}'} maxlength="33"
				autocomplete="off" spellcheck="false" required />
			<span class="hint">Kleinbuchstaben, Ziffern, _ und -</span>
		</label>
		<label class="field wide">
			<span>Antwort</span>
			<textarea class="input" bind:value={response} maxlength="2000" required></textarea>
			<span class="hint">Platzhalter: {'{user}'} erwähnt die Person, {'{server}'} ist der Servername.</span>
		</label>
	</div>
	<button class="btn primary" disabled={!clean || !response.trim()}>{exists ? 'Änderung speichern' : 'Befehl anlegen'}</button>
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
</form>

<style>
	.lead {
		margin: -6px 4px 16px;
	}
	section {
		margin-bottom: 16px;
	}
	.resp {
		max-width: 420px;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		color: var(--dim);
	}
	.actions {
		text-align: right;
		white-space: nowrap;
	}
	.empty {
		margin: 0 4px 16px;
	}
	h2 {
		font-size: 17px;
		margin-bottom: 14px;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 16px 20px;
		margin-bottom: 16px;
	}
	.wide {
		grid-column: 1 / -1;
	}
	.notice {
		margin: 14px 0 0;
	}
</style>
