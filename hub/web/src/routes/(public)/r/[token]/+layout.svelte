<!-- Geteilter Run: öffentlich, ohne Login, gleiche Ansicht wie im Hub. Nicht für Suchmaschinen. -->
<script lang="ts">
	import { page } from '$app/state';
	import { t } from '#lib/i18n.svelte.ts';
	import RunView from '#modules/logs/components/RunView.svelte';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();
</script>

<svelte:head>
	<title>{data.run.dungeon} · NexHub</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<RunView run={data.run} base="/r/{page.params.token}" fight={page.params.fight ?? null}>
	{@render children()}
</RunView>

<p class="dim note">{t('shell.shared')}</p>

<style>
	.note {
		text-align: center;
		font-size: 13px;
		margin-top: 24px;
	}
</style>
