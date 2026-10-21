<script lang="ts">
	import BotSection from '#modules/bot/BotSection.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<p class="dim lead">{data.section.description}</p>
{#key data.section.id}
	<BotSection section={data.section} guild={data.guild!} />
{/key}

<style>
	.lead {
		margin: -6px 4px 16px;
	}
</style>
