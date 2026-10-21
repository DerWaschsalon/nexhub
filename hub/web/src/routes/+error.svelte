<!-- Fehlerseite für beide Bereiche, z. B. wenn die API nicht antwortet. -->
<script lang="ts">
	import { page } from '$app/state';
	import { t } from '#lib/i18n.svelte.ts';
</script>

<section class="glass pad card">
	<h1>{page.status}</h1>
	<p class="dim">{page.error?.message ?? t('error.fallback')}</p>
	<a class="btn" href="/">{t('error.home')}</a>
</section>

<style>
	.card {
		max-width: 440px;
		margin: 14vh auto 0;
		text-align: center;
	}
	h1 {
		font-size: 44px;
	}
	p {
		margin: 6px 0 22px;
	}
</style>
