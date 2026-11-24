<!-- Rahmen eines Armory-Charakters: Kopf mit Aktualisieren und Entfernen, darunter die Reiter „Ausrüstung“
     und „Upgrades“ als Unterseiten. Solange der Abruf läuft, alle 5 s neu laden. -->
<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { api } from '#lib/api.ts';
	import Tabs from '#lib/components/Tabs.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
	const c = $derived(data.character);
	const base = $derived(`/hub/armory/${c.id}`);
	const tabs = $derived([
		{ id: 'gear', label: t('armory.tab.gear'), href: base },
		{ id: 'upgrades', label: t('armory.tab.upgrades'), href: `${base}/upgrades` }
	]);
	let error = $state('');

	$effect(() => {
		if (c.status !== 'offen') return;
		const timer = setInterval(() => invalidateAll(), 5000);
		return () => clearInterval(timer);
	});

	async function refresh() {
		error = '';
		try {
			await api<unknown>(`/api/armory/${c.id}/refresh`, { method: 'POST' });
			await invalidateAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function remove() {
		if (!confirm(t('armory.confirmRemove', { name: c.name }))) return;
		try {
			await api<void>(`/api/armory/${c.id}`, { method: 'DELETE' });
			await goto('/hub/armory');
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}
</script>

<svelte:head><title>{c.name} · {t('armory.title')} · NexHub</title></svelte:head>

<div class="bar">
	<a class="back" href="/hub/armory">‹ {t('armory.back')}</a>
	<span class="actions">
		<a class="btn small" href="/hub/armory/vergleich?links={c.id}">{t('armory.compare')}</a>
		<button class="btn small" onclick={refresh} disabled={c.status === 'offen'}>{t('armory.refresh')}</button>
		{#if c.can_delete}<button class="btn small danger" onclick={remove}>{t('armory.remove')}</button>{/if}
	</span>
</div>

{#if c.status === 'offen'}
	<p class="notice" role="status">{t('armory.updating')}</p>
{:else if c.status !== 'ok' && c.data}
	<p class="notice error" role="alert">{t('armory.lastFailed', { why: c.error ?? '' })}</p>
{/if}
{#if error}<p class="notice error" role="alert">{error}</p>{/if}

{#if c.data}
	<div class="tabs-row">
		<Tabs {tabs} active={page.url.pathname.endsWith('/upgrades') ? 'upgrades' : 'gear'} label={c.name} />
	</div>
{/if}

{@render children()}

<style>
	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		margin-bottom: 14px;
	}
	.bar .back {
		margin-bottom: 0;
	}
	.actions {
		display: flex;
		gap: 8px;
	}
	.notice,
	.tabs-row {
		margin-bottom: 14px;
	}
</style>
