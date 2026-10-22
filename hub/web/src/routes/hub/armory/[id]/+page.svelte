<!-- Ein Charakter der Armory: Profil wie bei den Mitspielern eines Runs, dazu Verlauf, Aktualisieren
     und Entfernen. Solange der Abruf läuft, alle 5 s neu laden. -->
<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import History from '#modules/armory/components/History.svelte';
	import { classColor, classFromName } from '#modules/logs/classes.ts';
	import CharacterProfile from '#modules/logs/components/CharacterProfile.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const c = $derived(data.character);
	const cls = $derived(c.cls ?? classFromName(c.class_name));
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
		{#if c.data}<a class="btn small" href="/hub/armory/{c.id}/check">{t('armory.check.title')}</a>{/if}
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
	{#if c.days.length}
		<section class="glass pad history">
			<h2>{t('armory.history')}</h2>
			<div class="charts">
				<History title={t('logs.char.combatPower')} days={c.days} key="combat_power" color={classColor(cls)} />
				<History title={t('logs.char.itemLevel')} days={c.days} key="item_level" color={classColor(cls)} />
			</div>
			{#if c.days.length === 1}<p class="dim small">{t('armory.historyStart')}</p>{/if}
		</section>
	{/if}
	<CharacterProfile character={{ ...c, cls }} data={c.data} source={t('armory.source')} />
{:else if c.status !== 'offen'}
	<section class="glass pad">
		<h2>{c.name}</h2>
		<p>
			{c.status === 'nicht_gefunden'
				? t('logs.char.notFound', { why: c.error ?? '' })
				: t('logs.char.error', { why: c.error ?? '' })}
		</p>
	</section>
{/if}

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
	.notice {
		margin-bottom: 14px;
	}
	.history {
		margin-bottom: 16px;
	}
	h2 {
		font-size: 17px;
		margin-bottom: 10px;
	}
	.charts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
		gap: 18px;
	}
	.small {
		font-size: 12px;
		margin-top: 8px;
	}
</style>
