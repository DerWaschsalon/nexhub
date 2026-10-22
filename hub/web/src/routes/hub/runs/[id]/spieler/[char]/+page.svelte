<!-- Charakterprofil eines Mitspielers; solange der Abruf läuft, alle 5 s neu laden. -->
<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { api } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';
	import CharacterProfile from '#modules/logs/components/CharacterProfile.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const c = $derived(data.character);
	let error = $state('');

	// Neu laden, solange der Abruf oder das Nachladen der Item-Werte läuft
	const busy = $derived(c.status === 'offen' || (!!c.data && 'v' in c.data && c.data.details?.state === 'laden'));
	$effect(() => {
		if (!busy) return;
		const timer = setInterval(() => invalidateAll(), 5000);
		return () => clearInterval(timer);
	});

	async function loadDetails() {
		await api<unknown>(`/api/runs/${data.run.id}/characters/${c.id}/details`, { method: 'POST' });
		await invalidateAll();
	}

	async function retry() {
		error = '';
		try {
			await api<unknown>(`/api/runs/${data.run.id}/characters/refresh`, { method: 'POST' });
			await invalidateAll();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}
</script>

<svelte:head><title>{c.name} · {data.run.dungeon} · NexHub</title></svelte:head>

<div class="bar">
	<a class="back" href="/hub/runs/{data.run.id}">‹ {t('logs.char.back')}</a>
	{#if c.armory_id}<a class="btn small" href="/hub/armory/{c.armory_id}">{t('armory.inArmory')} ›</a>{/if}
</div>

{#if c.status === 'ok' && c.data}
	<CharacterProfile character={c} data={c.data} {loadDetails} />
{:else}
	<section class="glass pad">
		<h2>{c.name}</h2>
		{#if c.status === 'offen'}
			<p>{t('logs.char.loading')}</p>
		{:else if c.status === 'name_maskiert'}
			<p>{t('logs.char.masked')}</p>
		{:else}
			<p>
				{c.status === 'nicht_gefunden'
					? t('logs.char.notFound', { why: c.error ?? '' })
					: t('logs.char.error', { why: c.error ?? '' })}
			</p>
			{#if data.run.can_delete}
				<button class="btn small" onclick={retry}>{t('logs.char.retry')}</button>
			{/if}
		{/if}
		{#if error}<p class="notice error" role="alert">{error}</p>{/if}
	</section>
{/if}

<style>
	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		margin-bottom: 10px;
	}
	.bar .back {
		margin-bottom: 0;
	}
	h2 {
		font-size: 17px;
		margin-bottom: 10px;
	}
	p {
		margin-bottom: 12px;
	}
</style>
