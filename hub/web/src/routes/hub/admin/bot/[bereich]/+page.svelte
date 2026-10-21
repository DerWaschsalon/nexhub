<script lang="ts">
	import BotPage from '#modules/bot/BotPage.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head><title>{data.page.title} · Bot · NexHub</title></svelte:head>

{#key data.page.id}
	<BotPage page={data.page} guild={data.guild!} />
{/key}
