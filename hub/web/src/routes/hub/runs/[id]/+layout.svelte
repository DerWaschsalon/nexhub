<!-- Ein Run im Hub: gemeinsame Ansicht (Modul Logs) plus Herunterladen, Teilen und Löschen. -->
<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import ShareLink from '#lib/components/ShareLink.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import RunView from '#modules/logs/components/RunView.svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
	const run = $derived(data.run);
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
</script>

<svelte:head><title>{run.dungeon} · NexHub</title></svelte:head>

<a class="back" href="/hub/runs">‹ {t('logs.run.allRuns')}</a>

<RunView {run} base="/hub/runs/{run.id}" fight={page.params.fight ?? null}>
	{#snippet actions()}
		<a class="btn small" href="/api/runs/{run.id}/nexlog" download>{t('logs.download')}</a>
		{#if run.can_delete}
			{#if !run.share_url}
				<button class="btn small" onclick={() => call('POST', `/api/runs/${run.id}/share`)}>{t('share.button')}</button>
			{/if}
			<button class="btn small danger" onclick={remove}>{t('logs.delete')}</button>
		{/if}
	{/snippet}
	{#snippet extra()}
		{#if error}<p class="notice error" role="alert">{error}</p>{/if}
		{#if run.share_url}
			<ShareLink url={run.share_url} text={t('logs.sharedText')} onunshare={run.can_delete ? unshare : undefined} />
		{/if}
	{/snippet}
	{@render children()}
</RunView>

<style>
	.notice {
		margin: 0 0 16px;
	}
</style>
