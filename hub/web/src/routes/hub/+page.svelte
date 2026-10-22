<!-- Übersicht: je Eintrag der Seitenleiste eine Kachel, ein Spiel (AION 2 …) also eine Kachel für alle
     seine Seiten. Bringt eine Seite eine Vorschau mit (NavItem.overview), steht sie in der Kachel und
     die Kachel geht über die ganze Breite; bei einem Spiel steht jede Vorschau unter dem Namen ihrer Seite. -->
<script lang="ts">
	import Icon from '#lib/components/Icon.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import { menu, navFor } from '#lib/modules.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Die Übersicht selbst nicht noch einmal als Kachel
	const tiles = $derived(menu(navFor(data.me).filter((item) => item.href !== '/hub')));
</script>

<header class="page-head">
	<h1>{t('overview.hello', { name: data.me.name })}</h1>
	<p>{t('overview.text')}</p>
</header>

<div class="tiles">
	{#each tiles as entry (entry.label)}
		<section class="glass tile" class:wide={entry.overview || entry.pages.some((p) => p.overview)}>
			<a class="head" href={entry.href}>
				<Icon name={entry.icon} />
				<h2>{t(entry.label)}</h2>
				<span class="open">{t('overview.open')} →</span>
			</a>
			{#if entry.pages.length}
				{#each entry.pages.filter((p) => p.overview) as p (p.href)}
					<div class="body">
						<a class="sub" href={p.href}>{t(p.label)} →</a>
						<p.overview />
					</div>
				{/each}
			{:else if entry.overview}
				<div class="body"><entry.overview /></div>
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
	.sub {
		display: inline-block;
		margin-bottom: 10px;
		font-size: 14px;
		font-weight: 600;
		color: var(--dim);
		text-decoration: none;
	}
	.sub:hover {
		color: var(--text);
	}
</style>
