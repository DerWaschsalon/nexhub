<!-- Kampf aus einem geteilten Run: öffentlich, nicht für Suchmaschinen. -->
<script lang="ts">
	import { page } from '$app/state';
	import FightView from '#lib/components/FightView.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>{data.fight.name} · NexHub</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<FightView fight={data.fight} back="/r/{page.params.token}" />
