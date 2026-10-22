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

	$effect(() => {
		if (c.status !== 'offen') return;
		const timer = setInterval(() => invalidateAll(), 5000);
		return () => clearInterval(timer);
	});

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

<a class="back" href="/hub/runs/{data.run.id}">‹ {t('logs.char.back')}</a>

{#if c.status === 'ok' && c.data}
	<CharacterProfile character={c} data={c.data} />
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
	h2 {
		font-size: 17px;
		margin-bottom: 10px;
	}
	p {
		margin-bottom: 12px;
	}
</style>
