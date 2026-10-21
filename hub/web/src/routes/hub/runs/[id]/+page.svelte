<!-- Ein Run im Hub: gemeinsame Ansicht plus Download, Teilen und Löschen. -->
<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import RunView from '#lib/components/RunView.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const run = $derived(data.run);
	let copied = $state(false);
	let error = $state('');

	async function call(method: 'POST' | 'DELETE', path: string) {
		error = '';
		try {
			await api<unknown>(path, { method });
			await invalidateAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function remove() {
		if (!confirm('Diesen Run löschen? Die Datei ist danach weg.')) return;
		await call('DELETE', `/api/runs/${run.id}`);
		if (!error) await goto('/hub/runs');
	}

	async function unshare() {
		if (confirm('Link zurückziehen? Wer ihn hat, sieht den Run danach nicht mehr.'))
			await call('DELETE', `/api/runs/${run.id}/share`);
	}

	async function copy() {
		await navigator.clipboard.writeText(run.share_url ?? '');
		copied = true;
		setTimeout(() => (copied = false), 2000);
	}
</script>

<a class="back" href="/hub/runs">← Runs</a>

<RunView {run}>
	{#snippet actions()}
		<a class="btn small" href="/api/runs/{run.id}/nexlog" download>NexLog herunterladen</a>
		{#if run.can_delete}
			{#if !run.share_url}
				<button class="btn small" onclick={() => call('POST', `/api/runs/${run.id}/share`)}>Teilen</button>
			{/if}
			<button class="btn small danger" onclick={remove}>Löschen</button>
		{/if}
	{/snippet}
	{#snippet extra()}
		{#if error}<p class="notice error" role="alert">{error}</p>{/if}
		{#if run.share_url}
			<section class="glass pad share">
				<div>
					<strong>Geteilt</strong>
					<span class="dim">Wer diesen Link hat, sieht den Run ohne Login, mit den Namen aller Mitspieler.</span>
				</div>
				<div class="link">
					<input readonly value={run.share_url} onfocus={(e) => e.currentTarget.select()} />
					<button class="btn small primary" onclick={copy}>{copied ? 'Kopiert' : 'Kopieren'}</button>
					{#if run.can_delete}<button class="btn small" onclick={unshare}>Zurückziehen</button>{/if}
				</div>
			</section>
		{/if}
	{/snippet}
</RunView>

<style>
	.back {
		color: var(--dim);
		text-decoration: none;
		font-size: 14px;
	}
	.notice {
		margin: 0 0 16px;
	}
	.share {
		display: flex;
		flex-direction: column;
		gap: 12px;
		margin-bottom: 16px;
		padding: 18px 20px;
	}
	.share div:first-child {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.link {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}
	input {
		flex: 1 1 280px;
		font: inherit;
		font-size: 14px;
		color: var(--text);
		background: rgba(0, 0, 0, 0.3);
		border: 1px solid var(--edge);
		border-radius: var(--radius-sm);
		padding: 8px 12px;
	}
</style>
