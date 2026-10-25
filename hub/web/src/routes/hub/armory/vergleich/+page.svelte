<!-- Zwei Charaktere vergleichen: links aus der Armory, rechts über die Suche (live, nicht gespeichert).
     Teilen gibt einen öffentlichen Link (/v/<token>), der beim Öffnen die Werte neu holt. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, send } from '#lib/api.ts';
	import ShareLink from '#lib/components/ShareLink.svelte';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import type { ArmoryHit } from '#modules/armory/api.ts';
	import CharacterSearch from '#modules/armory/components/CharacterSearch.svelte';
	import CompareView from '#modules/armory/components/CompareView.svelte';
	import { armorySide, liveSide } from '#modules/armory/compare.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const left = $derived(data.left ? armorySide(data.left, i18n.lang) : null);
	const right = $derived(data.right ? liveSide(data.right) : null);

	let shareUrl = $state<string | null>(null);
	let error = $state('');

	/** Auswahl in die Adresse schreiben; die Seite lädt dann neu (+page.ts) */
	function choose(key: 'links' | 'rechts', value: string) {
		shareUrl = null; // der Link gehört zum vorigen Vergleich
		const url = new URL(page.url.href);
		url.searchParams.set(key, value);
		goto(url, { replace: true, reset: false });
	}

	async function share() {
		error = '';
		try {
			const body = { left: data.left?.id, server_id: data.right?.server_id, name: data.right?.name };
			shareUrl = (await send<{ share_url: string }>('/api/armory/compare/share', 'POST', body)).share_url;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function unshare() {
		if (!shareUrl || !confirm(t('armory.compare.confirmUnshare'))) return;
		error = '';
		try {
			await api<unknown>(`/api/armory/compare/share/${shareUrl.split('/').pop()}`, { method: 'DELETE' });
			shareUrl = null;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}
</script>

<svelte:head><title>{t('armory.compare.title')} · NexHub</title></svelte:head>

<a class="back" href="/hub/armory">‹ {t('armory.back')}</a>

<header class="page-head">
	<h1>{t('armory.compare.title')}</h1>
	<p>{t('armory.compare.intro')}</p>
</header>

<section class="glass pad pick">
	<label class="field">
		{t('armory.compare.left')}
		<select class="input" value={data.left?.id} onchange={(e) => choose('links', e.currentTarget.value)}>
			{#each data.characters as c (c.id)}<option value={c.id}>{c.name} · {c.server}</option>{/each}
		</select>
	</label>
	<div>
		<p class="label">{t('armory.compare.right')}</p>
		<CharacterSearch>
			{#snippet action(h: ArmoryHit)}
				<button class="btn small" onclick={() => choose('rechts', `${h.server_id}/${h.name}`)}>{t('armory.compare.pick')}</button>
			{/snippet}
		</CharacterSearch>
	</div>
	{#if data.rightError}<p class="notice error" role="alert">{data.rightError}</p>{/if}
</section>

{#if left && right}
	{#if error}<p class="notice error" role="alert">{error}</p>{/if}
	{#if shareUrl}
		<ShareLink url={shareUrl} text={t('armory.compare.sharedText')} onunshare={unshare} />
	{:else}
		<p class="share"><button class="btn small" onclick={share}>{t('share.button')}</button></p>
	{/if}
	<CompareView {left} {right} />
{:else if !data.characters.length}
	<p class="dim">{t('armory.none')}</p>
{:else}
	<p class="dim">{t('armory.compare.pickRight')}</p>
{/if}

<style>
	.pick {
		display: flex;
		flex-direction: column;
		gap: 16px;
		margin-bottom: 16px;
	}
	.label {
		font-size: 13px;
		color: var(--dim);
		margin-bottom: 6px;
	}
	.share {
		margin-bottom: 16px;
	}
</style>
