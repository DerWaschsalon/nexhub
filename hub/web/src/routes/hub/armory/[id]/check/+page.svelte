<!-- Build-Check: starten, Fortschritt (alle 3 s neu laden), Ergebnis und Teilen. Ein Fehler zeigt das
     vorige Ergebnis darunter weiter an. -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import ShareLink from '#lib/components/ShareLink.svelte';
	import { formatDateTime } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import CheckView from '#modules/armory/components/CheckView.svelte';
	import { localized } from '#modules/logs/api.ts';
	import { classFromName } from '#modules/logs/classes.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const c = $derived(data.character);
	const check = $derived(data.check);
	let error = $state('');

	$effect(() => {
		if (check?.status !== 'läuft') return;
		const timer = setInterval(() => invalidateAll(), 3000);
		return () => clearInterval(timer);
	});

	async function call(method: 'POST' | 'DELETE', path: string) {
		error = '';
		try {
			await api<unknown>(path, { method });
			await invalidateAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function unshare() {
		if (confirm(t('armory.check.confirmUnshare'))) await call('DELETE', `/api/armory/${c.id}/check/share`);
	}
</script>

<svelte:head><title>{t('armory.check.title')} · {c.name} · NexHub</title></svelte:head>

<div class="bar">
	<a class="back" href="/hub/armory/{c.id}">‹ {c.name}</a>
	<span class="actions">
		{#if check?.result && c.can_delete && !check.share_url}
			<button class="btn small" onclick={() => call('POST', `/api/armory/${c.id}/check/share`)}>{t('share.button')}</button>
		{/if}
		{#if check?.status !== 'läuft'}
			<button class="btn small primary" onclick={() => call('POST', `/api/armory/${c.id}/check`)}>
				{check ? t('armory.check.again') : t('armory.check.start')}
			</button>
		{/if}
	</span>
</div>

<header class="page-head">
	<h1>{t('armory.check.title')}</h1>
	<p>{t('armory.check.intro')}</p>
</header>

{#if error}<p class="notice error" role="alert">{error}</p>{/if}
{#if !check}
	<p class="dim">{t('armory.check.none')}</p>
{:else if check.status === 'läuft'}
	<p class="notice" role="status">{t('armory.check.running', { n: check.progress })}</p>
{:else if check.status === 'fehler'}
	<p class="notice error" role="alert">{t('armory.check.failed', { why: check.error ?? '' })}</p>
{/if}

{#if check?.share_url}
	<ShareLink url={check.share_url} text={t('armory.check.sharedText')} onunshare={c.can_delete ? unshare : undefined} />
{/if}

{#if check?.result && c.data}
	{#if check.finished_at}<p class="dim small">{t('armory.check.from', { when: formatDateTime(check.finished_at) })}</p>{/if}
	<CheckView name={c.name} cls={c.cls ?? classFromName(c.class_name)} data={localized(c.data, i18n.lang)} result={check.result} />
{/if}

<style>
	.small {
		font-size: 13px;
		margin-bottom: 12px;
	}
</style>
