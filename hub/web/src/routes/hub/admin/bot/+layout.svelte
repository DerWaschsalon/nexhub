<!-- Bot: TheWashBot steuern. Links das Menü (kommt vom Bot, nach Gruppen), rechts die Seite.
     Auf schmalen Bildschirmen wird das Menü zu einer aufklappbaren Liste über der Seite. -->
<script lang="ts">
	import { page } from '$app/state';
	import { botHref, navGroups } from '#modules/bot/bot.ts';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	const current = $derived(page.url.pathname);
	const groups = $derived(navGroups(data.nav));
	const active = $derived(data.nav.find((it) => botHref(it.id) === current));
	let menu = $state<HTMLDetailsElement>();

	// Nach dem Wechsel der Seite das Klappmenü wieder schließen
	$effect(() => {
		void current;
		if (menu) menu.open = false;
	});
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
	<div class="split">
		<details class="menu" bind:this={menu}>
			<summary>{active?.title ?? 'Bereich wählen'}</summary>
			{@render nav()}
		</details>
		<div class="side">{@render nav()}</div>
		<div class="content">{@render children()}</div>
	</div>
{/if}

{#snippet nav()}
	<nav aria-label="Bereiche des Bots">
		{#each groups as g (g.name)}
			<div class="group">
				<span class="group-name">{g.name}</span>
				{#each g.items as item (item.id)}
					{@const href = botHref(item.id)}
					<a {href} class:active={current === href} aria-current={current === href ? 'page' : undefined}>
						{item.title}
					</a>
				{/each}
			</div>
		{/each}
	</nav>
{/snippet}

<style>
	.head {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 16px;
	}
	.notice p {
		margin: 6px 0 0;
		color: var(--dim);
	}
	.split {
		display: grid;
		grid-template-columns: 188px minmax(0, 1fr);
		gap: 24px;
		align-items: start;
	}
	.side {
		position: sticky;
		top: 24px;
	}
	.content {
		min-width: 0;
	}
	nav {
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.group {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.group-name {
		padding: 0 12px 4px;
		font-size: 13px;
		font-weight: 600;
		color: var(--faint);
	}
	nav a {
		padding: 6px 12px;
		border-radius: 10px;
		border: 1px solid transparent;
		color: var(--dim);
		font-size: 14px;
		font-weight: 550;
		text-decoration: none;
	}
	nav a:hover {
		color: var(--text);
		background: rgba(255, 255, 255, 0.06);
	}
	nav a.active {
		color: var(--text);
		background: rgba(255, 255, 255, 0.1);
		border-color: var(--edge-soft);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.15);
	}
	nav a:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}
	.menu {
		display: none;
	}
	@media (max-width: 1100px) {
		.split {
			grid-template-columns: minmax(0, 1fr);
			gap: 16px;
		}
		.side {
			display: none;
		}
		.menu {
			display: block;
			border-radius: var(--radius-sm);
			border: 1px solid var(--edge-soft);
			background: rgba(255, 255, 255, 0.05);
		}
		.menu summary {
			padding: 10px 14px;
			font-weight: 600;
			cursor: pointer;
		}
		.menu nav {
			display: grid;
			grid-template-columns: repeat(2, minmax(0, 1fr));
			align-items: start;
			padding: 4px 6px 14px;
		}
	}
</style>
