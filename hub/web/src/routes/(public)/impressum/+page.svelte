<!-- Impressum: Angaben kommen vom Server (HUB_OPERATOR_*), nicht aus dem Repo. -->
<script lang="ts">
	import OperatorAddress from '#lib/components/OperatorAddress.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head><title>{t('legal.imprintTitle')} · NexHub</title></svelte:head>

<article class="glass pad legal-page">
	<h1>{t('legal.imprintTitle')}</h1>
	<h2>{t('legal.imprintBasis')}</h2>
	<OperatorAddress operator={data.info.operator} />
</article>

<style>
	.legal-page {
		max-width: 760px;
		margin: 0 auto;
	}
	h1 {
		font-size: 28px;
		margin-bottom: 18px;
	}
	h2 {
		font-size: 16px;
		margin-bottom: 10px;
		color: var(--dim);
	}
</style>
