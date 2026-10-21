<!-- Links auf Impressum und Datenschutz; im öffentlichen Kopf/Fuß und in der Seitenleiste des Hubs. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';
</script>

<nav class="legal" aria-label="{t('legal.imprint')} · {t('legal.privacy')}">
	<a href="/impressum">{t('legal.imprint')}</a>
	<a href="/datenschutz">{t('legal.privacy')}</a>
</nav>

<style>
	.legal {
		display: flex;
		gap: 14px;
		font-size: 12px;
	}
	a {
		color: var(--faint);
		text-decoration: none;
	}
	a:hover {
		color: var(--dim);
		text-decoration: underline;
	}
</style>
