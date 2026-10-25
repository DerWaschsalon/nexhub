<!-- Geteilter Build-Check: öffentlich, ohne Login, gleiche Ansicht wie im Hub. Nicht für Suchmaschinen. -->
<script lang="ts">
	import { formatDateTime } from '#lib/format.ts';
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import CheckView from '#modules/armory/components/CheckView.svelte';
	import { localized } from '#modules/logs/api.ts';
	import { classFromName } from '#modules/logs/classes.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const c = $derived(data.check);
</script>

<svelte:head>
	<title>{t('armory.check.title')} · {c.name} · NexHub</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<header class="page-head">
	<h1>{t('armory.check.title')}</h1>
	{#if c.finished_at}<p>{t('armory.check.from', { when: formatDateTime(c.finished_at) })}</p>{/if}
</header>

{#if c.data}
	<CheckView name={c.name} cls={c.cls ?? classFromName(c.class_name)} data={localized(c.data, i18n.lang)} result={c.result} />
{/if}

<p class="dim note">{t('shell.shared')}</p>

<style>
	.note {
		text-align: center;
		font-size: 13px;
		margin-top: 24px;
	}
</style>
