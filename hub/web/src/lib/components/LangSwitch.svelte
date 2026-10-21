<!-- Sprachwahl EN/DE; gilt für den ganzen Hub und alle Module (lib/i18n.svelte.ts). -->
<script lang="ts">
	import { i18n, LANGS, t } from '#lib/i18n.svelte.ts';
</script>

<div class="lang" role="group" aria-label={t('lang.label')}>
	{#each LANGS as lang (lang)}
		<button type="button" aria-pressed={i18n.lang === lang} class:active={i18n.lang === lang} onclick={() => i18n.set(lang)}>
			{lang.toUpperCase()}
		</button>
	{/each}
</div>

<style>
	.lang {
		display: inline-flex;
		flex-shrink: 0;
		padding: 3px;
		border-radius: 999px;
		border: 1px solid var(--edge-soft);
		background: rgba(255, 255, 255, 0.04);
	}
	button {
		border: 0;
		background: none;
		color: var(--dim);
		font: inherit;
		font-size: 12px;
		font-weight: 650;
		letter-spacing: 0.04em;
		padding: 4px 10px;
		border-radius: 999px;
		cursor: pointer;
	}
	button.active {
		color: var(--text);
		background: rgba(255, 255, 255, 0.12);
	}
</style>
