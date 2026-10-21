<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<header class="page-head">
	<h1>{t('overview.hello', { name: data.me.name })}</h1>
	<p>{t('overview.text')}</p>
</header>
