<!-- Reiter für den ganzen Hub. Mit `href` sind es Unterseiten: Links in einer Navigation, jeder Reiter hat
     eine eigene Adresse. Ohne `href` sind es Ansichten einer Seite: eine Reiterleiste, die Pfeiltasten gehen
     zum nächsten Reiter. Aussehen aus app.css (.tabs), `underline` ist die schmale Form für Karten. -->
<script lang="ts" module>
	export type Tab = { id: string; label: string; href?: string; disabled?: boolean };
</script>

<script lang="ts" generics="T extends Tab">
	import type { Snippet } from 'svelte';

	let {
		tabs,
		active,
		onselect,
		label,
		underline = false,
		tab: content,
		children
	}: {
		tabs: T[];
		active: string | null;
		/** Ansichten: gewählter Reiter (bei Unterseiten wechselt der Link die Seite) */
		onselect?: (id: string) => void;
		/** Name der Leiste für Screenreader */
		label?: string;
		underline?: boolean;
		/** eigener Inhalt je Reiter (Symbol, Zähler); ohne: die Beschriftung */
		tab?: Snippet<[T]>;
		/** Zusatz am Ende der Leiste, z. B. ein Etikett */
		children?: Snippet;
	} = $props();

	const buttons: HTMLButtonElement[] = $state([]);
	const STEP: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1 };

	/** Pfeiltasten: zum nächsten wählbaren Reiter in dieser Richtung, am Ende von vorn. */
	function key(e: KeyboardEvent, from: number) {
		const step = STEP[e.key];
		if (!step) return;
		e.preventDefault();
		for (let i = 1; i <= tabs.length; i++) {
			const next = (from + step * i + tabs.length * i) % tabs.length;
			if (tabs[next].disabled) continue;
			onselect?.(tabs[next].id);
			buttons[next]?.focus();
			return;
		}
	}
</script>

{#snippet inner(item: T)}
	{#if content}{@render content(item)}{:else}{item.label}{/if}
{/snippet}

{#if tabs[0]?.href}
	<nav class="tabs" class:underline aria-label={label}>
		{#each tabs as item (item.id)}
			<a href={item.href} class:active={item.id === active} aria-current={item.id === active ? 'page' : undefined}>
				{@render inner(item)}
			</a>
		{/each}
		{@render children?.()}
	</nav>
{:else}
	<div class="tabs" class:underline role="tablist" aria-label={label}>
		{#each tabs as item, i (item.id)}
			<button type="button" role="tab" bind:this={buttons[i]} class:active={item.id === active}
				aria-selected={item.id === active} tabindex={item.id === active ? 0 : -1} disabled={item.disabled}
				onclick={() => onselect?.(item.id)} onkeydown={(e) => key(e, i)}>
				{@render inner(item)}
			</button>
		{/each}
		{@render children?.()}
	</div>
{/if}

<style>
	button:disabled {
		opacity: 0.35;
		cursor: default;
	}
	/* schmale Form: gleich breite Reiter mit Unterstrich, für Karten wie „Stat Info“ */
	.underline {
		display: grid;
		grid-auto-columns: 1fr;
		grid-auto-flow: column;
		gap: 0;
		padding: 0;
		margin: 0;
		border-top: 1px solid var(--fill-strong);
		border-bottom: 1px solid var(--fill-strong);
	}
	.underline > button,
	.underline > a {
		padding: 8px 6px;
		border: 0;
		border-bottom: 2px solid transparent;
		border-radius: 0;
		color: var(--faint);
		font-size: 13px;
		font-weight: 700;
		text-align: center;
	}
	.underline > .active {
		color: var(--text);
		background: none;
		border-bottom-color: var(--game-line);
	}
</style>
