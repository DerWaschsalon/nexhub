<!-- Ein Run im Hub: gemeinsame Ansicht (Modul Logs) plus Herunterladen, Teilen und Löschen. -->
<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import RunView from '#modules/logs/components/RunView.svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
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
		if (!confirm(t('logs.confirmDelete'))) return;
		await call('DELETE', `/api/runs/${run.id}`);
		if (!error) await goto('/hub/runs');
	}

	async function unshare() {
		if (confirm(t('logs.confirmUnshare'))) await call('DELETE', `/api/runs/${run.id}/share`);
	}

	async function copy() {
		await navigator.clipboard.writeText(run.share_url ?? '');
		copied = true;
		setTimeout(() => (copied = false), 2000);
	}
</script>

<svelte:head><title>{run.dungeon} · NexHub</title></svelte:head>

<a class="back" href="/hub/runs">‹ {t('logs.run.allRuns')}</a>

<RunView {run} base="/hub/runs/{run.id}" fight={page.params.fight ?? null}>
	{#snippet actions()}
		<a class="btn small" href="/api/runs/{run.id}/nexlog" download>{t('logs.download')}</a>
		{#if run.can_delete}
			{#if !run.share_url}
				<button class="btn small" onclick={() => call('POST', `/api/runs/${run.id}/share`)}>{t('logs.share')}</button>
			{/if}
			<button class="btn small danger" onclick={remove}>{t('logs.delete')}</button>
		{/if}
	{/snippet}
	{#snippet extra()}
		{#if error}<p class="notice error" role="alert">{error}</p>{/if}
		{#if run.share_url}
			<section class="glass pad share">
				<div>
					<strong>{t('logs.shared')}</strong>
					<span class="dim">{t('logs.sharedText')}</span>
				</div>
				<div class="link">
					<input class="input" readonly value={run.share_url} onfocus={(e) => e.currentTarget.select()} />
					<button class="btn small primary" onclick={copy}>{copied ? t('logs.copied') : t('logs.copy')}</button>
					{#if run.can_delete}<button class="btn small" onclick={unshare}>{t('logs.unshare')}</button>{/if}
				</div>
			</section>
		{/if}
	{/snippet}
	{@render children()}
</RunView>

<style>
	.share {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 16px 20px;
	}
	.share > div:first-child {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 12px;
		align-items: baseline;
	}
	.share .dim {
		font-size: 14px;
	}
	.link {
		display: flex;
		gap: 8px;
		align-items: center;
		flex-wrap: wrap;
	}
	.link .input {
		flex: 1 1 260px;
		width: auto;
		font-size: 14px;
		padding: 7px 10px;
	}
	.notice {
		margin: 0 0 16px;
	}
</style>
