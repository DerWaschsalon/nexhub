<!-- Bot: TheWashBot steuern. Oben die Unterseiten, darunter die jeweilige Seite. -->
<script lang="ts">
	import { page } from '$app/state';
	import { BOT_NAV, botHref } from '#lib/bot.ts';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	const current = $derived(page.url.pathname);
</script>

<header class="page-head head">
	<div>
		<h1>Bot</h1>
		<p>TheWashBot{data.guild ? ` auf ${data.guild.name}` : ''}. Änderungen wirken sofort.</p>
	</div>
	{#if data.status}
		<span class="chip" class:ok={data.status.ready} class:warn={!data.status.ready}>
			{data.status.ready ? 'verbunden' : 'startet'}
		</span>
	{:else}
		<span class="chip danger">nicht erreichbar</span>
	{/if}
</header>

<nav class="tabs" aria-label="Bereiche des Bots">
	{#each BOT_NAV as item (item.slug)}
		{@const href = botHref(item.slug)}
		<a {href} class:active={current === href} aria-current={current === href ? 'page' : undefined}>
			{item.label}
		</a>
	{/each}
</nav>

{#if data.offline}
	<section class="notice error" role="alert">
		<strong>{data.offline}</strong>
		<p>
			Der Bot läuft als eigener Dienst neben dem Hub. Erreicht der Hub ihn nicht, fehlen meist
			<code>BOT_CONTROL_URL</code> oder <code>BOT_CONTROL_KEY</code> in <code>/srv/nexhub/.env</code>,
			oder der Dienst <code>bot</code> ist nicht gestartet.
		</p>
	</section>
{:else}
	{@render children()}
{/if}

<style>
	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
	}
	.tabs {
		display: flex;
		gap: 4px;
		overflow-x: auto;
		scrollbar-width: none;
		margin: 0 -4px 20px;
		padding: 4px;
	}
	.tabs a {
		flex-shrink: 0;
		padding: 7px 14px;
		border-radius: 999px;
		font-size: 14px;
		font-weight: 550;
		color: var(--dim);
		text-decoration: none;
		border: 1px solid transparent;
		white-space: nowrap;
	}
	.tabs a:hover {
		color: var(--text);
		background: rgba(255, 255, 255, 0.06);
	}
	.tabs a.active {
		color: var(--text);
		background: rgba(255, 255, 255, 0.1);
		border-color: var(--edge-soft);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.15);
	}
	.notice p {
		margin: 6px 0 0;
		color: var(--dim);
	}
</style>
