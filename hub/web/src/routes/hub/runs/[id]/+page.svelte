<!-- Run gesamt: Schaden über alle Kämpfe. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import RankBars from '#modules/logs/components/RankBars.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<section class="glass pad">
	<h2>{t('logs.run.damageRun')}</h2>
	<RankBars players={data.run.summary.players} />
</section>

<style>
	h2 {
		font-size: 17px;
		margin-bottom: 14px;
	}
</style>
