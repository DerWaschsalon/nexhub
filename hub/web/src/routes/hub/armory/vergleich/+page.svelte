<!-- Zwei Charaktere vergleichen: links aus der Armory, rechts über die Suche (live, nicht gespeichert). -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import type { ArmoryHit } from '#modules/armory/api.ts';
	import CharacterSearch from '#modules/armory/components/CharacterSearch.svelte';
	import CompareView from '#modules/armory/components/CompareView.svelte';
	import { localized } from '#modules/logs/api.ts';
	import { classFromName } from '#modules/logs/classes.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const left = $derived.by(() => {
		const c = data.left;
		return c?.data ? { name: c.name, cls: c.cls ?? classFromName(c.class_name), data: localized(c.data, i18n.lang) } : null;
	});
	const right = $derived(
		data.right ? { name: data.right.name, cls: classFromName(data.right.data.profile.class), data: data.right.data } : null
	);

	/** Auswahl in die Adresse schreiben; die Seite lädt dann neu (+page.ts) */
	function choose(key: 'links' | 'rechts', value: string) {
		const url = new URL(page.url.href);
		url.searchParams.set(key, value);
		goto(url, { replace: true, reset: false });
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
	<CompareView {left} {right} />
	<p class="dim small">{t('armory.compare.share')}</p>
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
	.small {
		font-size: 12px;
	}
</style>
