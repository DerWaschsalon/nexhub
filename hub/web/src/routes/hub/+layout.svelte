<!-- Login-Bereich: Seitenleiste mit Menü (Kern + Module, lib/modules.ts), Sprache und Konto; rechts die
     jeweilige Seite mit Breadcrumb. Spiele und die Verwaltung sind aufklappbare Gruppen; bei schmalem
     Fenster klappt die ganze Leiste hinter einem Menüknopf zusammen. -->
<script lang="ts">
	import { afterNavigate, goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import { post } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import Brand from '#lib/components/Brand.svelte';
	import Breadcrumb, { type Crumb } from '#lib/components/Breadcrumb.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import LangSwitch from '#lib/components/LangSwitch.svelte';
	import LegalLinks from '#lib/components/LegalLinks.svelte';
	import { t } from '#lib/i18n.svelte.ts';
	import { menu, navFor, type MenuEntry } from '#lib/modules.ts';
	import type { LayoutProps } from './$types';

	const OPEN_KEY = 'nexhub.nav.open';

	let { data, children }: LayoutProps = $props();

	const items = $derived(navFor(data.me));
	const entries = $derived(menu(items));
	// Gruppe und Seite, zu der die aktuelle Adresse gehört
	const group = $derived(entries.find((e) => e.pages.some((p) => active(p.href))));
	const current = $derived(items.find((i) => active(i.href)));

	// Übersicht nur bei genau /hub markieren, die anderen auch auf Unterseiten
	function active(href: string): boolean {
		const path = page.url.pathname;
		return href === '/hub' ? path === href : path === href || path.startsWith(href + '/');
	}

	// Aufgeklappte Gruppen merkt sich der Browser; die Gruppe der aktuellen Seite ist immer offen
	let opened = $state<string[]>(JSON.parse(localStorage.getItem(OPEN_KEY) ?? '[]'));
	const isOpen = (e: MenuEntry) => e === group || opened.includes(e.label);
	function toggle(e: MenuEntry) {
		opened = opened.includes(e.label) ? opened.filter((label) => label !== e.label) : [...opened, e.label];
		localStorage.setItem(OPEN_KEY, JSON.stringify(opened));
	}

	// schmales Fenster: Menü hinter dem Knopf, nach jedem Seitenwechsel wieder zu
	let menuOpen = $state(false);
	afterNavigate(() => {
		menuOpen = false;
	});

	const trail = $derived.by((): Crumb[] => {
		if (!current) return [];
		const detail = current.detail?.(page.data, page.url.pathname);
		return [
			...(group ? [{ label: t(group.label) }] : []),
			{ label: t(current.label), href: current.href },
			...(detail ? [{ label: detail }] : [])
		];
	});

	async function logout() {
		await post('/api/auth/logout');
		await invalidateAll();
		await goto('/');
	}
</script>

<div class="shell">
	<aside class="glass" class:open={menuOpen}>
		<div class="top">
			<Brand href="/hub" />
			<button class="btn small burger" onclick={() => (menuOpen = !menuOpen)} aria-expanded={menuOpen}
				aria-controls="hub-menu" aria-label={t('shell.menu')}>
				<Icon name={menuOpen ? 'close' : 'menu'} />
			</button>
		</div>
		<div class="drawer" id="hub-menu">
			<nav class="menu" aria-label={t('shell.menu')}>
				{#each entries as e (e.label)}
					{#if e.pages.length}
						<button class="entry" class:within={e === group} onclick={() => toggle(e)} aria-expanded={isOpen(e)}>
							<Icon name={e.icon} />
							<span>{t(e.label)}</span>
							<span class="chevron"><Icon name="chevron" size={16} /></span>
						</button>
						{#if isOpen(e)}
							<div class="sub">
								{#each e.pages as p (p.href)}
									<a href={p.href} class:active={active(p.href)} aria-current={active(p.href) ? 'page' : undefined}>
										{t(p.label)}
									</a>
								{/each}
							</div>
						{/if}
					{:else}
						<a class="entry" href={e.href} class:active={active(e.href)} aria-current={active(e.href) ? 'page' : undefined}>
							<Icon name={e.icon} />
							<span>{t(e.label)}</span>
						</a>
					{/if}
				{/each}
			</nav>
			<LangSwitch />
			<div class="me">
				<Avatar name={data.me.name} url={data.me.avatar_url} />
				<div class="who">
					<strong>{data.me.name}</strong>
					<span class="chip accent">{t(`role.${data.me.role}`)}</span>
				</div>
				<button class="btn small" onclick={logout} title={t('shell.logout')} aria-label={t('shell.logout')}>
					<Icon name="logout" size={16} />
				</button>
			</div>
			<LegalLinks />
		</div>
	</aside>

	<main>
		{#if trail.length > 1}<Breadcrumb {trail} />{/if}
		{@render children()}
	</main>
</div>

<style>
	.shell {
		display: grid;
		grid-template-columns: 250px minmax(0, 1fr);
		gap: 20px;
		max-width: var(--page-width);
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
	.top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0 8px;
	}
	.burger {
		display: none;
	}
	.drawer {
		display: flex;
		flex-direction: column;
		gap: 24px;
		flex: 1;
		min-height: 0;
	}
	.menu {
		display: flex;
		flex-direction: column;
		gap: 4px;
		flex: 1;
		min-height: 0;
		overflow-y: auto;
	}
	.entry {
		display: flex;
		align-items: center;
		gap: 12px;
		width: 100%;
		padding: 10px 12px;
		border-radius: var(--radius);
		color: var(--dim);
		background: none;
		font: inherit;
		font-weight: 550;
		text-align: left;
		text-decoration: none;
		border: 1px solid transparent;
		cursor: pointer;
		transition:
			background 0.15s,
			color 0.15s;
	}
	.entry:hover,
	.sub a:hover {
		color: var(--text);
		background: var(--fill);
	}
	.entry.active,
	.sub a.active {
		color: var(--text);
		background: var(--fill-strong);
		border-color: var(--edge-soft);
	}
	.entry.within,
	.entry.active :global(svg),
	.entry.within :global(svg:first-child) {
		color: var(--text);
	}
	.entry.active :global(svg),
	.entry.within > :global(svg) {
		color: var(--accent);
	}
	.chevron {
		display: grid;
		margin-left: auto;
		transition: transform 0.15s;
	}
	.entry[aria-expanded='true'] .chevron {
		transform: rotate(180deg);
	}
	/* Seiten einer Gruppe: eingerückt an einer feinen Linie */
	.sub {
		display: flex;
		flex-direction: column;
		gap: 2px;
		margin: 0 0 6px 20px;
		padding-left: 10px;
		border-left: 1px solid var(--edge-soft);
	}
	.sub a {
		padding: 7px 12px;
		border-radius: var(--radius);
		border: 1px solid transparent;
		color: var(--dim);
		font-size: 14px;
		text-decoration: none;
	}
	.drawer > :global(.lang) {
		align-self: flex-start;
		margin-left: 8px;
	}
	.drawer > :global(.legal) {
		margin: -14px 8px 0;
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

	/* Schmal: Die Leiste wird zur Kopfzeile mit Menüknopf, das Menü klappt darunter auf */
	@media (max-width: 820px) {
		.shell {
			/* minmax(0, …): breite Tabellen scrollen in ihrer Karte statt die Seite zu verbreitern */
			grid-template-columns: minmax(0, 1fr);
			gap: 12px;
		}
		aside {
			position: static;
			height: auto;
			gap: 0;
			padding: 10px 12px;
		}
		.top {
			padding: 0;
		}
		.burger {
			display: inline-flex;
		}
		.drawer {
			display: none;
			gap: 16px;
			padding-top: 12px;
		}
		aside.open .drawer {
			display: flex;
		}
		.drawer > :global(.legal) {
			margin: 0 8px;
		}
		main {
			padding: 4px 0;
		}
	}
</style>
