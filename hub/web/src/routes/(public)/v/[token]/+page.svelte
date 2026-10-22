<!-- Geteilter Vergleich: öffentlich, ohne Login, gleiche Ansicht wie im Hub. Nicht für Suchmaschinen. -->
<script lang="ts">
	import { i18n, t } from '#lib/i18n.svelte.ts';
	import CompareView from '#modules/armory/components/CompareView.svelte';
	import { armorySide, liveSide } from '#modules/armory/compare.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const c = $derived(data.comparison);
	const left = $derived(armorySide(c.left, i18n.lang));
	const right = $derived(c.right ? liveSide(c.right) : null);
	const title = $derived(t('armory.compare.sharedTitle', { left: c.left.name, right: c.right?.name ?? '?' }));
</script>

<svelte:head>
	<title>{title} · NexHub</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<header class="page-head">
	<h1>{title}</h1>
</header>

{#if c.right_error}<p class="notice error" role="alert">{c.right_error}</p>{/if}
{#if left && right}<CompareView {left} {right} />{/if}

<p class="dim note">{t('shell.shared')}</p>

<style>
	.note {
		text-align: center;
		font-size: 13px;
		margin-top: 24px;
	}
</style>
