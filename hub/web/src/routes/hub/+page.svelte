<!-- Übersicht: je Bereich aus dem Menü eine Kachel. Bringt ein Modul eine Vorschau mit (NavItem.overview),
     steht sie in der Kachel und die Kachel geht über die ganze Breite. -->
<script lang="ts">
	import Icon from '#lib/components/Icon.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import { navFor } from '#lib/modules.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Die Übersicht selbst nicht noch einmal als Kachel
	const tiles = $derived(navFor(data.me).filter((item) => item.href !== '/hub'));
</script>

<header class="page-head">
	<h1>{t('overview.hello', { name: data.me.name })}</h1>
	<p>{t('overview.text')}</p>
</header>

<div class="tiles">
	{#each tiles as item (item.href)}
		<section class="glass tile" class:wide={item.overview}>
			<a class="head" href={item.href}>
				<Icon name={item.icon} />
				<h2>{t(item.label)}</h2>
				<span class="open">{t('overview.open')} →</span>
			</a>
			{#if item.overview}
				<div class="body"><item.overview /></div>
			{/if}
		</section>
	{/each}
</div>

<style>
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: 16px;
	}
	.wide {
		grid-column: 1 / -1;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 18px 22px;
		border-radius: inherit;
		color: var(--text);
		text-decoration: none;
		transition: background 0.15s;
	}
	.head:hover {
		background: rgba(255, 255, 255, 0.06);
	}
	.head :global(svg) {
		color: var(--accent);
	}
	h2 {
		flex: 1;
		font-size: 18px;
	}
	.open {
		font-size: 13px;
		color: var(--dim);
	}
	.body {
		padding: 0 22px 22px;
	}
</style>
