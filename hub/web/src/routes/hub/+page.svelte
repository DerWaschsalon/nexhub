<!-- Übersicht: je Eintrag der Seitenleiste eine Kachel, ein Spiel (AION 2 …) oder die Verwaltung also eine
     Kachel für alle ihre Seiten. Bringt eine Seite eine Vorschau mit (NavItem.overview), steht sie in der Kachel und
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

<svelte:head><title>{t('nav.overview')} · NexHub</title></svelte:head>

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
				<!-- Seiten der Gruppe ohne Vorschau: direkt erreichbar, statt nur über die erste Seite -->
				<nav class="links" aria-label={t(entry.label)}>
					{#each entry.pages.filter((p) => !p.overview) as p (p.href)}
						<a class="chip" href={p.href}>{t(p.label)}</a>
					{/each}
				</nav>
			{:else if entry.overview}
				<div class="body"><entry.overview /></div>
			{/if}
		</section>
	{/each}
</div>

<style>
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 16px;
	}
	.wide {
		grid-column: 1 / -1;
	}
	.links {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		padding: 0 22px 18px;
	}
	.links a {
		text-decoration: none;
	}
	.links a:hover {
		color: var(--text);
		border-color: var(--edge);
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
		background: var(--fill);
	}
	.head :global(svg) {
		flex-shrink: 0;
		color: var(--accent);
	}
	h2 {
		flex: 1;
		min-width: 0;
		font-size: 16px;
		overflow-wrap: anywhere;
	}
	.open {
		font-size: 13px;
		color: var(--dim);
		white-space: nowrap;
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
