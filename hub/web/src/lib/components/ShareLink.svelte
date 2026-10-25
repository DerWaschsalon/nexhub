<!-- Kasten „Geteilt“: der öffentliche Link zum Kopieren und, wer darf, zum Zurückziehen (Runs, Vergleiche). -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';

	let { url, text, onunshare }: { url: string; text: string; onunshare?: () => void } = $props();
	let copied = $state(false);

	async function copy() {
		await navigator.clipboard.writeText(url);
		copied = true;
		setTimeout(() => (copied = false), 2000);
	}
</script>

<section class="glass pad share">
	<div>
		<strong>{t('share.shared')}</strong>
		<span class="dim">{text}</span>
	</div>
	<div class="link">
		<input class="input" readonly value={url} onfocus={(e) => e.currentTarget.select()} />
		<button class="btn small primary" onclick={copy}>{copied ? t('share.copied') : t('share.copy')}</button>
		{#if onunshare}<button class="btn small" onclick={onunshare}>{t('share.unshare')}</button>{/if}
	</div>
</section>

<style>
	.share {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 16px 20px;
	}
	.share > div:first-child {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 12px;
		align-items: baseline;
	}
	.share .dim {
		font-size: 14px;
	}
	.link {
		display: flex;
		gap: 8px;
		align-items: center;
		flex-wrap: wrap;
	}
	.link .input {
		flex: 1 1 260px;
		width: auto;
		font-size: 14px;
		padding: 7px 10px;
	}
</style>
