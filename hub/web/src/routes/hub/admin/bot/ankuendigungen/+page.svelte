<!-- Ankündigungen: Texte, die der Bot in festen Abständen in einen Kanal postet. -->
<script lang="ts">
	import { BOT_API, send, type Announcement } from '#lib/api.ts';
	import { formatMs } from '#lib/format.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// svelte-ignore state_referenced_locally
	let items = $state<Announcement[]>(data.announcements);
	let channel = $state('');
	let text = $state('');
	let interval = $state(60);
	let error = $state('');

	const channels = $derived(data.guild!.channels.filter((c) => c.kind === 'text'));

	function every(min: number): string {
		if (min % 1440 === 0) return min === 1440 ? 'täglich' : `alle ${min / 1440} Tage`;
		if (min % 60 === 0) return min === 60 ? 'stündlich' : `alle ${min / 60} Stunden`;
		return `alle ${min} Minuten`;
	}

	async function add(e: SubmitEvent) {
		e.preventDefault();
		error = '';
		try {
			items = await send<Announcement[]>(`${BOT_API}/announcements`, 'POST', {
				channel_id: channel,
				text,
				interval_minutes: interval
			});
			text = '';
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	async function remove(a: Announcement) {
		if (!confirm('Ankündigung löschen?')) return;
		error = '';
		try {
			await send<void>(`${BOT_API}/announcements/${a.id}`, 'DELETE');
			items = items.filter((x) => x.id !== a.id);
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}
</script>

<p class="dim lead">Texte, die der Bot regelmäßig in einen Kanal postet.</p>

{#if items.length}
	<section class="list">
		{#each items as a (a.id)}
			<article class="glass pad item">
				<header>
					<strong>{a.channel ? `#${a.channel}` : 'Kanal gelöscht'}</strong>
					<span class="chip accent">{every(a.interval_minutes)}</span>
					<span class="dim when">nächstes Mal {formatMs(a.next_run * 1000)}</span>
					<button class="btn small danger" onclick={() => remove(a)}>Löschen</button>
				</header>
				<p>{a.text}</p>
			</article>
		{/each}
	</section>
{:else}
	<p class="dim empty">Noch keine Ankündigung. Lege unten die erste an.</p>
{/if}

<form class="glass pad" onsubmit={add}>
	<h2>Neue Ankündigung</h2>
	<div class="grid">
		<label class="field">
			<span>Kanal</span>
			<select class="input" bind:value={channel} required>
				<option value="" disabled>Kanal wählen</option>
				{#each channels as c (c.id)}<option value={c.id}>#{c.name}</option>{/each}
			</select>
		</label>
		<label class="field">
			<span>Abstand in Minuten</span>
			<input class="input" type="number" min="5" step="1" bind:value={interval} required />
			<span class="hint">Mindestens 5. Täglich sind 1440.</span>
		</label>
		<label class="field wide">
			<span>Text</span>
			<textarea class="input" bind:value={text} maxlength="2000" required></textarea>
		</label>
	</div>
	<button class="btn primary" disabled={!channel || !text.trim() || interval < 5}>Ankündigung anlegen</button>
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
</form>

<style>
	.lead {
		margin: -6px 4px 16px;
	}
	.list {
		display: flex;
		flex-direction: column;
		gap: 12px;
		margin-bottom: 16px;
	}
	.item header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px;
	}
	.when {
		font-size: 13px;
		margin-right: auto;
	}
	.item p {
		margin: 10px 0 0;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
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
