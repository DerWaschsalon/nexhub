<!-- Geteilter Run: öffentlich, ohne Login. Nicht für Suchmaschinen. -->
<script lang="ts">
	import { page } from '$app/state';
	import RunView from '#lib/components/RunView.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>{data.run.dungeon} · NexHub</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<RunView run={data.run} fightHref={(f) => `/r/${page.params.token}/kampf/${encodeURIComponent(f)}`} />

<p class="dim note">Geteilt über NexHub.</p>

<style>
	.note {
		text-align: center;
		font-size: 13px;
		margin-top: 24px;
	}
</style>
