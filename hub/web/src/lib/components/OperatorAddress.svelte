<!-- Betreiber aus der Server-Konfiguration (HUB_OPERATOR_* in /srv/nexhub/.env). -->
<script lang="ts">
	import type { Operator } from '#lib/api.ts';
	import { t } from '#lib/i18n.svelte.ts';

	let { operator }: { operator: Operator | null } = $props();
</script>

{#if operator}
	<address>
		<strong>{operator.name}</strong>
		{#each operator.address as line (line)}<br />{line}{/each}
		{#if operator.email}<br /><a href="mailto:{operator.email}">{operator.email}</a>{/if}
	</address>
{:else}
	<p class="notice">{t('legal.missing')}</p>
{/if}

<style>
	address {
		font-style: normal;
		line-height: 1.7;
	}
</style>
