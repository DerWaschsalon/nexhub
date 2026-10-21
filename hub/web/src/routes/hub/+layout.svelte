<!-- Login-Bereich: Seitenleiste mit Menü und Konto, rechts die jeweilige Seite. -->
<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { post, ROLE_LABEL } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import Brand from '#lib/components/Brand.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import { NAV } from '#lib/nav.ts';
	import type { LayoutProps } from './$types';

	let { data, children }: LayoutProps = $props();

	const items = $derived(NAV.filter((i) => !i.admin || data.me.role === 'admin'));

	// Übersicht nur bei genau /hub markieren, die anderen auch auf Unterseiten
	function active(href: string): boolean {
		const path = page.url.pathname;
		return href === '/hub' ? path === href : path === href || path.startsWith(href + '/');
	}

	async function logout() {
		await post('/api/auth/logout');
		await invalidateAll();
		await goto('/');
	}
</script>

<div class="shell">
	<aside class="glass">
		<Brand href="/hub" />
		<nav>
			{#each items as item (item.href)}
				<a href={item.href} class:active={active(item.href)}>
					<Icon name={item.icon} />
					<span>{item.label}</span>
				</a>
			{/each}
		</nav>
		<div class="me">
			<Avatar name={data.me.name} url={data.me.avatar_url} />
			<div class="who">
				<strong>{data.me.name}</strong>
				<span class="chip accent">{ROLE_LABEL[data.me.role]}</span>
			</div>
			<button class="btn small" onclick={logout} title="Abmelden" aria-label="Abmelden">
				<Icon name="logout" size={16} />
			</button>
		</div>
	</aside>

	<main>
		{@render children()}
	</main>
</div>

<style>
	.shell {
		display: grid;
		grid-template-columns: 250px minmax(0, 1fr);
		gap: 20px;
		max-width: 1280px;
		margin: 0 auto;
		padding: 16px;
		min-height: 100vh;
	}
	aside {
		position: sticky;
		top: 16px;
		height: calc(100vh - 32px);
		display: flex;
		flex-direction: column;
		gap: 24px;
		padding: 20px 14px;
	}
	aside > :global(.brand) {
		padding: 0 8px;
	}
	nav {
		display: flex;
		flex-direction: column;
		gap: 4px;
		flex: 1;
	}
	nav a {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 12px;
		border-radius: 14px;
		color: var(--dim);
		text-decoration: none;
		font-weight: 550;
		border: 1px solid transparent;
		transition:
			background 0.15s,
			color 0.15s;
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
	nav a.active :global(svg) {
		color: var(--accent);
	}
	.me {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 8px 0;
		border-top: 1px solid var(--edge-soft);
	}
	.who {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 2px;
	}
	.who strong {
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 14px;
	}
	main {
		padding: 12px 8px;
		min-width: 0;
	}

	/* Schmal: Leiste wird zur Kopfzeile, Menü scrollt seitlich */
	@media (max-width: 820px) {
		.shell {
			/* minmax(0, …): breite Tabellen scrollen in ihrer Karte statt die Seite zu verbreitern */
			grid-template-columns: minmax(0, 1fr);
			gap: 12px;
		}
		aside {
			position: static;
			height: auto;
			flex-direction: row;
			flex-wrap: wrap;
			align-items: center;
			gap: 10px;
			padding: 10px 12px;
			border-radius: 20px;
		}
		nav {
			order: 3;
			flex-basis: 100%;
			flex-direction: row;
			overflow-x: auto;
			scrollbar-width: none;
		}
		nav a {
			white-space: nowrap;
			padding: 8px 12px;
		}
		.me {
			margin-left: auto;
			border: 0;
			padding: 0;
		}
		.who {
			display: none;
		}
		main {
			padding: 4px 0;
		}
	}
</style>
