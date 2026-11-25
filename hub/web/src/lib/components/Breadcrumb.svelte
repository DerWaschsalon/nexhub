<!-- Wo bin ich: Gruppe › Seite › Unterseite. Der letzte Eintrag ist die aktuelle Seite und kein Link. -->
<script lang="ts">
	import { t } from '#lib/i18n.svelte.ts';

	export type Crumb = { label: string; href?: string };

	let { trail }: { trail: Crumb[] } = $props();
</script>

<nav class="crumbs" aria-label={t('shell.breadcrumb')}>
	<ol>
		{#each trail as crumb, i (i)}
			<li>
				{#if crumb.href && i < trail.length - 1}
					<a href={crumb.href}>{crumb.label}</a>
				{:else}
					<span aria-current={i === trail.length - 1 ? 'page' : undefined}>{crumb.label}</span>
				{/if}
			</li>
		{/each}
	</ol>
</nav>

<style>
	ol {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 8px;
		margin: 0 0 14px;
		padding: 0;
		list-style: none;
		font-size: 13px;
		color: var(--faint);
	}
	li + li::before {
		content: '›';
		margin-right: 8px;
		color: var(--faint);
	}
	a {
		color: var(--dim);
		text-decoration: none;
	}
	a:hover {
		color: var(--text);
		text-decoration: underline;
	}
	[aria-current='page'] {
		color: var(--text);
		font-weight: 600;
	}
</style>
